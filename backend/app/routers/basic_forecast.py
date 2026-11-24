from fastapi import APIRouter, Depends, Response

from ..deps import get_current_user
from ..services.basic_forecast import DroughtAssessment, DroughtInput, assess_drought

router = APIRouter(prefix="/basic-forecast", dependencies=[Depends(get_current_user)])


@router.post("/drought/assessment", response_model=DroughtAssessment)
def drought_assessment(body: DroughtInput, response: Response) -> DroughtAssessment:
    response.headers["Cache-Control"] = "no-store"
    return assess_drought(body)
