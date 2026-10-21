from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cities import CITIES, DEFAULT_MODELS, MODEL_DISPLAY
from ..models import Dataset, ForecastRecord, ObservationRecord, WarningThreshold
from ..schemas import CityOut, ModelValue, ReplaySource, ThresholdOut
from ..security import new_public_id


def _latest_dataset_id(db: Session, dataset_type: str) -> int | None:
    return db.scalar(
        select(Dataset.id)
        .where(Dataset.dataset_type == dataset_type, Dataset.quality_status == "READY")
        .order_by(Dataset.imported_at.desc(), Dataset.id.desc())
        .limit(1)
    )


def _day_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


def _get_threshold(db: Session, threshold_code: str) -> WarningThreshold | None:
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
    threshold = _get_threshold(db, threshold_code)
    if threshold is None:
        return None

    start = _day_start(valid_date)
    fc_dataset_id = _latest_dataset_id(db, "FORECAST")
    stmt = select(ForecastRecord).where(
        ForecastRecord.city_code == city_code,
        ForecastRecord.valid_at == start,
        ForecastRecord.lead_hours == 24,
    )
    if fc_dataset_id is not None:
        stmt = stmt.where(ForecastRecord.dataset_id == fc_dataset_id)
    records = db.scalars(stmt).all()

    by_model: dict[str, Decimal] = {}
    dataset_version: str | None = None
    for r in records:
        by_model[r.model_code] = r.precipitation_mm
        if dataset_version is None and r.dataset_id is not None:
            dataset_version = str(r.dataset_id)

    model_values: list[ModelValue] = []
    present: list[Decimal] = []
    for model in DEFAULT_MODELS:
        val = by_model.get(model)
        model_values.append(ModelValue(model=MODEL_DISPLAY[model], precipitation_mm=float(val) if val is not None else None))
        if val is not None:
            present.append(val)

    complete = len(present) == len(DEFAULT_MODELS)
    fused = float(sum(present) / len(present)) if present else 0.0
    baseline = float(by_model["ecmwf_ifs025"]) if by_model.get("ecmwf_ifs025") is not None else None

    proxy_stmt = select(ObservationRecord.precipitation_mm).where(
        ObservationRecord.city_code == city_code,
        ObservationRecord.observed_date == valid_date,
        ObservationRecord.observation_type == "ERA5_PROXY",
    )
    obs_dataset_id = _latest_dataset_id(db, "ERA5_LABEL")
    if obs_dataset_id is not None:
        proxy_stmt = proxy_stmt.where(ObservationRecord.dataset_id == obs_dataset_id)
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
        "source": ReplaySource(dataset_version=f"sample-{dataset_version}" if dataset_version else "sample"),
    }
