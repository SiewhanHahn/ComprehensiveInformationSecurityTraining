from fastapi import APIRouter, Depends

from ..assessment_schemas import LightningCatalog, LightningReplay
from ..deps import get_current_user
from ..services import lightning

router = APIRouter(prefix='/lightning', dependencies=[Depends(get_current_user)])


@router.get('/cases', response_model=LightningCatalog)
def list_cases():
    return lightning.catalog()


@router.get('/cases/{case_id}/assessment', response_model=LightningReplay)
def assessment(case_id: str):
    return lightning.replay(case_id)
