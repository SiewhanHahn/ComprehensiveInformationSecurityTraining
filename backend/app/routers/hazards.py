from fastapi import APIRouter, Depends

from ..cities import WARNING_CITIES
from ..deps import get_current_user
from ..hazards import HAZARDS, hazard_summary
from ..schemas import CityOut

router = APIRouter()


@router.get("/warning-cities", response_model=list[CityOut])
def list_warning_cities(_=Depends(get_current_user)):
    return [CityOut(code=code, name=name) for code, name in WARNING_CITIES.items()]


@router.get("/hazards")
def list_hazards(_=Depends(get_current_user)) -> dict:
    return {"hazards": HAZARDS, "summary": hazard_summary()}
