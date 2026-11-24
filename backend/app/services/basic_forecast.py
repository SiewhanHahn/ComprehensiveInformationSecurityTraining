"""Deterministic teaching forecasts with caller-provided inputs, no persistence."""
import re
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal, TypeVar

from pydantic import (
    AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, StringConstraints, field_validator,
)

from ..hazards import (
    COLD_THRESHOLD_C, DROUGHT_DRY_DAY_BELOW_MM, DROUGHT_STREAK_THRESHOLD_DAYS, HEAT_THRESHOLD_C, WIND_GUST_THRESHOLD_MPS,
)

DROUGHT_FORECAST_DAYS = 7
RainMm = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
DryDays = Annotated[int, Field(strict=True, ge=0, le=3650)]
Location = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class DroughtInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location: Location
    start_date: date = Field(le=date.max - timedelta(days=DROUGHT_FORECAST_DAYS - 1))
    antecedent_dry_days: DryDays | None
    daily_rain_mm: tuple[RainMm | None, ...] = Field(min_length=DROUGHT_FORECAST_DAYS, max_length=DROUGHT_FORECAST_DAYS)

    @field_validator("start_date", mode="before")
    @classmethod
    def require_calendar_date(cls, value):
        if type(value) is date or (isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)):
            return value
        raise ValueError("start_date must be a UTC calendar date (YYYY-MM-DD)")


class DroughtDay(BaseModel):
    valid_date: date
    rain_mm: float | None
    dry_days: int | None


class DroughtAssessment(BaseModel):
    hazard_type: Literal["DROUGHT"] = "DROUGHT"
    method: Literal["daily-dry-streak-v1"] = "daily-dry-streak-v1"
    location: str
    start_date: date
    end_date: date  # Inclusive UTC date of the seventh forecast day.
    antecedent_dry_days: int | None
    usable_days: int
    dry_day_below_mm: float = DROUGHT_DRY_DAY_BELOW_MM
    continuation_at_least_days: int = DROUGHT_STREAK_THRESHOLD_DAYS
    end_dry_days: int | None
    outcome: Literal["INSUFFICIENT", "REACHED", "NOT_REACHED"]
    days: list[DroughtDay]


def assess_drought(body: DroughtInput) -> DroughtAssessment:
    """The window-end dry streak, not a soil-moisture index or an official warning."""
    available = sum(value is not None for value in body.daily_rain_mm)
    streak = body.antecedent_dry_days if available == DROUGHT_FORECAST_DAYS else None
    days = []
    for offset, rain_mm in enumerate(body.daily_rain_mm):
        if streak is not None and rain_mm is not None:
            streak = streak + 1 if rain_mm < DROUGHT_DRY_DAY_BELOW_MM else 0
        days.append(DroughtDay(valid_date=body.start_date + timedelta(days=offset), rain_mm=rain_mm, dry_days=streak))
    outcome = "INSUFFICIENT" if streak is None else "REACHED" if streak >= DROUGHT_STREAK_THRESHOLD_DAYS else "NOT_REACHED"
    return DroughtAssessment(location=body.location, start_date=body.start_date, end_date=days[-1].valid_date,
                             antecedent_dry_days=body.antecedent_dry_days, usable_days=available, days=days,
                             end_dry_days=streak, outcome=outcome)


TEMPERATURE_FORECAST_HOURS = 24
WIND_HAIL_FORECAST_HOURS = 6
ForecastOutcome = Literal["INSUFFICIENT", "REACHED", "NOT_REACHED"]
TemperatureC = Annotated[float, Field(strict=True, allow_inf_nan=False)]


def require_utc_hour(value):
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:00:00(?:Z|\+00:00)", value):
        return value
    raise ValueError("start_at must be a whole UTC hour (YYYY-MM-DDTHH:00:00Z)")


UTCHour = Annotated[AwareDatetime, BeforeValidator(require_utc_hour)]


def latest_utc_start(hours: int) -> datetime:
    return datetime.max.replace(tzinfo=UTC) - timedelta(hours=hours - 1)


def window_outcome(complete: bool, qualifying: list[datetime]) -> ForecastOutcome:
    return "INSUFFICIENT" if not complete else "REACHED" if qualifying else "NOT_REACHED"


class HourlyTemperatureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location: Location
    start_at: UTCHour = Field(le=latest_utc_start(TEMPERATURE_FORECAST_HOURS))
    hourly_temperature_c: tuple[TemperatureC | None, ...] = Field(
        min_length=TEMPERATURE_FORECAST_HOURS, max_length=TEMPERATURE_FORECAST_HOURS,
    )


class TemperatureAssessmentFields(BaseModel):
    location: str
    start_at: datetime
    end_at: datetime  # Inclusive UTC time of the last forecast hour.
    usable_hours: int
    threshold_c: float
    extreme_c: float | None
    outcome: ForecastOutcome
    qualifying_hours: list[datetime]


class HourlyTemperatureAssessment(TemperatureAssessmentFields):
    hazard_type: Literal["HEATWAVE"] = "HEATWAVE"
    method: Literal["hourly-heat-threshold-v1"] = "hourly-heat-threshold-v1"
    threshold_c: float = HEAT_THRESHOLD_C


class ColdAssessment(TemperatureAssessmentFields):
    hazard_type: Literal["LOW_TEMPERATURE"] = "LOW_TEMPERATURE"
    method: Literal["hourly-cold-threshold-v1"] = "hourly-cold-threshold-v1"
    threshold_c: float = COLD_THRESHOLD_C


TemperatureAssessment = TypeVar("TemperatureAssessment", bound=TemperatureAssessmentFields)


def _assess_temperature(
    body: HourlyTemperatureInput,
    assessment: type[TemperatureAssessment],
    extreme: Callable[[Iterable[float]], float],
    qualifies: Callable[[float], bool],
) -> TemperatureAssessment:
    readings = [(i, value) for i, value in enumerate(body.hourly_temperature_c) if value is not None]
    complete = len(readings) == TEMPERATURE_FORECAST_HOURS
    qualifying = [body.start_at + timedelta(hours=i) for i, value in readings if qualifies(value)] if complete else []
    return assessment(
        location=body.location,
        start_at=body.start_at,
        end_at=body.start_at + timedelta(hours=TEMPERATURE_FORECAST_HOURS - 1),
        usable_hours=len(readings),
        extreme_c=extreme(value for _, value in readings) if complete else None,
        outcome=window_outcome(complete, qualifying),
        qualifying_hours=qualifying,
    )


def assess_heat(body: HourlyTemperatureInput) -> HourlyTemperatureAssessment:
    """Compute the maximum and all hours at or above the heat teaching line."""
    return _assess_temperature(body, HourlyTemperatureAssessment, max, lambda value: value >= HEAT_THRESHOLD_C)


def assess_cold(body: HourlyTemperatureInput) -> ColdAssessment:
    """Compute the minimum and all hours at or below the cold teaching line (not a cold-wave forecast)."""
    return _assess_temperature(body, ColdAssessment, min, lambda value: value <= COLD_THRESHOLD_C)


GustMps = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


class WindHailInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location: Location
    start_at: UTCHour = Field(le=latest_utc_start(WIND_HAIL_FORECAST_HOURS))
    hourly_gust_mps: tuple[GustMps | None, ...] = Field(
        min_length=WIND_HAIL_FORECAST_HOURS, max_length=WIND_HAIL_FORECAST_HOURS,
    )
    hourly_hail_signal: tuple[StrictBool | None, ...] = Field(
        min_length=WIND_HAIL_FORECAST_HOURS, max_length=WIND_HAIL_FORECAST_HOURS,
    )


class WindHailComponentAssessment(BaseModel):
    usable_hours: int
    outcome: ForecastOutcome
    qualifying_hours: list[datetime]


class GustAssessment(WindHailComponentAssessment):
    threshold_mps: float = WIND_GUST_THRESHOLD_MPS
    max_gust_mps: float | None


class WindHailAssessment(BaseModel):
    hazard_type: Literal["WIND_HAIL"] = "WIND_HAIL"
    method: Literal["hourly-gust-and-hail-v1"] = "hourly-gust-and-hail-v1"
    location: str
    start_at: datetime
    end_at: datetime
    gust: GustAssessment
    hail: WindHailComponentAssessment


def assess_wind_hail(body: WindHailInput) -> WindHailAssessment:
    """Each six-hour series must be complete to judge that component independently."""
    gusts = [(i, value) for i, value in enumerate(body.hourly_gust_mps) if value is not None]
    gust_complete = len(gusts) == WIND_HAIL_FORECAST_HOURS
    gust_hours = [body.start_at + timedelta(hours=i) for i, value in gusts if value >= WIND_GUST_THRESHOLD_MPS] if gust_complete else []
    hail_available = sum(signal is not None for signal in body.hourly_hail_signal)
    hail_complete = hail_available == WIND_HAIL_FORECAST_HOURS
    hail_hours = [body.start_at + timedelta(hours=i) for i, signal in enumerate(body.hourly_hail_signal) if signal is True] if hail_complete else []
    return WindHailAssessment(
        location=body.location,
        start_at=body.start_at,
        end_at=body.start_at + timedelta(hours=WIND_HAIL_FORECAST_HOURS - 1),
        gust=GustAssessment(usable_hours=len(gusts), outcome=window_outcome(gust_complete, gust_hours),
                            qualifying_hours=gust_hours, max_gust_mps=max(value for _, value in gusts) if gust_complete else None),
        hail=WindHailComponentAssessment(usable_hours=hail_available, outcome=window_outcome(hail_complete, hail_hours),
                                         qualifying_hours=hail_hours),
    )
