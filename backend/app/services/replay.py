from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cities import CITIES, DEFAULT_MODELS, MODEL_DISPLAY
from ..models import Dataset, ForecastRecord, ObservationRecord, WarningThreshold
from ..schemas import CityOut, ModelValue, ReplaySource, ThresholdOut
from ..security import new_public_id


def latest_dataset(db: Session, dataset_type: str) -> Dataset | None:
    # PARTIAL 数据集仍可用于回放（缺测按数据不完整处理）；只排除 FAILED 批次
    return db.scalar(
        select(Dataset)
        .where(Dataset.dataset_type == dataset_type, Dataset.quality_status != "FAILED")
        .order_by(Dataset.imported_at.desc(), Dataset.id.desc())
        .limit(1)
    )


def _day_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


def get_threshold(db: Session, threshold_code: str) -> WarningThreshold | None:
    return db.scalar(
        select(WarningThreshold).where(
            WarningThreshold.hazard_type == "RAINSTORM",
            WarningThreshold.code == threshold_code,
            WarningThreshold.is_active.is_(True),
        )
    )


def compute_replay(db: Session, city_code: str, valid_date: date, threshold_code: str) -> dict | None:
    if city_code not in CITIES:
        return None
    threshold = get_threshold(db, threshold_code)
    if threshold is None:
        return None

    start = _day_start(valid_date)
    fc_dataset = latest_dataset(db, "FORECAST")
    stmt = select(ForecastRecord).where(
        ForecastRecord.city_code == city_code,
        ForecastRecord.valid_at == start,
        ForecastRecord.lead_hours == 24,
    )
    if fc_dataset is not None:
        stmt = stmt.where(ForecastRecord.dataset_id == fc_dataset.id)
    records = db.scalars(stmt).all()

    by_model: dict[str, ForecastRecord] = {}
    for r in records:
        by_model[r.model_code] = r

    model_values: list[ModelValue] = []
    present: list[ForecastRecord] = []
    for model in DEFAULT_MODELS:
        rec = by_model.get(model)
        val = rec.precipitation_mm if rec is not None else None
        model_values.append(ModelValue(model=MODEL_DISPLAY[model], precipitation_mm=float(val) if val is not None else None))
        if rec is not None:
            present.append(rec)

    complete = len(present) == len(DEFAULT_MODELS)
    fused = float(sum(r.precipitation_mm for r in present) / len(present)) if present else 0.0
    ecmwf = by_model.get("ecmwf_ifs025")
    baseline = float(ecmwf.precipitation_mm) if ecmwf is not None else None

    proxy_stmt = select(ObservationRecord.precipitation_mm).where(
        ObservationRecord.city_code == city_code,
        ObservationRecord.observed_date == valid_date,
        ObservationRecord.observation_type == "ERA5_PROXY",
    )
    obs_dataset = latest_dataset(db, "ERA5_LABEL")
    if obs_dataset is not None:
        proxy_stmt = proxy_stmt.where(ObservationRecord.dataset_id == obs_dataset.id)
    proxy = db.scalar(proxy_stmt)

    risk_level: str | None = None
    if complete and fused >= float(threshold.threshold_mm):
        risk_level = threshold.level

    return {
        "replay_id": new_public_id(),
        "city": CityOut(code=city_code, name=CITIES.get(city_code, city_code)),
        "valid_date": valid_date,
        "threshold": ThresholdOut(
            code=threshold.code,
            threshold_mm=float(threshold.threshold_mm),
            level=threshold.level,
        ),
        "models": model_values,
        "fused_mm": round(fused, 3) if complete else None,
        "baseline_mm": round(baseline, 3) if baseline is not None else None,
        "proxy_label_mm": float(proxy) if proxy is not None else None,
        "risk_level": risk_level,
        "data_status": "COMPLETE" if complete else "PARTIAL",
        "source": ReplaySource(dataset_version=fc_dataset.version if fc_dataset is not None else "sample"),
        "inputs": [
            {"forecast_record_id": r.id, "model_code": r.model_code, "value_mm": float(r.precipitation_mm)}
            for r in present
        ],
    }
