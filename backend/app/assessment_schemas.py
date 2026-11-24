"""Typed outputs for provenance-backed hazard assessments (not rainfall quantities)."""
from datetime import date, timedelta
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class CaseSource(BaseModel):
    agency: str
    product: str
    url: str
    checked_on_utc: date


class GeoPoint(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class CaseCity(GeoPoint):
    code: str
    name: str


class TrackPoint(GeoPoint):
    valid_at: AwareDatetime


class HazardMetric(BaseModel):
    label: str
    value: float
    unit: str
    threshold: float
    comparison: Literal["<=", ">="]


class TyphoonCaseInfo(BaseModel):
    case_id: str
    name: str
    storm_number: str
    issued_at: AwareDatetime
    forecast_source: CaseSource


class TyphoonCatalog(BaseModel):
    cases: list[TyphoonCaseInfo]
    cities: list[CaseCity]


class TyphoonAssessment(BaseModel):
    schema_version: Literal[1] = 1
    method: Literal["track-point-distance-v1"] = "track-point-distance-v1"
    case: TyphoonCaseInfo
    city: CaseCity
    forecast_window_end: AwareDatetime
    forecast_points: tuple[TrackPoint, ...]
    closest_point: TrackPoint | None = None
    outcome: Literal["INSUFFICIENT", "NEAR", "NOT_NEAR"]
    metric: HazardMetric | None = None


class TyphoonVerification(BaseModel):
    source: CaseSource
    point: TrackPoint
    distance_km: float
    position_error_km: float
    within_teaching_threshold: bool


class TyphoonReplay(BaseModel):
    forecast: TyphoonAssessment
    verification: TyphoonVerification | None = None


class SnowCaseInfo(BaseModel):
    case_id: str
    name: str
    city: CaseCity
    forecast_grid: GeoPoint
    initialized_at: AwareDatetime
    window_start: AwareDatetime
    forecast_source: CaseSource

    @model_validator(mode="after")
    def validate_window_start(self) -> "SnowCaseInfo":
        start = self.window_start
        if (start.utcoffset() != timedelta(0) or self.initialized_at.utcoffset() != timedelta(0)
                or start.minute or start.second or start.microsecond
                or start != self.initialized_at + timedelta(hours=12)):
            raise ValueError("snow window must begin on a UTC hour, 12h after model initialization")
        return self


class SnowForecastHour(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valid_at: AwareDatetime  # Hour ending; temperature is instantaneous at this time.
    snowfall_cm: float | None = Field(ge=0, strict=True, allow_inf_nan=False)
    temperature_c: float | None = Field(strict=True, allow_inf_nan=False)


class SnowAssessment(BaseModel):
    schema_version: Literal[1] = 1
    method: Literal["hourly-snowfall-sum-v1"] = "hourly-snowfall-sum-v1"
    case: SnowCaseInfo
    forecast_window_end: AwareDatetime
    usable_hours: int = Field(ge=0, le=24)
    hours: tuple[SnowForecastHour, ...]
    outcome: Literal["INSUFFICIENT", "REACHED", "NOT_REACHED"]
    metric: HazardMetric | None = None
    min_temperature_c: float | None = None
    snow_period_start: AwareDatetime | None = None
    snow_period_end: AwareDatetime | None = None


class SnowStationReport(BaseModel):
    observed_at: AwareDatetime
    code: Literal["00", "60", "70", "74"]
    quality: Literal["1"]


class SnowVerification(BaseModel):
    source: CaseSource
    station_id: str
    observations: tuple[SnowStationReport, ...]
    outcome: Literal["SNOW_REPORTED", "NO_SNOW_IN_SAMPLES"]


class SnowCatalog(BaseModel):
    cases: list[SnowCaseInfo]


class SnowReplay(BaseModel):
    forecast: SnowAssessment
    verification: SnowVerification | None = None
