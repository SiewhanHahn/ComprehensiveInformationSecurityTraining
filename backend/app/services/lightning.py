"""Archived HRRR lightning guidance, kept separate from the station verification."""
from datetime import timedelta
from functools import lru_cache
from logging import getLogger
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..assessment_schemas import (
    LIGHTNING_WINDOW_HOURS, CaseSource, HazardMetric, LightningAssessment, LightningCaseInfo,
    LightningCatalog, LightningForecastHour, LightningReplay, LightningStationReport, LightningVerification,
)
from ..hazards import LIGHTNING_LTNG_THRESHOLD

_LOG = getLogger(__name__)
_HOUR = timedelta(hours=1)
_DATA_DIR = Path(__file__).resolve().parents[1] / 'data/lightning'
_CASE_IDS = ('kstl-20250315-00z', 'kstl-20250315-06z')
REACHED_RISK_LEVEL = 'YELLOW'  # 教学工作流标记，不是官方雷电预警等级。


class LightningForecastSeries(BaseModel):
    model_config = ConfigDict(extra='forbid')
    unit: Literal['1']  # Dimensionless GRIB2 parameter 0/17/192, not %.
    hours: tuple[LightningForecastHour, ...]

    @field_validator('hours')
    @classmethod
    def distinct_valid_times(cls, hours: tuple[LightningForecastHour, ...]) -> tuple[LightningForecastHour, ...]:
        if len({hour.valid_at for hour in hours}) != len(hours):
            raise ValueError('duplicate lightning forecast valid time')
        return hours


class LightningStationReports(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source: CaseSource
    station_id: str = Field(pattern=r'^[A-Z][A-Z0-9]{3}$')
    observations: tuple[LightningStationReport, ...]

    @field_validator('observations')
    @classmethod
    def distinct_report_times(cls, observations: tuple[LightningStationReport, ...]) -> tuple[LightningStationReport, ...]:
        if len({row.observed_at for row in observations}) != len(observations):
            raise ValueError('duplicate station observation time')
        return observations


class LightningCase(BaseModel):
    model_config = ConfigDict(extra='forbid')
    info: LightningCaseInfo
    forecast: LightningForecastSeries


@lru_cache(maxsize=len(_CASE_IDS))
def _read_case(case_id: str) -> LightningCase:
    case = LightningCase.model_validate_json((_DATA_DIR / f'{case_id}.json').read_bytes())
    if case.info.case_id != case_id:
        raise ValueError('lightning case fixture ID mismatch')
    return case


def get_case(case_id: str) -> LightningCase:
    if case_id not in _CASE_IDS:
        raise HTTPException(404, 'NOT_FOUND')
    return _read_case(case_id)


def catalog() -> LightningCatalog:
    return LightningCatalog(cases=[get_case(case_id).info for case_id in _CASE_IDS])


def assess_forecast(info: LightningCaseInfo, series: LightningForecastSeries) -> LightningAssessment:
    """Evaluate six exact instantaneous times, never interpolating or filling from observations."""
    start = info.window_start
    ltng_at = {hour.valid_at: hour.ltng for hour in series.hours}
    times = tuple(start + i * _HOUR for i in range(1, LIGHTNING_WINDOW_HOURS + 1))
    hours = tuple(LightningForecastHour(valid_at=stamp, ltng=ltng_at.get(stamp)) for stamp in times)
    values = {hour.valid_at: hour.ltng for hour in hours if hour.ltng is not None}
    common = dict(case=info, forecast_window_end=times[-1], hours=hours, usable_hours=len(values))
    if len(values) != LIGHTNING_WINDOW_HOURS:
        return LightningAssessment(**common, outcome='INSUFFICIENT')
    hits = tuple(stamp for stamp, value in values.items() if value >= LIGHTNING_LTNG_THRESHOLD)
    metric = HazardMetric(label='6 小时最大 LTNG', unit='无量纲', value=max(values.values()),
                          threshold=LIGHTNING_LTNG_THRESHOLD, comparison='>=')
    return LightningAssessment(**common, outcome='REACHED' if hits else 'NOT_REACHED',
                               metric=metric, reached_times=hits)


def assess_case(case_id: str) -> LightningAssessment:
    case = get_case(case_id)
    return assess_forecast(case.info, case.forecast)


def _read_station_reports(case_id: str) -> LightningStationReports | None:
    try:
        content = (_DATA_DIR / f'{case_id}-station.json').read_bytes()
        return LightningStationReports.model_validate_json(content)
    except (OSError, ValidationError):
        _LOG.warning('Lightning station extract unavailable for %s', case_id)
        return None


def replay(case_id: str) -> LightningReplay:
    forecast = assess_case(case_id)
    reports = _read_station_reports(case_id)
    if reports is None or reports.station_id != forecast.case.station_id:
        return LightningReplay(forecast=forecast)
    observations = tuple(sorted(
        (row for row in reports.observations
         if forecast.case.window_start < row.observed_at <= forecast.forecast_window_end),
        key=lambda row: row.observed_at,
    ))
    if not observations:
        return LightningReplay(forecast=forecast)
    thunder = any(row.thunder_code for row in observations)
    lightning = any(row.lightning_remark for row in observations)
    outcome = {
        (True, True): 'THUNDER_AND_LIGHTNING_REPORTED', (True, False): 'THUNDER_REPORTED',
        (False, True): 'LIGHTNING_REPORTED', (False, False): 'NO_EVENT_IN_SAMPLES',
    }[(thunder, lightning)]
    reference = LightningVerification(source=reports.source, station_id=reports.station_id,
                                      observations=observations, outcome=outcome)
    return LightningReplay(forecast=forecast, verification=reference)
