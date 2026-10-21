from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..hazards import HAZARDS, hazard_summary

router = APIRouter()


@router.get("/hazards")
def list_hazards(_=Depends(get_current_user)) -> dict:
    return {"hazards": HAZARDS, "summary": hazard_summary()}
