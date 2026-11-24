"""Typed outputs for provenance-backed hazard assessments (not rainfall quantities)."""
from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field


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
