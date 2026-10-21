from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_current_user
from ..schemas import ExperimentDetail, ExperimentListItem
from ..services import metrics

router = APIRouter()


@router.get("/metrics/experiments", response_model=list[ExperimentListItem])
def experiments(_=Depends(get_current_user)):
    return metrics.list_experiments()


@router.get("/metrics/experiments/{version}", response_model=ExperimentDetail)
def experiment(version: str, _=Depends(get_current_user)):
    detail = metrics.get_experiment(version)
    if detail is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return detail
