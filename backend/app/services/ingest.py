"""离线回放样本导入：先校验城市/模式/日期/数值，再在事务中写入并记录质量问题。"""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cities import CITIES, DEFAULT_MODELS, LEAD_HOURS
from ..clock import utcnow
from ..models import Dataset, DatasetIssue, ForecastRecord, ObservationRecord

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


def import_sample(session: Session, path: Path, forecast_source_id: int, era5_source_id: int) -> dict:
    """导入并校验回放样本；返回 ``{imported, forecast, observation, issues}``。

    幂等：同版本 FORECAST 数据集已存在时跳过。缺测/重复/乱序/异常值逐条写入
    ``dataset_issues``，不写入对应记录；有问题的数据集标 ``PARTIAL``（仍可回放）。
    """
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    version = data.get("version", "sample")
    days = data.get("days", [])
    if not isinstance(days, list):
        days = []

    exists = session.scalar(
        select(Dataset.id).where(Dataset.dataset_type == "FORECAST", Dataset.version == version)
    )
    if exists is not None:
        return {"imported": False, "forecast": 0, "observation": 0, "issues": 0}

    checksum = hashlib.sha256(raw).hexdigest()
    fc_dataset = Dataset(
        source_id=forecast_source_id, dataset_type="FORECAST", version=version,
        period_start=date.min, period_end=date.min, quality_status="READY",
        imported_at=utcnow(), checksum=checksum,
    )
    obs_dataset = Dataset(
        source_id=era5_source_id, dataset_type="ERA5_LABEL", version=version,
        period_start=date.min, period_end=date.min, quality_status="READY",
        imported_at=utcnow(), checksum=checksum,
    )
    session.add_all([fc_dataset, obs_dataset])
    session.flush()

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
        if city not in CITIES:
            issue(ISSUE_UNKNOWN_CITY, city_code=str(city), detail="未知城市代码")
            continue
        try:
            valid_date = date.fromisoformat(day["valid_date"])
        except (KeyError, ValueError, TypeError):
            issue(ISSUE_INVALID_DATE, city_code=city, detail=str(day.get("valid_date")))
            continue
        if (city, valid_date) in seen_city_dates:
            issue(ISSUE_DUPLICATE, city_code=city, valid_date=valid_date, detail="城市+日期重复")
            continue
        seen_city_dates.add((city, valid_date))
        all_dates.add(valid_date)

        previous = last_date_by_city.get(city)
        if previous is not None and valid_date < previous:
            issue(ISSUE_OUT_OF_ORDER, city_code=city, valid_date=valid_date, detail="日期早于同城前一条记录")
        last_date_by_city[city] = valid_date

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

    if all_dates:
        fc_dataset.period_start = min(all_dates)
        fc_dataset.period_end = max(all_dates)
        obs_dataset.period_start = min(all_dates)
        obs_dataset.period_end = max(all_dates)
    fc_dataset.row_count = n_fc
    obs_dataset.row_count = n_obs
    if fc_has_issue:
        fc_dataset.quality_status = "PARTIAL"
    if obs_has_issue:
        obs_dataset.quality_status = "PARTIAL"
    session.commit()
    return {"imported": True, "forecast": n_fc, "observation": n_obs, "issues": n_issues}
