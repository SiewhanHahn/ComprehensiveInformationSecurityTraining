"""Deterministic teaching forecasts with caller-provided inputs, no persistence."""
import re
from datetime import date, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from ..hazards import DROUGHT_DRY_DAY_BELOW_MM, DROUGHT_STREAK_THRESHOLD_DAYS

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
