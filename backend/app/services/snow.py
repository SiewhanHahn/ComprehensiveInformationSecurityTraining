"""Windowed snowfall risk from a curated archived run, independent of verification."""
from datetime import timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, field_validator

from ..assessment_schemas import (
    CaseSource, HazardMetric, SnowAssessment, SnowCaseInfo, SnowCatalog, SnowForecastHour,
    SnowReplay, SnowStationReport, SnowVerification,
)
from ..hazards import SNOW_24H_THRESHOLD_CM

_HOUR = timedelta(hours=1)
WINDOW_HOURS = 24
REACHED_RISK_LEVEL = "YELLOW"  # 教学标记，不是官方预警信号。
_DATA_DIR = Path(__file__).resolve().parents[1] / "data/snow"
_CASE_IDS = ("jinan-20250302", "jinan-20250304")


class SnowForecastSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snowfall_unit: Literal["cm"]
    temperature_unit: Literal["°C"]
    hours: tuple[SnowForecastHour, ...]

    @field_validator("hours")
    @classmethod
    def distinct_valid_times(cls, hours: tuple[SnowForecastHour, ...]) -> tuple[SnowForecastHour, ...]:
        if len({hour.valid_at for hour in hours}) != len(hours):
            raise ValueError("duplicate snow forecast valid time")
        return hours


class SnowStationReports(BaseModel):
    source: CaseSource
    station_id: str
    observations: tuple[SnowStationReport, ...]


class SnowCase(BaseModel):
    info: SnowCaseInfo
    forecast: SnowForecastSeries
    verification: SnowStationReports


@lru_cache(maxsize=len(_CASE_IDS))
def _read_case(case_id: str) -> SnowCase:
    case = SnowCase.model_validate_json((_DATA_DIR / f"{case_id}.json").read_bytes())
    if case.info.case_id != case_id:
        raise ValueError("snow case fixture ID mismatch")
    return case


def get_case(case_id: str) -> SnowCase:
    if case_id not in _CASE_IDS:
        raise HTTPException(404, "NOT_FOUND")
    return _read_case(case_id)


def catalog() -> SnowCatalog:
    return SnowCatalog(cases=[get_case(case_id).info for case_id in _CASE_IDS])


def assess_forecast(info: SnowCaseInfo, series: SnowForecastSeries) -> SnowAssessment:
    """Sum hour-ending snowfall forecasts; never use station reports."""
    start = info.window_start
    by_time = {hour.valid_at.astimezone(timezone.utc): hour for hour in series.hours}
    end_times = (start + i * _HOUR for i in range(1, WINDOW_HOURS + 1))
    hours = tuple(by_time[t] for t in end_times if t in by_time)
    available = [(hour.valid_at, hour.snowfall_cm, hour.temperature_c) for hour in hours
                 if hour.snowfall_cm is not None and hour.temperature_c is not None]
    args = dict(case=info, forecast_window_end=start + WINDOW_HOURS * _HOUR, hours=hours,
                usable_hours=len(available))
    if len(available) != WINDOW_HOURS:
        return SnowAssessment(**args, outcome="INSUFFICIENT")

    total = sum(Decimal(str(snowfall)) for _, snowfall, _ in available)
    threshold = Decimal(str(SNOW_24H_THRESHOLD_CM))
    snow_ends = [stamp for stamp, snowfall, _ in available if snowfall > 0]
    metric = HazardMetric(label="24 小时累计预报降雪", unit="cm", value=float(total),
                          threshold=SNOW_24H_THRESHOLD_CM, comparison=">=")
    return SnowAssessment(**args, metric=metric, outcome="REACHED" if total >= threshold else "NOT_REACHED",
                          min_temperature_c=min(temp for _, _, temp in available),
                          snow_period_start=snow_ends[0] - _HOUR if snow_ends else None,
                          snow_period_end=snow_ends[-1] if snow_ends else None)


def assess_case(case_id: str) -> tuple[SnowCase, SnowAssessment]:
    case = get_case(case_id)
    return case, assess_forecast(case.info, case.forecast)


def replay(case_id: str) -> SnowReplay:
    case, forecast = assess_case(case_id)
    reference = case.verification
    observations = tuple(sorted(
        (report for report in reference.observations
         if case.info.window_start < report.observed_at <= forecast.forecast_window_end),
        key=lambda report: report.observed_at,
    ))
    verification = None
    if observations:
        outcome = "SNOW_REPORTED" if any(report.code in {"70", "74"} for report in observations) else "NO_SNOW_IN_SAMPLES"
        verification = SnowVerification(source=reference.source, station_id=reference.station_id,
                                        observations=observations, outcome=outcome)
    return SnowReplay(forecast=forecast, verification=verification)
