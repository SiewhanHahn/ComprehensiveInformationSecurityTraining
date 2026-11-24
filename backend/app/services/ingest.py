"""离线回放样本导入：先校验城市/模式/日期/数值，再在事务中写入并记录质量问题。"""

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..cities import CITIES, DEFAULT_MODELS, LEAD_HOURS, PROTOCOL_END_DATE, PROTOCOL_START_DATE
from ..clock import utcnow
from ..models import Dataset, DatasetIssue, ForecastRecord, FusionInput, ObservationRecord

MAX_PRECIP_MM = 2000.0  # 日累计降水物理上不可能超过的保守上限

ISSUE_MISSING_MODEL = "MISSING_MODEL"
ISSUE_DUPLICATE = "DUPLICATE"
ISSUE_OUT_OF_ORDER = "OUT_OF_ORDER"
ISSUE_INVALID_VALUE = "INVALID_VALUE"
ISSUE_UNKNOWN_CITY = "UNKNOWN_CITY"
ISSUE_UNKNOWN_MODEL = "UNKNOWN_MODEL"
ISSUE_INVALID_DATE = "INVALID_DATE"


def _clip(value, width: int) -> str | None:
    """把任意原始值压进列宽。

    样本里的城市/模式是自由文本，直接写进 VARCHAR(32) 时超长值会让 MySQL 报 1406
    并连带回滚整个导入——宁可截断，也要把这条质量问题记下来。
    """
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    return text[:width]


def _add_issue(session, dataset_id, issue_type, *, city_code=None, model_code=None, valid_date=None, detail=None):
    session.add(
        DatasetIssue(
            dataset_id=dataset_id,
            issue_type=_clip(issue_type, 32),
            city_code=_clip(city_code, 32),
            model_code=_clip(model_code, 32),
            valid_date=valid_date,
            detail=_clip(detail, 500),
        )
    )


def _to_decimal(value) -> Decimal | None:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not d.is_finite():
        return None
    return d


def _has_fusion_inputs(session: Session, dataset_id: int) -> bool:
    """该数据集的预报记录是否已被某个预警的融合输入引用（外键 RESTRICT，不能删）。"""
    return session.scalar(
        select(FusionInput.forecast_record_id)
        .join(ForecastRecord, ForecastRecord.id == FusionInput.forecast_record_id)
        .where(ForecastRecord.dataset_id == dataset_id)
        .limit(1)
    ) is not None


def _reset_dataset(session: Session, dataset: Dataset, status: str, checksum: str) -> None:
    """复用同版本的 FAILED/空数据集：清掉上一次失败的记录与问题，再按本次样本重写。"""
    session.execute(delete(DatasetIssue).where(DatasetIssue.dataset_id == dataset.id))
    session.execute(delete(ForecastRecord).where(ForecastRecord.dataset_id == dataset.id))
    session.execute(delete(ObservationRecord).where(ObservationRecord.dataset_id == dataset.id))
    dataset.quality_status = status
    dataset.checksum = checksum
    dataset.imported_at = utcnow()
    dataset.row_count = 0
    dataset.period_start = date.min
    dataset.period_end = date.min


def _parse_protocol_date(value: object) -> date:
    """只接受协议范围内的 ASCII YYYY-MM-DD，不规范化或截断原始值。"""
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ValueError("invalid protocol date format")
    parsed = date.fromisoformat(value)
    if not PROTOCOL_START_DATE <= parsed <= PROTOCOL_END_DATE:
        raise ValueError("date outside protocol bounds")
    return parsed


def _validate_days(days: list) -> dict:
    """在内存里预先校验并构造待写行；校验未通过时不触碰既有数据集。"""
    fc_rows: list[tuple[str, str, datetime, Decimal]] = []
    obs_rows: list[tuple[str, date, Decimal]] = []
    issues: list[tuple[bool, str, str | None, str | None, date | None, str | None]] = []
    fc_has_issue = False
    obs_has_issue = False
    seen: set[tuple[str, str, datetime, int]] = set()
    seen_obs: set[tuple[str, date]] = set()
    fc_dates: set[date] = set()
    obs_dates: set[date] = set()
    last_date_by_city: dict[str, date] = {}

    def issue(issue_type, *, city_code=None, model_code=None, valid_date=None, detail=None, on_obs=False):
        nonlocal fc_has_issue, obs_has_issue
        issues.append((on_obs, issue_type, city_code, model_code, valid_date, detail))
        if on_obs:
            obs_has_issue = True
        else:
            fc_has_issue = True

    for day in days:
        if not isinstance(day, dict):
            issue(ISSUE_INVALID_VALUE, detail=f"条目不是对象：{day!r}")
            continue
        city = day.get("city_code")
        # 先判类型再判成员：list/dict 不可哈希，直接 in CITIES 会抛 TypeError，
        # 整个导入随之中断，连一条质量问题都记不下来。
        if not isinstance(city, str) or city not in CITIES:
            issue(ISSUE_UNKNOWN_CITY, city_code=city, detail="未知城市代码")
            continue
        try:
            valid_date = _parse_protocol_date(day.get("valid_date"))
        except ValueError:
            issue(ISSUE_INVALID_DATE, city_code=city, detail=str(day.get("valid_date")))
            continue
        previous = last_date_by_city.get(city)
        if previous is not None and valid_date < previous:
            issue(ISSUE_OUT_OF_ORDER, city_code=city, valid_date=valid_date, detail="日期早于同城前一条记录")
        day_fc_before = len(fc_rows)
        day_obs_before = len(obs_rows)

        valid_at = datetime(valid_date.year, valid_date.month, valid_date.day)
        raw_models = day.get("models")
        if raw_models is None:
            issue(ISSUE_INVALID_VALUE, city_code=city, valid_date=valid_date, detail="models 缺失或为 null")
            models = {}
        elif not isinstance(raw_models, dict):
            issue(ISSUE_INVALID_VALUE, city_code=city, valid_date=valid_date, detail="models 不是对象")
            models = {}
        else:
            models = raw_models
        # 逐个默认模式检查：只遍历「存在的键」会让「整个模式都没出现」既不记账也不标 PARTIAL，
        # 数据集保持 READY 而回放却判 PARTIAL
        for model_code in DEFAULT_MODELS:
            mm = models.get(model_code)
            if mm is None:
                issue(ISSUE_MISSING_MODEL, city_code=city, model_code=model_code, valid_date=valid_date)
                continue
            dec = _to_decimal(mm)
            if dec is None or dec < 0 or dec > MAX_PRECIP_MM:
                issue(ISSUE_INVALID_VALUE, city_code=city, model_code=model_code, valid_date=valid_date, detail=str(mm))
                continue
            key = (city, model_code, valid_at, LEAD_HOURS)
            if key in seen:
                issue(ISSUE_DUPLICATE, city_code=city, model_code=model_code, valid_date=valid_date, detail="同城同模式同提前量重复")
                continue
            seen.add(key)
            fc_rows.append((city, model_code, valid_at, dec))
            fc_dates.add(valid_date)

        # 默认模式之外的键单独记，既不参与融合也不悄悄丢掉
        for model_code in models:
            if model_code not in DEFAULT_MODELS:
                issue(ISSUE_UNKNOWN_MODEL, city_code=city, model_code=model_code, valid_date=valid_date)

        if day.get("proxy_label_mm") is None:
            issue("MISSING_PROXY", city_code=city, valid_date=valid_date, on_obs=True)
        else:
            proxy = _to_decimal(day["proxy_label_mm"])
            if proxy is None or proxy < 0 or proxy > MAX_PRECIP_MM:
                issue(ISSUE_INVALID_VALUE, city_code=city, valid_date=valid_date, detail=str(day["proxy_label_mm"]), on_obs=True)
            elif (city, valid_date) in seen_obs:
                issue(ISSUE_DUPLICATE, city_code=city, valid_date=valid_date, detail="同城同日代理标签重复", on_obs=True)
            else:
                seen_obs.add((city, valid_date))
                obs_rows.append((city, valid_date, proxy))
                obs_dates.add(valid_date)

        # 预报和标签独立去重；一侧缺失不妨碍随后补全另一侧。
        if len(fc_rows) > day_fc_before or len(obs_rows) > day_obs_before:
            last_date_by_city[city] = valid_date

    return {
        "fc_rows": fc_rows,
        "obs_rows": obs_rows,
        "issues": issues,
        "fc_dates": fc_dates,
        "obs_dates": obs_dates,
        "fc_has_issue": fc_has_issue,
        "obs_has_issue": obs_has_issue,
    }


def _import_result(session: Session, outcome: str, **values) -> dict:
    """outcome 描述本次操作；可用性检查所有版本的 FORECAST，而非本次写入行数。"""
    has_usable_forecast = session.scalar(
        select(Dataset.id).where(
            Dataset.dataset_type == "FORECAST",
            Dataset.quality_status != "FAILED",
            Dataset.row_count > 0,
        ).limit(1)
    ) is not None
    return {
        "imported": False, "forecast": 0, "observation": 0, "issues": 0,
        **values, "outcome": outcome, "has_usable_forecast": has_usable_forecast,
    }


def import_sample(session: Session, path: Path, forecast_source_id: int, era5_source_id: int) -> dict:
    """返回兼容的计数字典，另含本次 ``outcome`` 和库内 ``has_usable_forecast``。

    幂等：同版本 FORECAST 与 ERA5_LABEL 数据集校验和都未变时跳过；FAILED 或 0 行版本允许用
    修正后的样本重导；已有可用数据时，新文件若无效或产出 0 条预报，不覆盖既有数据集。
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return _import_result(session, "file_unreadable", unusable=True, error=str(exc))
    parse_error = None
    try:
        data = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        parse_error = "样本不是 UTF-8 文本"
        data = {}
    except json.JSONDecodeError as exc:
        parse_error = f"样本不是合法 JSON：{exc.msg}（行 {exc.lineno}）"
        data = {}
    # 顶层必须是对象：否则 data.get() 会抛 AttributeError，seed 直接退出、API 起不来。
    # 解析/结构错误也落成 FAILED 数据集并记问题，而不是把异常抛给调用方。
    structure_ok = isinstance(data, dict)
    if not structure_ok:
        data = {}
    version = str(data.get("version") or "sample").strip()[:100] or "sample"
    days = data.get("days", [])
    # 结构不对或一条都没有时不能静默当成「导入成功」：那会留下一个 0 行、quality_status=READY
    # 的数据集，它的 imported_at 最新又不是 FAILED，latest_dataset() 会选中它，
    # 于是所有回放都变成 PARTIAL、真实数据被整体遮蔽。改成标 FAILED + 记一条问题。
    usable_sample = isinstance(days, list) and bool(days)
    if not usable_sample:
        days = []
        if parse_error is None:
            parse_error = "样本缺少 days 数组或为空" if structure_ok else "样本顶层不是 JSON 对象"

    checksum = hashlib.sha256(raw).hexdigest()
    # 幂等按文件内容而不是只看版本：同版本换了文件（例如补上 proxy_label_mm）允许重导；
    # 字节完全相同且 FORECAST / ERA5_LABEL 两个数据集都完整一致时才跳过，避免静默漏掉缺失的观测集。
    # (source_id, dataset_type, version) 有唯一约束，重导时复用旧行。
    fc_dataset = session.scalar(
        select(Dataset).where(
            Dataset.source_id == forecast_source_id,
            Dataset.dataset_type == "FORECAST",
            Dataset.version == version,
        )
    )
    obs_dataset = session.scalar(
        select(Dataset).where(
            Dataset.source_id == era5_source_id,
            Dataset.dataset_type == "ERA5_LABEL",
            Dataset.version == version,
        )
    )
    if (
        fc_dataset is not None
        and fc_dataset.checksum == checksum
        and obs_dataset is not None
        and obs_dataset.checksum == checksum
    ):
        if fc_dataset.quality_status == "FAILED":
            return _import_result(session, "unchanged_failed", unusable=True, error=parse_error)
        return _import_result(session, "unchanged")

    # 被预警引用过的数据集不能删记录重写：fusion_inputs.forecast_record_id 外键是 RESTRICT。
    # 拒绝覆盖并让操作者提升 version，避免 MySQL 1451 或悄悄丢失溯源链。
    if fc_dataset is not None and _has_fusion_inputs(session, fc_dataset.id):
        return _import_result(session, "dataset_in_use", blocked="dataset_in_use")

    staged = _validate_days(days) if usable_sample else None
    has_usable_existing = (
        fc_dataset is not None and fc_dataset.quality_status != "FAILED" and fc_dataset.row_count > 0
    )
    if has_usable_existing and (not usable_sample or len(staged["fc_rows"]) == 0):
        return _import_result(
            session, "preserved_existing",
            issues=len(staged["issues"]) if staged is not None else 1,
            unusable=True, blocked="unusable_sample",
            error=parse_error or "样本没有任何可用的预报记录",
        )

    initial_status = "READY" if usable_sample else "FAILED"
    if fc_dataset is None:
        fc_dataset = Dataset(
            source_id=forecast_source_id, dataset_type="FORECAST", version=version,
            period_start=date.min, period_end=date.min, quality_status=initial_status,
            imported_at=utcnow(), checksum=checksum,
        )
        session.add(fc_dataset)
    else:
        _reset_dataset(session, fc_dataset, initial_status, checksum)
    if obs_dataset is None:
        obs_dataset = Dataset(
            source_id=era5_source_id, dataset_type="ERA5_LABEL", version=version,
            period_start=date.min, period_end=date.min, quality_status=initial_status,
            imported_at=utcnow(), checksum=checksum,
        )
        session.add(obs_dataset)
    else:
        _reset_dataset(session, obs_dataset, initial_status, checksum)
    session.flush()

    if not usable_sample:
        _add_issue(
            session, fc_dataset.id, ISSUE_INVALID_VALUE,
            detail=f"{parse_error}，整个数据集标 FAILED（不参与回放）",
        )
        session.commit()
        return _import_result(session, "marked_failed", issues=1, unusable=True, error=parse_error)

    fc_rows = staged["fc_rows"]
    obs_rows = staged["obs_rows"]
    staged_issues = staged["issues"]
    fc_dates = staged["fc_dates"]
    obs_dates = staged["obs_dates"]
    fc_has_issue = staged["fc_has_issue"]
    obs_has_issue = staged["obs_has_issue"]

    for city, model_code, valid_at, dec in fc_rows:
        session.add(
            ForecastRecord(
                dataset_id=fc_dataset.id, city_code=city, model_code=model_code,
                valid_at=valid_at, lead_hours=LEAD_HOURS, precipitation_mm=dec, is_complete=True,
            )
        )
    for city, valid_date, proxy in obs_rows:
        session.add(
            ObservationRecord(
                dataset_id=obs_dataset.id, city_code=city, observation_type="ERA5_PROXY",
                observed_date=valid_date, precipitation_mm=proxy, quality_flag="OK",
            )
        )
    for on_obs, issue_type, city_code, model_code, valid_date, detail in staged_issues:
        target = obs_dataset.id if on_obs else fc_dataset.id
        _add_issue(session, target, issue_type, city_code=city_code, model_code=model_code, valid_date=valid_date, detail=detail)

    n_fc = len(fc_rows)
    n_obs = len(obs_rows)
    n_issues = len(staged_issues)

    if fc_dates:
        fc_dataset.period_start = min(fc_dates)
        fc_dataset.period_end = max(fc_dates)
    if obs_dates:
        obs_dataset.period_start = min(obs_dates)
        obs_dataset.period_end = max(obs_dates)
    fc_dataset.row_count = n_fc
    obs_dataset.row_count = n_obs
    # 0 行数据集绝不能留成 READY/PARTIAL：latest_dataset 只排除 FAILED，
    # 一个空数据集会因为 imported_at 最新而遮蔽此前可用的数据。
    if n_fc == 0:
        fc_dataset.quality_status = "FAILED"
        _add_issue(session, fc_dataset.id, ISSUE_INVALID_VALUE, detail="样本没有任何可用的预报记录，整个 FORECAST 数据集标 FAILED")
        n_issues += 1
    elif fc_has_issue:
        fc_dataset.quality_status = "PARTIAL"
    if n_obs == 0:
        obs_dataset.quality_status = "FAILED"
    elif obs_has_issue:
        obs_dataset.quality_status = "PARTIAL"
    session.commit()
    counts = {"imported": True, "forecast": n_fc, "observation": n_obs, "issues": n_issues}
    if n_fc == 0:
        return _import_result(session, "marked_failed", **counts, unusable=True)
    return _import_result(session, "imported", **counts)
