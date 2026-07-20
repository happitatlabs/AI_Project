from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from mellow_link.infra import User, get_current_user, get_db
from mellow_link.services.delivery_package import (
    AssemblyAlreadyExistsError,
    AssemblyView,
    ChecklistItemView,
    ChecklistView,
    DeliveryAccessDeniedError,
    DeliveryAuditPage,
    DeliveryIdempotencyConflictError,
    DeliveryNotFoundError,
    DeliveryPackageService,
    DeliveryStateConflictError,
    DeliveryStorageError,
    DeliveryValidationError,
    DeliveryVersionConflictError,
    DownloadReferenceView,
    IdempotentRequest,
    InvalidArtifactError,
    ManifestView,
    PackageIntegrityError,
    PackagePage,
    ReadinessBlockedError,
    ReadinessStaleError,
    ReadinessView,
    RequestAssemblyRequest,
    RetryAssemblyRequest,
    VersionedChecklistRequest,
    WaiveChecklistItemRequest,
)

router = APIRouter(prefix="/pilot-delivery", tags=["Pilot Delivery"])
T = TypeVar("T")


def _service(db: Session) -> DeliveryPackageService:
    return DeliveryPackageService(db)


def _execute(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except DeliveryNotFoundError as exc:
        raise _http_error(status.HTTP_404_NOT_FOUND, exc) from exc
    except DeliveryAccessDeniedError as exc:
        raise _http_error(status.HTTP_403_FORBIDDEN, exc) from exc
    except (
        AssemblyAlreadyExistsError,
        DeliveryIdempotencyConflictError,
        DeliveryStateConflictError,
        DeliveryVersionConflictError,
        PackageIntegrityError,
        ReadinessBlockedError,
        ReadinessStaleError,
    ) as exc:
        raise _http_error(status.HTTP_409_CONFLICT, exc) from exc
    except (DeliveryValidationError, InvalidArtifactError) as exc:
        raise _http_error(status.HTTP_422_UNPROCESSABLE_ENTITY, exc) from exc
    except DeliveryStorageError as exc:
        raise _http_error(status.HTTP_500_INTERNAL_SERVER_ERROR, exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "delivery_validation_error", "message": str(exc)},
        ) from exc


def _http_error(status_code: int, exc: Exception) -> HTTPException:
    detail: dict[str, object] = {
        "code": getattr(exc, "code", "delivery_error"),
        "message": str(exc),
    }
    current_version = getattr(exc, "current_version", None)
    if current_version is not None:
        detail["current_version"] = current_version
    return HTTPException(status_code=status_code, detail=detail)


@router.post(
    "/pilots/{pilot_id}/checklist",
    response_model=ChecklistView,
    status_code=status.HTTP_201_CREATED,
)
def create_checklist(
    pilot_id: str,
    payload: IdempotentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(
        lambda: _service(db).create_checklist(current_user, pilot_id, payload)
    )


@router.get("/pilots/{pilot_id}/checklist", response_model=ChecklistView)
def get_checklist(
    pilot_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(lambda: _service(db).get_checklist(current_user, pilot_id))


@router.get(
    "/pilots/{pilot_id}/checklist/items/{item_key}",
    response_model=ChecklistItemView,
)
def get_checklist_item(
    pilot_id: str,
    item_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(lambda: _service(db).get_item(current_user, pilot_id, item_key))


@router.post(
    "/pilots/{pilot_id}/checklist/items/{item_key}/verify",
    response_model=ChecklistView,
)
def verify_checklist_item(
    pilot_id: str,
    item_key: str,
    payload: VersionedChecklistRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(
        lambda: _service(db).verify_item(current_user, pilot_id, item_key, payload)
    )


@router.post(
    "/pilots/{pilot_id}/checklist/items/{item_key}/waive",
    response_model=ChecklistView,
)
def waive_checklist_item(
    pilot_id: str,
    item_key: str,
    payload: WaiveChecklistItemRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(
        lambda: _service(db).waive_item(current_user, pilot_id, item_key, payload)
    )


@router.get("/pilots/{pilot_id}/readiness", response_model=ReadinessView)
def get_readiness(
    pilot_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(lambda: _service(db).get_readiness(current_user, pilot_id))


@router.post("/pilots/{pilot_id}/assemblies", response_model=AssemblyView)
def request_assembly(
    pilot_id: str,
    payload: RequestAssemblyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(
        lambda: _service(db).request_assembly(current_user, pilot_id, payload)
    )


@router.get("/assemblies/{assembly_id}", response_model=AssemblyView)
def get_assembly(
    assembly_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(lambda: _service(db).get_assembly(current_user, assembly_id))


@router.post("/assemblies/{assembly_id}/retry", response_model=AssemblyView)
def retry_assembly(
    assembly_id: str,
    payload: RetryAssemblyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(
        lambda: _service(db).retry_assembly(current_user, assembly_id, payload)
    )


@router.get("/pilots/{pilot_id}/packages", response_model=PackagePage)
def list_packages(
    pilot_id: str,
    cursor: str | None = Query(default=None, max_length=500),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(
        lambda: _service(db).list_packages(
            current_user, pilot_id, cursor=cursor, limit=limit
        )
    )


@router.get("/packages/{package_id}/manifest", response_model=ManifestView)
def get_manifest(
    package_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(lambda: _service(db).get_manifest(current_user, package_id))


@router.post(
    "/packages/{package_id}/download-references",
    response_model=DownloadReferenceView,
)
def create_download_reference(
    package_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(
        lambda: _service(db).create_download_reference(current_user, package_id)
    )


@router.get("/downloads/{token}")
def download_package(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolved = _execute(
        lambda: _service(db).redeem_download_reference(current_user, token)
    )
    return FileResponse(
        path=resolved.path,
        media_type=resolved.content_type,
        filename=resolved.filename,
    )


@router.get("/pilots/{pilot_id}/audit", response_model=DeliveryAuditPage)
def get_audit_history(
    pilot_id: str,
    cursor: str | None = Query(default=None, max_length=500),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _execute(
        lambda: _service(db).get_audit_history(
            current_user, pilot_id, cursor=cursor, limit=limit
        )
    )
