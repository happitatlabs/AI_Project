from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from mellow_link.infra import User, get_current_user, get_db
from mellow_link.services.daily_checkin import (
    DailyStateCreate,
    DailyStateNotFoundError,
    DailyStateRepository,
    DailyStateResponse,
    DailyStateService,
    DailyStateUpdate,
    DuplicateDailyStateError,
    parse_local_date,
)

router = APIRouter(prefix="/daily-states", tags=["Daily Check-in"])


def _service(db: Session) -> DailyStateService:
    return DailyStateService(DailyStateRepository(db))


def _target_date(target_date: str) -> date:
    return parse_local_date(target_date)


@router.post("", response_model=DailyStateResponse, status_code=status.HTTP_201_CREATED)
def create_daily_state(
    payload: DailyStateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _service(db).create(current_user.id, payload)
    except DuplicateDailyStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"DailyState already exists for {exc.target_date.isoformat()}",
        ) from exc


@router.get("", response_model=list[DailyStateResponse])
def list_daily_states(
    start_date_raw: str = Query(..., alias="startDate"),
    end_date_raw: str = Query(..., alias="endDate"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    start_date = parse_local_date(start_date_raw, "startDate")
    end_date = parse_local_date(end_date_raw, "endDate")
    return _service(db).list_range(current_user.id, start_date, end_date)


@router.get("/{target_date}", response_model=DailyStateResponse)
def get_daily_state(
    target_date: date = Depends(_target_date),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _service(db).get_by_date(current_user.id, target_date)
    except DailyStateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DailyState not found for {exc.target_date.isoformat()}",
        ) from exc


@router.put("/{target_date}", response_model=DailyStateResponse)
def update_daily_state(
    payload: DailyStateUpdate,
    target_date: date = Depends(_target_date),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _service(db).update(current_user.id, target_date, payload)
    except DailyStateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DailyState not found for {exc.target_date.isoformat()}",
        ) from exc
    except DuplicateDailyStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"DailyState already exists for {exc.target_date.isoformat()}",
        ) from exc
