from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ..assessment_schemas import TyphoonCatalog, TyphoonReplay
from ..deps import get_current_user
from ..services import typhoon

router = APIRouter(prefix="/typhoon", dependencies=[Depends(get_current_user)])


@router.get("/cases", response_model=TyphoonCatalog)
def list_cases():
    return typhoon.catalog()


@router.get("/cases/{case_id}/assessment", response_model=TyphoonReplay)
def assessment(case_id: str, city_code: Annotated[str, Query(min_length=1, max_length=32)]):
    return typhoon.replay(case_id, city_code)
