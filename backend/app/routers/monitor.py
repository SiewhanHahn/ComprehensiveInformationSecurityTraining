from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..cities import DEFAULT_MODELS
from ..db import get_db
from ..deps import get_current_user
from ..models import DataSource, Dataset, ForecastRecord, ObservationRecord

router = APIRouter()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


@router.get("/monitor/status")
def monitor_status(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> dict:
    sources = db.scalars(select(DataSource).order_by(DataSource.id)).all()
    datasets = db.scalars(select(Dataset).order_by(Dataset.id.desc())).all()
    forecast_count = db.scalar(select(func.count()).select_from(ForecastRecord)) or 0
    observation_count = db.scalar(select(func.count()).select_from(ObservationRecord)) or 0
    latest_valid_at = db.scalar(select(func.max(ForecastRecord.valid_at)))
    latest_observed_date = db.scalar(select(func.max(ObservationRecord.observed_date)))
    models = sorted(db.scalars(select(ForecastRecord.model_code).distinct()).all())
    cities = sorted(db.scalars(select(ForecastRecord.city_code).distinct()).all())

    completeness = "COMPLETE" if set(DEFAULT_MODELS).issubset(models) else "PARTIAL"

    return {
        "mode": "SNAPSHOT",
        "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "sources": [
            {
                "code": s.code,
                "name": s.name,
                "data_type": s.data_type,
                "license_note": s.license_note,
                "is_active": s.is_active,
            }
            for s in sources
        ],
        "datasets": [
            {
                "id": d.id,
                "dataset_type": d.dataset_type,
                "version": d.version,
                "period_start": d.period_start.isoformat(),
                "period_end": d.period_end.isoformat(),
                "row_count": d.row_count,
                "quality_status": d.quality_status,
                "imported_at": _iso(d.imported_at),
            }
            for d in datasets
        ],
        "records": {
            "forecast": forecast_count,
            "observation": observation_count,
            "latest_forecast_valid_at": _iso(latest_valid_at),
            "latest_observed_date": latest_observed_date.isoformat() if latest_observed_date else None,
        },
        "coverage": {
            "models": models,
            "expected_models": DEFAULT_MODELS,
            "cities": cities,
            "completeness": completeness,
        },
    }
