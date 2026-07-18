from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from mellow_link.infra import User, get_current_user, get_db
from mellow_link.services.pilot_state import (
    AuditPage,
    CreatePilotRequest,
    DuplicatePilotError,
    IdempotencyKeyReusedError,
    MarkDeliveredRequest,
    PilotAccessDeniedError,
    PilotNotFoundError,
    PilotResultNotReadyError,
    PilotStateService,
    PilotStatus,
    PilotStorageError,
    PilotTransitionNotAllowedError,
    PilotVersionConflictError,
    PilotView,
    ProjectRunNotFoundError,
    QueuePage,
    RequestChangesRequest,
    TransitionPilotRequest,
)

router = APIRouter(prefix="/pilot-states", tags=["Pilot State"])
T = TypeVar("T")


def _service(db: Session) -> PilotStateService:
    return PilotStateService(db)


def _execute(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (PilotNotFoundError, ProjectRunNotFoundError) as exc:
        raise _http_error(status.HTTP_404_NOT_FOUND, exc) from exc
    except PilotAccessDeniedError as exc:
        raise _http_error(status.HTTP_403_FORBIDDEN, exc) from exc
    except (
        DuplicatePilotError,
        IdempotencyKeyReusedError,
        PilotResultNotReadyError,
        PilotTransitionNotAllowedError,
        PilotVersionConflictError,
    ) as exc:
        raise _http_error(status.HTTP_409_CONFLICT, exc) from exc
    except PilotStorageError as exc:
        raise _http_error(status.HTTP_500_INTERNAL_SERVER_ERROR, exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "pilot_validation_error", "message": str(exc)},
        ) from exc


def _http_error(status_code: int, exc: Exception) -> HTTPException:
    detail: dict[str, object] = {
        "code": getattr(exc, "code", "pilot_error"),
        "message": str(exc),
    }
    current_status = getattr(exc, "current_status", None)
    current_version = getattr(exc, "current_version", None)
    if current_status is not None:
        detail["current_status"] = current_status
    if current_version is not None:
        detail["current_version"] = current_version
    return HTTPException(status_code=status_code, detail=detail)


@router.get("/queue/pending", response_model=QueuePage)
def get_pending_queue(
    reviewer_id: int | None = Query(default=None, ge=1),
    project_id: str | None = Query(default=None, min_length=1, max_length=40),
    cursor: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(
        lambda: _service(db).list_queue(
            current_user,
            statuses=[PilotStatus.READY_FOR_REVIEW, PilotStatus.UNDER_REVIEW],
            reviewer_id=reviewer_id,
            project_id=project_id,
            cursor=cursor,
            limit=limit,
        )
    )


@router.get("/queue/delivered", response_model=QueuePage)
def get_delivered_queue(
    project_id: str | None = Query(default=None, min_length=1, max_length=40),
    cursor: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(
        lambda: _service(db).list_queue(
            current_user,
            statuses=[PilotStatus.DELIVERED],
            project_id=project_id,
            cursor=cursor,
            limit=limit,
        )
    )


@router.get("/queue", response_model=QueuePage)
def list_pilot_queue(
    statuses: list[PilotStatus] | None = Query(default=None, alias="status"),
    reviewer_id: int | None = Query(default=None, ge=1),
    project_id: str | None = Query(default=None, min_length=1, max_length=40),
    cursor: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(
        lambda: _service(db).list_queue(
            current_user,
            statuses=statuses,
            reviewer_id=reviewer_id,
            project_id=project_id,
            cursor=cursor,
            limit=limit,
        )
    )


@router.post("", response_model=PilotView, status_code=status.HTTP_201_CREATED)
def create_pilot(
    payload: CreatePilotRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(lambda: _service(db).create(current_user, payload))


@router.get("/{pilot_id}/audit", response_model=AuditPage)
def get_audit_history(
    pilot_id: str,
    cursor: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(
        lambda: _service(db).get_audit_history(
            current_user, pilot_id, cursor=cursor, limit=limit
        )
    )


@router.get("/{pilot_id}", response_model=PilotView)
def get_pilot(
    pilot_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(lambda: _service(db).get(current_user, pilot_id))


@router.post("/{pilot_id}/submit", response_model=PilotView)
def submit_for_review(
    pilot_id: str,
    payload: TransitionPilotRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(lambda: _service(db).submit(current_user, pilot_id, payload))


@router.post("/{pilot_id}/start-review", response_model=PilotView)
def start_review(
    pilot_id: str,
    payload: TransitionPilotRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(lambda: _service(db).start_review(current_user, pilot_id, payload))


@router.post("/{pilot_id}/approve", response_model=PilotView)
def approve_pilot(
    pilot_id: str,
    payload: TransitionPilotRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(lambda: _service(db).approve(current_user, pilot_id, payload))


@router.post("/{pilot_id}/request-changes", response_model=PilotView)
def request_changes(
    pilot_id: str,
    payload: RequestChangesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(
        lambda: _service(db).request_changes(current_user, pilot_id, payload)
    )


@router.post("/{pilot_id}/resubmit", response_model=PilotView)
def resubmit_pilot(
    pilot_id: str,
    payload: TransitionPilotRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(lambda: _service(db).resubmit(current_user, pilot_id, payload))


@router.post("/{pilot_id}/deliver", response_model=PilotView)
def mark_delivered(
    pilot_id: str,
    payload: MarkDeliveredRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(
        lambda: _service(db).mark_delivered(current_user, pilot_id, payload)
    )
