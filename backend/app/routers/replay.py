from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..cities import CITIES
from ..db import get_db
from ..deps import get_current_user
from ..schemas import CityOut, ReplayOut
from ..services.replay import compute_replay

router = APIRouter()


@router.get("/cities", response_model=list[CityOut])
def cities(_=Depends(get_current_user)):
    return [CityOut(code=code, name=name) for code, name in CITIES.items()]


@router.get("/replay", response_model=ReplayOut)
def replay(
    city_code: str,
    date: date,
    threshold_code: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    result = compute_replay(db, city_code, date, threshold_code)
    if result is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return ReplayOut(**result)
