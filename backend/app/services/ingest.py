"""离线回放样本导入：先校验城市/模式/日期/数值，再在事务中写入并记录质量问题。"""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..cities import CITIES, DEFAULT_MODELS, LEAD_HOURS
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


def import_sample(session: Session, path: Path, forecast_source_id: int, era5_source_id: int) -> dict:
    """导入并校验回放样本；返回 ``{imported, forecast, observation, issues}``。

    幂等：同版本 FORECAST 数据集已有可用数据时跳过；FAILED 或 0 行版本允许用修正后的
    样本重导。缺测/重复/乱序/异常值逐条写入 ``dataset_issues``，不写入对应记录；
    有问题的数据集标 ``PARTIAL``（仍可回放），一条可用记录都没有时标 ``FAILED``。
    """
    raw = path.read_bytes()
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

    checksum = hashlib.sha256(raw).hexdigest()
    # 幂等按文件内容而不是只看版本：同版本换了文件（例如补上 proxy_label_mm）允许重导；
    # 字节完全相同的文件直接跳过，避免每次 compose up 都重写数据。
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
    if fc_dataset is not None and fc_dataset.checksum == checksum:
        result = {"imported": False, "forecast": 0, "observation": 0, "issues": 0}
        if fc_dataset.quality_status == "FAILED":
            result["unusable"] = True
        return result

    # 被预警引用过的数据集不能删记录重写：fusion_inputs.forecast_record_id 外键是 RESTRICT。
    # 拒绝覆盖并让操作者提升 version，避免 MySQL 1451 或悄悄丢失溯源链。
    if fc_dataset is not None and _has_fusion_inputs(session, fc_dataset.id):
        return {"imported": False, "forecast": 0, "observation": 0, "issues": 0, "blocked": "dataset_in_use"}

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
        if parse_error:
            detail = parse_error
        elif not structure_ok:
            detail = "样本顶层不是 JSON 对象"
        else:
            detail = "样本缺少 days 数组或为空"
        _add_issue(
            session, fc_dataset.id, ISSUE_INVALID_VALUE,
            detail=f"{detail}，整个数据集标 FAILED（不参与回放）",
        )
        session.commit()
        return {"imported": False, "forecast": 0, "observation": 0, "issues": 1, "unusable": True}

    n_fc = 0
    n_obs = 0
    n_issues = 0
    fc_has_issue = False
    obs_has_issue = False
    seen: set[tuple[str, str, datetime, int]] = set()
    seen_city_dates: set[tuple[str, date]] = set()
    all_dates: set[date] = set()
    last_date_by_city: dict[str, date] = {}

    def issue(issue_type, *, city_code=None, model_code=None, valid_date=None, detail=None, on_obs=False):
        nonlocal n_issues, fc_has_issue, obs_has_issue
        target = obs_dataset.id if on_obs else fc_dataset.id
        _add_issue(session, target, issue_type, city_code=city_code, model_code=model_code, valid_date=valid_date, detail=detail)
        n_issues += 1
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
            valid_date = date.fromisoformat(day["valid_date"])
        except (KeyError, ValueError, TypeError):
            issue(ISSUE_INVALID_DATE, city_code=city, detail=str(day.get("valid_date")))
            continue
        if (city, valid_date) in seen_city_dates:
            issue(ISSUE_DUPLICATE, city_code=city, valid_date=valid_date, detail="城市+日期重复")
            continue
        all_dates.add(valid_date)

        previous = last_date_by_city.get(city)
        if previous is not None and valid_date < previous:
            issue(ISSUE_OUT_OF_ORDER, city_code=city, valid_date=valid_date, detail="日期早于同城前一条记录")
        day_fc_before = n_fc
        day_obs_before = n_obs

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
            session.add(
                ForecastRecord(
                    dataset_id=fc_dataset.id, city_code=city, model_code=model_code,
                    valid_at=valid_at, lead_hours=LEAD_HOURS, precipitation_mm=dec, is_complete=True,
                )
            )
            n_fc += 1

        # 默认模式之外的键单独记，既不参与融合也不悄悄丢掉
        for model_code in models:
            if model_code not in DEFAULT_MODELS:
                issue(ISSUE_UNKNOWN_MODEL, city_code=city, model_code=model_code, valid_date=valid_date)

        if day.get("proxy_label_mm") is not None:
            proxy = _to_decimal(day["proxy_label_mm"])
            if proxy is None or proxy < 0 or proxy > MAX_PRECIP_MM:
                issue(ISSUE_INVALID_VALUE, city_code=city, valid_date=valid_date, detail=str(day["proxy_label_mm"]), on_obs=True)
            else:
                session.add(
                    ObservationRecord(
                        dataset_id=obs_dataset.id, city_code=city, observation_type="ERA5_PROXY",
                        observed_date=valid_date, precipitation_mm=proxy, quality_flag="OK",
                    )
                )
                n_obs += 1

        # 只有真正产出记录的条目才占用 (city, date) 去重键；否则一条全坏条目
        # 会把后面修正过的同城同日条目误判为 DUPLICATE，整天数据一起丢失。
        if n_fc > day_fc_before or n_obs > day_obs_before:
            seen_city_dates.add((city, valid_date))
            last_date_by_city[city] = valid_date

    if all_dates:
        fc_dataset.period_start = min(all_dates)
        fc_dataset.period_end = max(all_dates)
        obs_dataset.period_start = min(all_dates)
        obs_dataset.period_end = max(all_dates)
    fc_dataset.row_count = n_fc
    obs_dataset.row_count = n_obs
    # 0 行数据集绝不能留成 READY/PARTIAL：latest_dataset 只排除 FAILED，
    # 一个空数据集会因为 imported_at 最新而遮蔽此前可用的数据。
    if n_fc == 0:
        fc_dataset.quality_status = "FAILED"
        issue(ISSUE_INVALID_VALUE, detail="样本没有任何可用的预报记录，整个 FORECAST 数据集标 FAILED")
    elif fc_has_issue:
        fc_dataset.quality_status = "PARTIAL"
    if n_obs == 0:
        obs_dataset.quality_status = "FAILED"
    elif obs_has_issue:
        obs_dataset.quality_status = "PARTIAL"
    session.commit()
    result = {"imported": True, "forecast": n_fc, "observation": n_obs, "issues": n_issues}
    if n_fc == 0:
        result["unusable"] = True
    return result
