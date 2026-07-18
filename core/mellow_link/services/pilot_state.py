from __future__ import annotations

import base64
import binascii
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from mellow_link.infra.database import (
    AgentRun,
    ModernizationProject,
    PilotAuditEvent,
    PilotCommandResult,
    PilotStateRecord,
    ProjectRunHistory,
    User,
    UserRole,
)
from mellow_link.services.project_results.archive import (
    build_project_result_archive_paths,
)

IDEMPOTENCY_KEY_MAX_LENGTH = 200
CHANGE_REQUEST_REASON_MAX_LENGTH = 2000
DELIVERY_REFERENCE_MAX_LENGTH = 500
QUEUE_PAGE_MAX_SIZE = 100


class PilotStatus(str, Enum):
    DRAFT = "draft"
    READY_FOR_REVIEW = "ready_for_review"
    UNDER_REVIEW = "under_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    DELIVERED = "delivered"


class PilotEvent(str, Enum):
    SUBMIT = "submit"
    START_REVIEW = "start_review"
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    RESUBMIT = "resubmit"
    DELIVER = "deliver"


@dataclass(frozen=True)
class TransitionSpec:
    from_status: PilotStatus
    to_status: PilotStatus
    audit_event: str


TRANSITIONS: dict[PilotEvent, TransitionSpec] = {
    PilotEvent.SUBMIT: TransitionSpec(
        PilotStatus.DRAFT, PilotStatus.READY_FOR_REVIEW, "pilot_submitted"
    ),
    PilotEvent.START_REVIEW: TransitionSpec(
        PilotStatus.READY_FOR_REVIEW,
        PilotStatus.UNDER_REVIEW,
        "pilot_review_started",
    ),
    PilotEvent.APPROVE: TransitionSpec(
        PilotStatus.UNDER_REVIEW, PilotStatus.APPROVED, "pilot_approved"
    ),
    PilotEvent.REQUEST_CHANGES: TransitionSpec(
        PilotStatus.UNDER_REVIEW,
        PilotStatus.CHANGES_REQUESTED,
        "pilot_changes_requested",
    ),
    PilotEvent.RESUBMIT: TransitionSpec(
        PilotStatus.CHANGES_REQUESTED,
        PilotStatus.READY_FOR_REVIEW,
        "pilot_resubmitted",
    ),
    PilotEvent.DELIVER: TransitionSpec(
        PilotStatus.APPROVED, PilotStatus.DELIVERED, "pilot_delivered"
    ),
}


class CreatePilotRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=40)
    run_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=IDEMPOTENCY_KEY_MAX_LENGTH)

    model_config = ConfigDict(extra="forbid")

    @field_validator("project_id", "run_id", "idempotency_key")
    @classmethod
    def reject_ambiguous_identifiers(cls, value: str) -> str:
        if value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError(
                "identifier must not contain surrounding whitespace or control characters"
            )
        return value


class TransitionPilotRequest(BaseModel):
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=IDEMPOTENCY_KEY_MAX_LENGTH)

    model_config = ConfigDict(extra="forbid")

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, value: str) -> str:
        if value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError(
                "idempotency_key must not contain surrounding whitespace or control characters"
            )
        return value


class RequestChangesRequest(TransitionPilotRequest):
    reason: str = Field(min_length=1, max_length=CHANGE_REQUEST_REASON_MAX_LENGTH)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        if any(ord(char) < 32 for char in value):
            raise ValueError("reason must not contain control characters")
        return value


class MarkDeliveredRequest(TransitionPilotRequest):
    delivery_reference: str | None = Field(
        default=None, max_length=DELIVERY_REFERENCE_MAX_LENGTH
    )

    @field_validator("delivery_reference")
    @classmethod
    def validate_delivery_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError(
                "delivery_reference must be non-blank and contain no control characters"
            )
        return value


class PilotView(BaseModel):
    pilot_id: str
    project_id: str
    run_id: str
    status: PilotStatus
    version: int
    created_at: datetime
    updated_at: datetime
    review_requested_at: datetime | None = None
    reviewer_id: int | None = None
    review_started_at: datetime | None = None
    approved_by_id: int | None = None
    approved_at: datetime | None = None
    delivered_by_id: int | None = None
    delivered_at: datetime | None = None
    change_request_reason: str | None = None
    delivery_reference: str | None = None


class QueueItem(BaseModel):
    pilot_id: str
    project_ref: str
    project_display_name: str
    run_ref: str
    status: PilotStatus
    version: int
    created_at: datetime
    updated_at: datetime
    review_requested_at: datetime | None = None
    reviewer_display: str | None = None
    review_started_at: datetime | None = None
    approved_at: datetime | None = None
    delivered_at: datetime | None = None
    docx_available: bool


class QueuePage(BaseModel):
    items: list[QueueItem]
    next_cursor: str | None = None


class AuditEventView(BaseModel):
    event_id: str
    event_type: str
    from_status: PilotStatus | None
    to_status: PilotStatus
    actor_ref: str
    occurred_at: datetime
    reason: str | None = None
    result_version: int


class AuditPage(BaseModel):
    items: list[AuditEventView]
    next_cursor: str | None = None


class PilotError(Exception):
    code = "pilot_error"


class PilotNotFoundError(PilotError):
    code = "pilot_not_found"


class ProjectRunNotFoundError(PilotError):
    code = "project_run_not_found"


class PilotAccessDeniedError(PilotError):
    code = "pilot_access_denied"


class DuplicatePilotError(PilotError):
    code = "pilot_already_exists"


class PilotTransitionNotAllowedError(PilotError):
    code = "pilot_transition_not_allowed"

    def __init__(self, status: str, version: int):
        super().__init__(f"Pilot transition is not allowed from {status}")
        self.current_status = status
        self.current_version = version


class PilotVersionConflictError(PilotError):
    code = "pilot_version_conflict"

    def __init__(self, status: str, version: int):
        super().__init__("Pilot version does not match expected_version")
        self.current_status = status
        self.current_version = version


class IdempotencyKeyReusedError(PilotError):
    code = "idempotency_key_reused"


class PilotResultNotReadyError(PilotError):
    code = "pilot_result_not_ready"


class PilotStorageError(PilotError):
    code = "pilot_storage_error"


def resolve_transition(status: PilotStatus, event: PilotEvent) -> TransitionSpec:
    spec = TRANSITIONS[event]
    if status != spec.from_status:
        raise PilotTransitionNotAllowedError(status.value, -1)
    return spec


class PilotStateService:
    def __init__(
        self,
        db: Session,
        *,
        archive_root: Path | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.db = db
        self.archive_root = archive_root or (
            Path(__file__).resolve().parents[3]
            / "data"
            / "outputs"
            / "final"
            / "project_results"
        )
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def create(self, actor: User, payload: CreatePilotRequest) -> PilotView:
        project = self._get_project_for_run(payload.project_id, payload.run_id)
        self._require_project_access(actor, project)
        request_hash = _request_hash(
            "create",
            {
                "project_id": payload.project_id,
                "run_id": payload.run_id,
                "idempotency_key": payload.idempotency_key,
            },
        )
        replay = self._load_replay(
            actor.id, payload.idempotency_key, "create", request_hash
        )
        if replay is not None:
            return replay

        now = self._now()
        pilot = PilotStateRecord(
            pilot_id=uuid.uuid4().hex,
            project_id=payload.project_id,
            run_id=payload.run_id,
            status=PilotStatus.DRAFT.value,
            version=0,
            created_at=now,
            updated_at=now,
            created_by_id=actor.id,
        )
        event = self._audit_event(
            pilot=pilot,
            event_type="pilot_created",
            from_status=None,
            to_status=PilotStatus.DRAFT,
            actor=actor,
            idempotency_key=payload.idempotency_key,
            result_version=0,
            occurred_at=now,
        )
        pilot.last_transition_id = event.event_id
        self.db.add(pilot)
        try:
            self.db.flush()
            self.db.add(event)
            self.db.flush()
            response = _pilot_view(pilot)
            self._store_result(
                actor_id=actor.id,
                idempotency_key=payload.idempotency_key,
                operation="create",
                request_hash=request_hash,
                response=response,
                created_at=now,
            )
            self.db.commit()
            return response
        except IntegrityError as exc:
            self.db.rollback()
            replay = self._load_replay(
                actor.id, payload.idempotency_key, "create", request_hash
            )
            if replay is not None:
                return replay
            if self._find_by_project_run(payload.project_id, payload.run_id):
                raise DuplicatePilotError(
                    "Pilot already exists for project/run"
                ) from exc
            raise PilotStorageError("Pilot could not be created") from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise PilotStorageError("Pilot could not be created") from exc

    def get(self, actor: User, pilot_id: str) -> PilotView:
        pilot = self._get_pilot(pilot_id)
        project = self._get_project(pilot.project_id)
        self._require_project_access(actor, project)
        return _pilot_view(pilot)

    def submit(
        self, actor: User, pilot_id: str, payload: TransitionPilotRequest
    ) -> PilotView:
        return self._transition(actor, pilot_id, PilotEvent.SUBMIT, payload)

    def start_review(
        self, actor: User, pilot_id: str, payload: TransitionPilotRequest
    ) -> PilotView:
        return self._transition(actor, pilot_id, PilotEvent.START_REVIEW, payload)

    def approve(
        self, actor: User, pilot_id: str, payload: TransitionPilotRequest
    ) -> PilotView:
        return self._transition(actor, pilot_id, PilotEvent.APPROVE, payload)

    def request_changes(
        self, actor: User, pilot_id: str, payload: RequestChangesRequest
    ) -> PilotView:
        return self._transition(
            actor,
            pilot_id,
            PilotEvent.REQUEST_CHANGES,
            payload,
            reason=payload.reason,
        )

    def resubmit(
        self, actor: User, pilot_id: str, payload: TransitionPilotRequest
    ) -> PilotView:
        return self._transition(actor, pilot_id, PilotEvent.RESUBMIT, payload)

    def mark_delivered(
        self, actor: User, pilot_id: str, payload: MarkDeliveredRequest
    ) -> PilotView:
        return self._transition(
            actor,
            pilot_id,
            PilotEvent.DELIVER,
            payload,
            delivery_reference=payload.delivery_reference,
        )

    def list_queue(
        self,
        actor: User,
        *,
        statuses: Iterable[PilotStatus] | None = None,
        reviewer_id: int | None = None,
        project_id: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> QueuePage:
        self._require_operator(actor)
        normalized_statuses = list(
            statuses or [PilotStatus.READY_FOR_REVIEW, PilotStatus.UNDER_REVIEW]
        )
        if not normalized_statuses:
            return QueuePage(items=[])
        limit = _validated_limit(limit)

        query = self.db.query(PilotStateRecord, ModernizationProject).join(
            ModernizationProject,
            ModernizationProject.id == PilotStateRecord.project_id,
        )
        query = query.filter(
            PilotStateRecord.status.in_(
                [status.value for status in normalized_statuses]
            )
        )
        if reviewer_id is not None:
            query = query.filter(PilotStateRecord.reviewer_id == reviewer_id)
        if project_id is not None:
            query = query.filter(PilotStateRecord.project_id == project_id)

        sort_column, sort_attr, descending = _queue_sort(normalized_statuses)
        if cursor:
            cursor_time, cursor_id = _decode_cursor(cursor)
            if descending:
                query = query.filter(
                    or_(
                        sort_column < cursor_time,
                        and_(
                            sort_column == cursor_time,
                            PilotStateRecord.pilot_id > cursor_id,
                        ),
                    )
                )
            else:
                query = query.filter(
                    or_(
                        sort_column > cursor_time,
                        and_(
                            sort_column == cursor_time,
                            PilotStateRecord.pilot_id > cursor_id,
                        ),
                    )
                )

        primary_order = sort_column.desc() if descending else sort_column.asc()
        rows = (
            query.order_by(primary_order, PilotStateRecord.pilot_id.asc())
            .limit(limit + 1)
            .all()
        )
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [self._queue_item(pilot, project) for pilot, project in rows]
        next_cursor = None
        if has_more and rows:
            last_pilot = rows[-1][0]
            next_cursor = _encode_cursor(
                _as_utc(getattr(last_pilot, sort_attr)), last_pilot.pilot_id
            )
        return QueuePage(items=items, next_cursor=next_cursor)

    def get_audit_history(
        self,
        actor: User,
        pilot_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AuditPage:
        self._require_operator(actor)
        pilot = self._get_pilot(pilot_id)
        limit = _validated_limit(limit)
        query = self.db.query(PilotAuditEvent).filter(
            PilotAuditEvent.pilot_id == pilot.pilot_id
        )
        if cursor:
            cursor_time, cursor_id = _decode_cursor(cursor)
            query = query.filter(
                or_(
                    PilotAuditEvent.occurred_at > cursor_time,
                    and_(
                        PilotAuditEvent.occurred_at == cursor_time,
                        PilotAuditEvent.event_id > cursor_id,
                    ),
                )
            )
        rows = (
            query.order_by(
                PilotAuditEvent.occurred_at.asc(), PilotAuditEvent.event_id.asc()
            )
            .limit(limit + 1)
            .all()
        )
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [_audit_view(event) for event in rows]
        next_cursor = None
        if has_more and rows:
            next_cursor = _encode_cursor(
                _as_utc(rows[-1].occurred_at), rows[-1].event_id
            )
        return AuditPage(items=items, next_cursor=next_cursor)

    def _transition(
        self,
        actor: User,
        pilot_id: str,
        event: PilotEvent,
        payload: TransitionPilotRequest,
        *,
        reason: str | None = None,
        delivery_reference: str | None = None,
    ) -> PilotView:
        pilot = self._get_pilot(pilot_id)
        project = self._get_project(pilot.project_id)
        self._require_event_access(actor, project, pilot, event)
        request_hash = _request_hash(
            event.value,
            {
                "pilot_id": pilot_id,
                "expected_version": payload.expected_version,
                "idempotency_key": payload.idempotency_key,
                "reason": reason,
                "delivery_reference": delivery_reference,
            },
        )
        replay = self._load_replay(
            actor.id, payload.idempotency_key, event.value, request_hash
        )
        if replay is not None:
            return replay
        if pilot.version != payload.expected_version:
            raise PilotVersionConflictError(pilot.status, pilot.version)

        current_status = PilotStatus(pilot.status)
        spec = TRANSITIONS[event]
        if current_status != spec.from_status:
            raise PilotTransitionNotAllowedError(pilot.status, pilot.version)
        if event in {PilotEvent.APPROVE, PilotEvent.REQUEST_CHANGES}:
            if pilot.reviewer_id != actor.id:
                raise PilotAccessDeniedError("Only the assigned reviewer may decide")
        if event in {PilotEvent.SUBMIT, PilotEvent.RESUBMIT}:
            self._require_result_ready(pilot.run_id)

        now = self._now()
        event_id = uuid.uuid4().hex
        new_version = pilot.version + 1
        updates: dict[str, object | None] = {
            "status": spec.to_status.value,
            "version": new_version,
            "updated_at": now,
            "last_transition_id": event_id,
        }
        if event in {PilotEvent.SUBMIT, PilotEvent.RESUBMIT}:
            updates["review_requested_at"] = now
        if event == PilotEvent.RESUBMIT:
            updates["reviewer_id"] = None
            updates["review_started_at"] = None
        elif event == PilotEvent.START_REVIEW:
            updates["reviewer_id"] = actor.id
            updates["review_started_at"] = now
        elif event == PilotEvent.APPROVE:
            updates["approved_by_id"] = actor.id
            updates["approved_at"] = now
        elif event == PilotEvent.REQUEST_CHANGES:
            updates["change_request_reason"] = reason
        elif event == PilotEvent.DELIVER:
            updates["delivered_by_id"] = actor.id
            updates["delivered_at"] = now
            updates["delivery_reference"] = delivery_reference

        try:
            updated_count = (
                self.db.query(PilotStateRecord)
                .filter(
                    PilotStateRecord.pilot_id == pilot.pilot_id,
                    PilotStateRecord.version == payload.expected_version,
                    PilotStateRecord.status == spec.from_status.value,
                )
                .update(updates, synchronize_session=False)
            )
            if updated_count != 1:
                self.db.rollback()
                replay = self._load_replay(
                    actor.id, payload.idempotency_key, event.value, request_hash
                )
                if replay is not None:
                    return replay
                current = self._get_pilot(pilot_id)
                if current.version != payload.expected_version:
                    raise PilotVersionConflictError(current.status, current.version)
                raise PilotTransitionNotAllowedError(current.status, current.version)

            self.db.expire_all()
            updated = self._get_pilot(pilot_id)
            audit = self._audit_event(
                pilot=updated,
                event_type=spec.audit_event,
                from_status=spec.from_status,
                to_status=spec.to_status,
                actor=actor,
                idempotency_key=payload.idempotency_key,
                result_version=new_version,
                occurred_at=now,
                reason=reason,
                event_id=event_id,
            )
            self.db.add(audit)
            self.db.flush()
            response = _pilot_view(updated)
            self._store_result(
                actor_id=actor.id,
                idempotency_key=payload.idempotency_key,
                operation=event.value,
                request_hash=request_hash,
                response=response,
                created_at=now,
            )
            self.db.commit()
            return response
        except PilotError:
            raise
        except IntegrityError as exc:
            self.db.rollback()
            replay = self._load_replay(
                actor.id, payload.idempotency_key, event.value, request_hash
            )
            if replay is not None:
                return replay
            raise PilotStorageError("Pilot transition could not be stored") from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise PilotStorageError("Pilot transition could not be stored") from exc

    def _get_project_for_run(
        self, project_id: str, run_id: str
    ) -> ModernizationProject:
        project = self._get_project(project_id)
        belongs_to_project = project.run_id == run_id or (
            self.db.query(ProjectRunHistory.id)
            .filter(
                ProjectRunHistory.project_id == project_id,
                ProjectRunHistory.run_id == run_id,
            )
            .first()
            is not None
        )
        run_exists = (
            self.db.query(AgentRun.run_id).filter(AgentRun.run_id == run_id).first()
            is not None
        )
        if not belongs_to_project or not run_exists:
            raise ProjectRunNotFoundError("Project run was not found")
        return project

    def _get_project(self, project_id: str) -> ModernizationProject:
        project = (
            self.db.query(ModernizationProject)
            .filter(ModernizationProject.id == project_id)
            .first()
        )
        if project is None:
            raise ProjectRunNotFoundError("Project run was not found")
        return project

    def _get_pilot(self, pilot_id: str) -> PilotStateRecord:
        pilot = (
            self.db.query(PilotStateRecord)
            .filter(PilotStateRecord.pilot_id == pilot_id)
            .first()
        )
        if pilot is None:
            raise PilotNotFoundError("Pilot was not found")
        return pilot

    def _find_by_project_run(
        self, project_id: str, run_id: str
    ) -> PilotStateRecord | None:
        return (
            self.db.query(PilotStateRecord)
            .filter(
                PilotStateRecord.project_id == project_id,
                PilotStateRecord.run_id == run_id,
            )
            .first()
        )

    def _require_project_access(
        self, actor: User, project: ModernizationProject
    ) -> None:
        if actor.role == UserRole.ADMIN.value or (
            actor.role == UserRole.USER.value and project.user_id == actor.id
        ):
            return
        raise PilotAccessDeniedError("Pilot access is denied")

    def _require_operator(self, actor: User) -> None:
        if actor.role != UserRole.ADMIN.value:
            raise PilotAccessDeniedError("Operator capability is required")

    def _require_event_access(
        self,
        actor: User,
        project: ModernizationProject,
        pilot: PilotStateRecord,
        event: PilotEvent,
    ) -> None:
        if event in {PilotEvent.SUBMIT, PilotEvent.RESUBMIT}:
            self._require_project_access(actor, project)
            return
        self._require_operator(actor)

    def _require_result_ready(self, run_id: str) -> None:
        run = self.db.query(AgentRun).filter(AgentRun.run_id == run_id).first()
        if run is None or str(run.status or "").lower() != "completed":
            raise PilotResultNotReadyError("Pilot result is not ready for review")

    def _load_replay(
        self,
        actor_id: int,
        idempotency_key: str,
        operation: str,
        request_hash: str,
    ) -> PilotView | None:
        result = (
            self.db.query(PilotCommandResult)
            .filter(
                PilotCommandResult.actor_id == actor_id,
                PilotCommandResult.idempotency_key == idempotency_key,
            )
            .first()
        )
        if result is None:
            return None
        if result.operation != operation or result.request_hash != request_hash:
            raise IdempotencyKeyReusedError(
                "Idempotency key was already used for a different command"
            )
        return PilotView.model_validate_json(result.response_json)

    def _store_result(
        self,
        *,
        actor_id: int,
        idempotency_key: str,
        operation: str,
        request_hash: str,
        response: PilotView,
        created_at: datetime,
    ) -> None:
        self.db.add(
            PilotCommandResult(
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                operation=operation,
                request_hash=request_hash,
                pilot_id=response.pilot_id,
                result_version=response.version,
                response_json=response.model_dump_json(),
                created_at=created_at,
            )
        )

    def _audit_event(
        self,
        *,
        pilot: PilotStateRecord,
        event_type: str,
        from_status: PilotStatus | None,
        to_status: PilotStatus,
        actor: User,
        idempotency_key: str,
        result_version: int,
        occurred_at: datetime,
        reason: str | None = None,
        event_id: str | None = None,
    ) -> PilotAuditEvent:
        return PilotAuditEvent(
            event_id=event_id or uuid.uuid4().hex,
            pilot_id=pilot.pilot_id,
            project_id=pilot.project_id,
            run_id=pilot.run_id,
            event_type=event_type,
            from_status=from_status.value if from_status else None,
            to_status=to_status.value,
            actor_id=actor.id,
            occurred_at=occurred_at,
            reason=reason,
            idempotency_key=idempotency_key,
            result_version=result_version,
            metadata_json="{}",
        )

    def _queue_item(
        self, pilot: PilotStateRecord, project: ModernizationProject
    ) -> QueueItem:
        archive_paths = build_project_result_archive_paths(
            archive_root=self.archive_root,
            project_id=pilot.project_id,
            run_id=pilot.run_id,
        )
        reviewer_display = (
            f"operator-{pilot.reviewer_id}" if pilot.reviewer_id is not None else None
        )
        return QueueItem(
            pilot_id=pilot.pilot_id,
            project_ref=_safe_ref("project", pilot.project_id),
            project_display_name=project.project_name,
            run_ref=_safe_ref("run", pilot.run_id),
            status=PilotStatus(pilot.status),
            version=pilot.version,
            created_at=_as_utc(pilot.created_at),
            updated_at=_as_utc(pilot.updated_at),
            review_requested_at=_optional_utc(pilot.review_requested_at),
            reviewer_display=reviewer_display,
            review_started_at=_optional_utc(pilot.review_started_at),
            approved_at=_optional_utc(pilot.approved_at),
            delivered_at=_optional_utc(pilot.delivered_at),
            docx_available=archive_paths["docx"].is_file(),
        )

    def _now(self) -> datetime:
        value = self.now_provider()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("now_provider must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)


def _pilot_view(pilot: PilotStateRecord) -> PilotView:
    return PilotView(
        pilot_id=pilot.pilot_id,
        project_id=pilot.project_id,
        run_id=pilot.run_id,
        status=PilotStatus(pilot.status),
        version=pilot.version,
        created_at=_as_utc(pilot.created_at),
        updated_at=_as_utc(pilot.updated_at),
        review_requested_at=_optional_utc(pilot.review_requested_at),
        reviewer_id=pilot.reviewer_id,
        review_started_at=_optional_utc(pilot.review_started_at),
        approved_by_id=pilot.approved_by_id,
        approved_at=_optional_utc(pilot.approved_at),
        delivered_by_id=pilot.delivered_by_id,
        delivered_at=_optional_utc(pilot.delivered_at),
        change_request_reason=pilot.change_request_reason,
        delivery_reference=pilot.delivery_reference,
    )


def _audit_view(event: PilotAuditEvent) -> AuditEventView:
    return AuditEventView(
        event_id=event.event_id,
        event_type=event.event_type,
        from_status=PilotStatus(event.from_status) if event.from_status else None,
        to_status=PilotStatus(event.to_status),
        actor_ref=f"actor-{event.actor_id}",
        occurred_at=_as_utc(event.occurred_at),
        reason=event.reason,
        result_version=event.result_version,
    )


def _request_hash(operation: str, payload: dict[str, object]) -> str:
    canonical = json.dumps(
        {"operation": operation, "payload": payload},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _safe_ref(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _queue_sort(statuses: list[PilotStatus]):
    status_set = set(statuses)
    if status_set == {PilotStatus.DELIVERED}:
        return PilotStateRecord.delivered_at, "delivered_at", True
    if status_set == {PilotStatus.APPROVED}:
        return PilotStateRecord.approved_at, "approved_at", False
    if status_set.issubset({PilotStatus.READY_FOR_REVIEW, PilotStatus.UNDER_REVIEW}):
        return PilotStateRecord.review_requested_at, "review_requested_at", False
    return PilotStateRecord.updated_at, "updated_at", True


def _encode_cursor(timestamp: datetime, item_id: str) -> str:
    raw = json.dumps(
        {"timestamp": _as_utc(timestamp).isoformat(), "id": item_id},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        timestamp = datetime.fromisoformat(payload["timestamp"])
        item_id = str(payload["id"])
        if timestamp.tzinfo is None or not item_id:
            raise ValueError
        return timestamp.astimezone(timezone.utc), item_id
    except (
        binascii.Error,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        raise ValueError("cursor is invalid") from exc


def _validated_limit(limit: int) -> int:
    if isinstance(limit, bool) or limit < 1 or limit > QUEUE_PAGE_MAX_SIZE:
        raise ValueError(f"limit must be between 1 and {QUEUE_PAGE_MAX_SIZE}")
    return limit


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _optional_utc(value: datetime | None) -> datetime | None:
    return _as_utc(value) if value is not None else None
