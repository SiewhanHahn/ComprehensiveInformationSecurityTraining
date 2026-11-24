from fastapi import APIRouter, Depends, Response

from ..deps import get_current_user
from ..services.basic_forecast import (
    ColdAssessment,
    DroughtAssessment,
    DroughtInput,
    HourlyTemperatureAssessment,
    HourlyTemperatureInput,
    WindHailAssessment,
    WindHailInput,
    assess_cold,
    assess_drought,
    assess_heat,
    assess_wind_hail,
)

router = APIRouter(prefix="/basic-forecast", dependencies=[Depends(get_current_user)])


@router.post("/drought/assessment", response_model=DroughtAssessment)
def drought_assessment(body: DroughtInput, response: Response) -> DroughtAssessment:
    response.headers["Cache-Control"] = "no-store"
    return assess_drought(body)


@router.post("/heat/assessment", response_model=HourlyTemperatureAssessment)
def heat_assessment(body: HourlyTemperatureInput, response: Response) -> HourlyTemperatureAssessment:
    response.headers["Cache-Control"] = "no-store"
    return assess_heat(body)


@router.post("/cold/assessment", response_model=ColdAssessment)
def cold_assessment(body: HourlyTemperatureInput, response: Response) -> ColdAssessment:
    response.headers["Cache-Control"] = "no-store"
    return assess_cold(body)


@router.post("/wind-hail/assessment", response_model=WindHailAssessment)
def wind_hail_assessment(body: WindHailInput, response: Response) -> WindHailAssessment:
    response.headers["Cache-Control"] = "no-store"
    return assess_wind_hail(body)
