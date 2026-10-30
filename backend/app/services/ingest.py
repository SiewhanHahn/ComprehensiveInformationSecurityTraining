"""离线回放样本导入：先校验城市/模式/日期/数值，再在事务中写入并记录质量问题。"""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cities import CITIES, DEFAULT_MODELS
from ..clock import utcnow
from ..models import Dataset, DatasetIssue, ForecastRecord, ObservationRecord

LEAD_HOURS = 24
MAX_PRECIP_MM = 2000.0  # 日累计降水物理上不可能超过的保守上限

ISSUE_MISSING_MODEL = "MISSING_MODEL"
ISSUE_DUPLICATE = "DUPLICATE"
ISSUE_OUT_OF_ORDER = "OUT_OF_ORDER"
ISSUE_INVALID_VALUE = "INVALID_VALUE"
ISSUE_UNKNOWN_CITY = "UNKNOWN_CITY"
ISSUE_UNKNOWN_MODEL = "UNKNOWN_MODEL"
ISSUE_INVALID_DATE = "INVALID_DATE"


def _add_issue(session, dataset_id, issue_type, *, city_code=None, model_code=None, valid_date=None, detail=None):
    session.add(
        DatasetIssue(
            dataset_id=dataset_id,
            issue_type=issue_type,
            city_code=city_code,
            model_code=model_code,
            valid_date=valid_date,
            detail=detail,
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
        city = day.get("city_code")
        if city not in CITIES:
            issue(ISSUE_UNKNOWN_CITY, city_code=str(city), detail="未知城市代码")
            continue
        try:
            valid_date = date.fromisoformat(day["valid_date"])
        except (KeyError, ValueError, TypeError):
            issue(ISSUE_INVALID_DATE, city_code=city, detail=str(day.get("valid_date")))
            continue
        if valid_date in all_dates:
            issue(ISSUE_DUPLICATE, city_code=city, valid_date=valid_date, detail="城市+日期重复")
            continue
        all_dates.add(valid_date)

        previous = last_date_by_city.get(city)
        if previous is not None and valid_date < previous:
            issue(ISSUE_OUT_OF_ORDER, city_code=city, valid_date=valid_date, detail="日期早于同城前一条记录")
        last_date_by_city[city] = valid_date

        valid_at = datetime(valid_date.year, valid_date.month, valid_date.day)
        for model_code, mm in day.get("models", {}).items():
            if model_code not in DEFAULT_MODELS:
                issue(ISSUE_UNKNOWN_MODEL, city_code=city, model_code=str(model_code), valid_date=valid_date)
                continue
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
