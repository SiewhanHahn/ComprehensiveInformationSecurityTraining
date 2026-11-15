from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cities import CITIES, DEFAULT_MODELS, LEAD_HOURS, MODEL_DISPLAY
from ..models import Dataset, ForecastRecord, ObservationRecord, WarningThreshold
from ..schemas import CityOut, ModelValue, ReplaySource, ThresholdOut
from ..security import new_public_id


def latest_dataset(db: Session, dataset_type: str, version: str | None = None) -> Dataset | None:
    # PARTIAL 数据集仍可用于回放（缺测按数据不完整处理）；只排除 FAILED 批次。
    # version 用于把同一次导入的 FORECAST 与 ERA5_LABEL 配成一对，避免混版本。
    stmt = select(Dataset).where(
        Dataset.dataset_type == dataset_type,
        Dataset.quality_status != "FAILED",
    )
    if version is not None:
        stmt = stmt.where(Dataset.version == version)
    return db.scalar(stmt.order_by(Dataset.imported_at.desc(), Dataset.id.desc()).limit(1))


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
    if fc_dataset is not None:
        records = db.scalars(
            select(ForecastRecord).where(
                ForecastRecord.city_code == city_code,
                ForecastRecord.valid_at == start,
                ForecastRecord.lead_hours == LEAD_HOURS,
                ForecastRecord.dataset_id == fc_dataset.id,
            )
        ).all()
    else:
        records = []

    by_model: dict[str, ForecastRecord] = {}
    for r in records:
        by_model[r.model_code] = r

    model_values: list[ModelValue] = []
    present: list[ForecastRecord] = []
    for model in DEFAULT_MODELS:
        rec = by_model.get(model)
        # 值为空或占位行（is_complete=False）都不算「这一天有该模式」：
        # 否则 sum() 会拿 None 做算术直接 500，也会把不完整的一天判成 COMPLETE
        usable = rec is not None and rec.precipitation_mm is not None and rec.is_complete
        val = rec.precipitation_mm if usable else None
        model_values.append(ModelValue(model=MODEL_DISPLAY[model], precipitation_mm=float(val) if val is not None else None))
        if usable:
            present.append(rec)

    complete = len(present) == len(DEFAULT_MODELS)
    quant = Decimal("0.001")
    fused_dec = (
        (sum((r.precipitation_mm for r in present), Decimal("0")) / Decimal(len(present))).quantize(
            quant, rounding=ROUND_HALF_UP
        )
        if present
        else Decimal("0.000")
    )
    # 判定与展示用同一精度：全程用 Decimal HALF_UP 避免二进制浮点偶舍入与阈值边界偏差
    ecmwf = by_model.get("ecmwf_ifs025")
    ecmwf_usable = ecmwf is not None and ecmwf.precipitation_mm is not None and ecmwf.is_complete
    baseline_dec = ecmwf.precipitation_mm.quantize(quant, rounding=ROUND_HALF_UP) if ecmwf_usable else None

    proxy = None
    # 代理标签必须来自与预报数据集同一版本：没有可用预报数据集时不回退到孤立的 ERA5 版本，
    # 避免已失败/损坏的观测数据单独泄漏，或与 dataset_version="sample" 张冠李戴。
    obs_dataset = latest_dataset(db, "ERA5_LABEL", version=fc_dataset.version) if fc_dataset is not None else None
    if obs_dataset is not None:
        proxy = db.scalar(
            select(ObservationRecord.precipitation_mm).where(
                ObservationRecord.city_code == city_code,
                ObservationRecord.observed_date == valid_date,
                ObservationRecord.observation_type == "ERA5_PROXY",
                ObservationRecord.dataset_id == obs_dataset.id,
            )
        )
    proxy_dec = proxy.quantize(quant, rounding=ROUND_HALF_UP) if proxy is not None else None

    risk_level: str | None = None
    if complete and fused_dec >= threshold.threshold_mm:
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
        "fused_mm": float(fused_dec) if complete else None,
        "baseline_mm": float(baseline_dec) if baseline_dec is not None else None,
        "proxy_label_mm": float(proxy_dec) if proxy_dec is not None else None,
        "fused_dec": fused_dec if complete else None,
        "baseline_dec": baseline_dec,
        "proxy_dec": proxy_dec,
        "risk_level": risk_level,
        "data_status": "COMPLETE" if complete else "PARTIAL",
        "source": ReplaySource(
            dataset_version=fc_dataset.version if fc_dataset is not None else "sample",
            cached_at=fc_dataset.imported_at if fc_dataset is not None else None,
        ),
        "inputs": [
            {
                "forecast_record_id": r.id,
                "model_code": r.model_code,
                "value_mm": float(r.precipitation_mm),
                "value_dec": r.precipitation_mm,
            }
            for r in present
        ],
        "threshold_row": threshold,
    }
