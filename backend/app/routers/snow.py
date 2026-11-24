from fastapi import APIRouter, Depends

from ..assessment_schemas import SnowCatalog, SnowReplay
from ..deps import get_current_user
from ..services import snow

router = APIRouter(prefix="/snow", dependencies=[Depends(get_current_user)])


@router.get("/cases", response_model=SnowCatalog)
def list_cases():
    return snow.catalog()


@router.get("/cases/{case_id}/assessment", response_model=SnowReplay)
def assessment(case_id: str):
    return snow.replay(case_id)
