from fastapi import APIRouter, Depends, Response

from ..deps import get_current_user
from ..services.basic_forecast import (
    ColdAssessment,
    DroughtAssessment,
    DroughtInput,
    HeatAssessment,
    HourlyTemperatureInput,
    assess_cold,
    assess_drought,
    assess_heat,
)

router = APIRouter(prefix="/basic-forecast", dependencies=[Depends(get_current_user)])


@router.post("/drought/assessment", response_model=DroughtAssessment)
def drought_assessment(body: DroughtInput, response: Response) -> DroughtAssessment:
    response.headers["Cache-Control"] = "no-store"
    return assess_drought(body)


@router.post("/heat/assessment", response_model=HeatAssessment)
def heat_assessment(body: HourlyTemperatureInput, response: Response) -> HeatAssessment:
    response.headers["Cache-Control"] = "no-store"
    return assess_heat(body)


@router.post("/cold/assessment", response_model=ColdAssessment)
def cold_assessment(body: HourlyTemperatureInput, response: Response) -> ColdAssessment:
    response.headers["Cache-Control"] = "no-store"
    return assess_cold(body)
