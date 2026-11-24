"""Offline replay: only points available at issue time can determine the outcome."""
from datetime import timedelta
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, field_validator

from ..assessment_schemas import (
    CaseCity, CaseSource, GeoPoint, HazardMetric, TrackPoint, TyphoonAssessment,
    TyphoonCaseInfo, TyphoonCatalog, TyphoonReplay, TyphoonVerification,
)
from ..cities import CITIES
from ..hazards import TYPHOON_PROXIMITY_KM

EARTH_RADIUS_KM = 6371.0
WINDOW_HOURS = 24
NEAR_RISK_LEVEL = "YELLOW"  # 教学标记，不是官方预警信号。
_CASES = {"hato-20170822": Path(__file__).resolve().parents[1] / "data/typhoon/hato-20170822.json"}
# 与既有地图标注一致的城市代表点。坐标是教学取点，不表示整个行政区。
_CITY_POINTS = {"GUANGZHOU": (23.1291, 113.2644), "HONGKONG": (22.3193, 114.1694), "SHANGHAI": (31.2304, 121.4737)}


class TyphoonCase(BaseModel):
    info: TyphoonCaseInfo
    forecast_points: tuple[TrackPoint, ...]
    verification_source: CaseSource
    verification_points: tuple[TrackPoint, ...]

    @field_validator("forecast_points", "verification_points")
    @classmethod
    def distinct_valid_times(cls, points: tuple[TrackPoint, ...]) -> tuple[TrackPoint, ...]:
        if len({point.valid_at for point in points}) != len(points):
            raise ValueError("duplicate typhoon valid time")
        return points


@lru_cache(maxsize=len(_CASES))
def _read_case(case_id: str) -> TyphoonCase:
    case = TyphoonCase.model_validate_json(_CASES[case_id].read_bytes())
    if case.info.case_id != case_id:
        raise ValueError("typhoon case fixture ID mismatch")
    return case


def get_case(case_id: str) -> TyphoonCase:
    if case_id not in _CASES:
        raise HTTPException(404, "NOT_FOUND")
    return _read_case(case_id)


def get_city(city_code: str) -> CaseCity:
    if city_code not in _CITY_POINTS:
        raise HTTPException(422, "INVALID_PARAMETER")
    lat, lon = _CITY_POINTS[city_code]
    return CaseCity(code=city_code, name=CITIES[city_code], latitude=lat, longitude=lon)


def catalog() -> TyphoonCatalog:
    return TyphoonCatalog(cases=[get_case(key).info for key in _CASES], cities=[get_city(code) for code in _CITY_POINTS])


def great_circle_km(a: GeoPoint, b: GeoPoint) -> float:
    lat_a, lat_b = radians(a.latitude), radians(b.latitude)
    half_lon = radians(b.longitude - a.longitude) / 2
    h = sin((lat_b - lat_a) / 2) ** 2 + cos(lat_a) * cos(lat_b) * sin(half_lon) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(min(1.0, max(0.0, h))))


def assess_forecast(case: TyphoonCaseInfo, points: tuple[TrackPoint, ...], city: CaseCity) -> TyphoonAssessment:
    """Closest supplied forecast point, never an interpolated or observed position."""
    window_end = case.issued_at + timedelta(hours=WINDOW_HOURS)
    candidates = tuple(sorted(
        (point for point in points if case.issued_at < point.valid_at <= window_end),
        key=lambda point: point.valid_at,
    ))
    args = dict(case=case, city=city, forecast_window_end=window_end, forecast_points=candidates)
    if not candidates:
        return TyphoonAssessment(**args, outcome="INSUFFICIENT")
    distance, closest = min(((great_circle_km(city, point), point) for point in candidates), key=lambda pair: pair[0])
    distance = round(distance, 1)
    metric = HazardMetric(label="预报点最小距离", unit="km", value=distance, threshold=TYPHOON_PROXIMITY_KM, comparison="<=")
    return TyphoonAssessment(**args, closest_point=closest, metric=metric,
                             outcome="NEAR" if distance <= metric.threshold else "NOT_NEAR")


def verify_assessment(forecast: TyphoonAssessment, case: TyphoonCase) -> TyphoonVerification | None:
    closest = forecast.closest_point
    if closest is None or forecast.metric is None:
        return None
    point = next((p for p in case.verification_points if p.valid_at == closest.valid_at), None)
    if point is None:
        return None
    distance = round(great_circle_km(forecast.city, point), 1)
    return TyphoonVerification(source=case.verification_source, point=point, distance_km=distance,
                                position_error_km=round(great_circle_km(closest, point), 1),
                                within_teaching_threshold=distance <= forecast.metric.threshold)


def assess_case(case_id: str, city_code: str) -> tuple[TyphoonCase, TyphoonAssessment]:
    case = get_case(case_id)
    return case, assess_forecast(case.info, case.forecast_points, get_city(city_code))


def replay(case_id: str, city_code: str) -> TyphoonReplay:
    case, forecast = assess_case(case_id, city_code)
    return TyphoonReplay(forecast=forecast, verification=verify_assessment(forecast, case))
