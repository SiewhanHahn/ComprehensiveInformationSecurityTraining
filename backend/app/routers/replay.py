import json
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..cities import CITIES
from ..db import get_db
from ..deps import CurrentUser, get_current_user, require_roles
from ..schemas import CityOut, ReplayOut
from ..services.audit import audit_context
from ..services.replay import compute_replay, get_threshold
from ..services.trial import TrialError, calculate_trial
from ..errors import error_response

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
    return ReplayOut(
        replay_id=result["replay_id"],
        city=result["city"],
        valid_date=result["valid_date"],
        threshold=result["threshold"],
        models=result["models"],
        fused_mm=result["fused_mm"],
        baseline_mm=result["baseline_mm"],
        proxy_label_mm=result["proxy_label_mm"],
        risk_level=result["risk_level"],
        data_status=result["data_status"],
        source=result["source"],
    )


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise HTTPException(422, 'TRIAL_DUPLICATE_FIELD')
        result[key] = value
    return result


async def read_trial_file(request: Request):
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > 256 * 1024:
            raise HTTPException(413, 'TRIAL_TOO_LARGE')
        data.extend(chunk)
    try:
        return json.loads(data.decode('utf-8-sig'), parse_float=Decimal, object_pairs_hook=_unique_fields)
    except (ValueError, RecursionError, ArithmeticError):
        raise HTTPException(422, 'TRIAL_INVALID_JSON') from None


@router.post('/replay/trial')
def trial(
    request: Request,
    response: Response,
    threshold_code: str,
    current: CurrentUser = Depends(require_roles('ANALYST', 'ADMIN')),
    dataset=Depends(read_trial_file),
    db: Session = Depends(get_db),
):
    threshold = get_threshold(db, threshold_code)
    if threshold is None:
        raise HTTPException(404, 'NOT_FOUND')
    try:
        rows = calculate_trial(dataset, threshold.threshold_mm)
    except TrialError as exc:
        return error_response(request, 422, 'VALIDATION_ERROR', message=str(exc))
    audit_context(request, db, current).record('REPLAY_TRIAL', resource_type='replay',
                                              reason=f'threshold={threshold.code}; rows={len(rows)}')
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return {'threshold_mm': float(threshold.threshold_mm), 'rows': rows}
