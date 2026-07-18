from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from mellow_link.infra.database import (
    AgentRun,
    Base,
    ModernizationProject,
    PilotAuditEvent,
    PilotStateRecord,
    User,
    UserRole,
    get_current_user,
    get_db,
)
from mellow_link.routers.pilot_state import router as pilot_state_router
from mellow_link.services.pilot_state import (
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
    ProjectRunNotFoundError,
    RequestChangesRequest,
    TransitionPilotRequest,
)
from mellow_link.services.project_results.archive import (
    build_project_result_archive_paths,
)


class AdvancingClock:
    def __init__(self):
        self.value = datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        current = self.value
        self.value += timedelta(seconds=1)
        return current


@pytest.fixture()
def database(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pilot-state.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield engine, session_factory
    finally:
        engine.dispose()


@pytest.fixture()
def db_session(database):
    _, session_factory = database
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def actors(db_session):
    owner = User(
        username="pilot-owner-a",
        hashed_password="synthetic-hash-a",
        role=UserRole.USER.value,
    )
    other = User(
        username="pilot-owner-b",
        hashed_password="synthetic-hash-b",
        role=UserRole.USER.value,
    )
    reviewer_one = User(
        username="pilot-operator-one",
        hashed_password="synthetic-hash-c",
        role=UserRole.ADMIN.value,
    )
    reviewer_two = User(
        username="pilot-operator-two",
        hashed_password="synthetic-hash-d",
        role=UserRole.ADMIN.value,
    )
    guest = User(
        username="pilot-guest",
        hashed_password="synthetic-hash-e",
        role=UserRole.GUEST.value,
    )
    db_session.add_all([owner, other, reviewer_one, reviewer_two, guest])
    db_session.commit()
    for actor in (owner, other, reviewer_one, reviewer_two, guest):
        db_session.refresh(actor)
    return owner, other, reviewer_one, reviewer_two, guest


@pytest.fixture()
def project(db_session, actors):
    owner, *_ = actors
    return create_project_run(db_session, owner, "project-alpha", "run-alpha")


@pytest.fixture()
def clock():
    return AdvancingClock()


@pytest.fixture()
def service(db_session, tmp_path, clock):
    return PilotStateService(
        db_session,
        archive_root=tmp_path / "project-results",
        now_provider=clock,
    )


def create_project_run(
    db_session,
    owner: User,
    project_id: str,
    run_id: str,
    *,
    run_status: str = "completed",
) -> ModernizationProject:
    run = AgentRun(
        run_id=run_id,
        session_id=f"session-{run_id}",
        module_id="engine",
        run_kind="project",
        status=run_status,
    )
    project = ModernizationProject(
        id=project_id,
        user_id=owner.id,
        session_id=f"session-{run_id}",
        run_id=run_id,
        project_name=f"Synthetic {project_id}",
        client_name="Synthetic Client",
        goal_text="Synthetic modernization goal",
        upload_session_id=f"upload-{run_id}",
        status=run_status,
    )
    db_session.add_all([run, project])
    db_session.commit()
    db_session.refresh(project)
    return project


def create_pilot(service, owner, project, *, key="create-pilot"):
    return service.create(
        owner,
        CreatePilotRequest(
            project_id=project.id,
            run_id=project.run_id,
            idempotency_key=key,
        ),
    )


def transition_request(version: int, key: str) -> TransitionPilotRequest:
    return TransitionPilotRequest(expected_version=version, idempotency_key=key)


def advance_to_under_review(service, owner, reviewer, project):
    pilot = create_pilot(service, owner, project)
    pilot = service.submit(
        owner, pilot.pilot_id, transition_request(pilot.version, "submit-pilot")
    )
    return service.start_review(
        reviewer,
        pilot.pilot_id,
        transition_request(pilot.version, "start-review"),
    )


def test_create_get_and_persist_pilot(
    database, db_session, actors, project, service, tmp_path, clock
):
    owner, *_ = actors
    created = create_pilot(service, owner, project)

    assert created.status == PilotStatus.DRAFT
    assert created.version == 0
    assert created.created_at.tzinfo is not None
    owner_id = owner.id

    _, session_factory = database
    db_session.close()
    restarted_session = session_factory()
    try:
        restarted_service = PilotStateService(
            restarted_session,
            archive_root=tmp_path / "project-results",
            now_provider=clock,
        )
        restarted_owner = (
            restarted_session.query(User).filter(User.id == owner_id).one()
        )
        found = restarted_service.get(restarted_owner, created.pilot_id)
        assert found == created
    finally:
        restarted_session.close()


def test_duplicate_project_run_and_missing_relation_are_rejected(
    db_session, actors, project, service
):
    owner, *_ = actors
    create_pilot(service, owner, project)

    with pytest.raises(DuplicatePilotError):
        create_pilot(service, owner, project, key="different-create-key")

    with pytest.raises(ProjectRunNotFoundError):
        service.create(
            owner,
            CreatePilotRequest(
                project_id=project.id,
                run_id="run-not-owned-by-project",
                idempotency_key="missing-run",
            ),
        )


def test_happy_path_records_state_version_and_audit(
    actors, project, service, db_session
):
    owner, _, reviewer, *_ = actors
    pilot = create_pilot(service, owner, project)
    pilot = service.submit(owner, pilot.pilot_id, transition_request(0, "submit-happy"))
    pilot = service.start_review(
        reviewer, pilot.pilot_id, transition_request(1, "review-happy")
    )
    pilot = service.approve(
        reviewer, pilot.pilot_id, transition_request(2, "approve-happy")
    )
    pilot = service.mark_delivered(
        reviewer,
        pilot.pilot_id,
        MarkDeliveredRequest(
            expected_version=3,
            idempotency_key="deliver-happy",
            delivery_reference="synthetic-delivery-ticket",
        ),
    )

    assert pilot.status == PilotStatus.DELIVERED
    assert pilot.version == 4
    assert pilot.reviewer_id == reviewer.id
    assert pilot.approved_by_id == reviewer.id
    assert pilot.delivered_by_id == reviewer.id
    assert pilot.delivery_reference == "synthetic-delivery-ticket"

    events = (
        db_session.query(PilotAuditEvent)
        .filter(PilotAuditEvent.pilot_id == pilot.pilot_id)
        .order_by(PilotAuditEvent.occurred_at.asc())
        .all()
    )
    assert [event.event_type for event in events] == [
        "pilot_created",
        "pilot_submitted",
        "pilot_review_started",
        "pilot_approved",
        "pilot_delivered",
    ]
    assert [event.result_version for event in events] == [0, 1, 2, 3, 4]


def test_changes_requested_resubmit_cycle(actors, project, service):
    owner, _, reviewer_one, reviewer_two, _ = actors
    pilot = advance_to_under_review(service, owner, reviewer_one, project)
    pilot = service.request_changes(
        reviewer_one,
        pilot.pilot_id,
        RequestChangesRequest(
            expected_version=2,
            idempotency_key="request-changes",
            reason="Please verify the synthetic external summary.",
        ),
    )
    assert pilot.status == PilotStatus.CHANGES_REQUESTED
    assert pilot.change_request_reason.startswith("Please verify")

    pilot = service.resubmit(
        owner, pilot.pilot_id, transition_request(3, "resubmit-pilot")
    )
    assert pilot.status == PilotStatus.READY_FOR_REVIEW
    assert pilot.reviewer_id is None
    pilot = service.start_review(
        reviewer_two, pilot.pilot_id, transition_request(4, "second-review")
    )
    pilot = service.approve(
        reviewer_two, pilot.pilot_id, transition_request(5, "second-approval")
    )
    assert pilot.status == PilotStatus.APPROVED
    assert pilot.reviewer_id == reviewer_two.id


def test_forbidden_transitions_do_not_change_state(actors, project, service):
    owner, _, reviewer, *_ = actors
    pilot = create_pilot(service, owner, project)

    with pytest.raises(PilotTransitionNotAllowedError):
        service.mark_delivered(
            reviewer,
            pilot.pilot_id,
            MarkDeliveredRequest(
                expected_version=0, idempotency_key="draft-to-delivered"
            ),
        )
    with pytest.raises(PilotTransitionNotAllowedError):
        service.approve(
            reviewer,
            pilot.pilot_id,
            transition_request(0, "draft-to-approved"),
        )

    unchanged = service.get(owner, pilot.pilot_id)
    assert unchanged.status == PilotStatus.DRAFT
    assert unchanged.version == 0


def test_result_must_be_completed_before_submit(db_session, actors, service):
    owner, *_ = actors
    running_project = create_project_run(
        db_session, owner, "project-running", "run-running", run_status="running"
    )
    pilot = create_pilot(service, owner, running_project, key="create-running")

    with pytest.raises(PilotResultNotReadyError):
        service.submit(owner, pilot.pilot_id, transition_request(0, "submit-running"))


def test_duplicate_approval_replays_original_result_without_new_audit(
    actors, project, service, db_session
):
    owner, _, reviewer, *_ = actors
    pilot = advance_to_under_review(service, owner, reviewer, project)
    request = transition_request(2, "approve-retry")
    approved = service.approve(reviewer, pilot.pilot_id, request)
    delivered = service.mark_delivered(
        reviewer,
        pilot.pilot_id,
        MarkDeliveredRequest(
            expected_version=3, idempotency_key="deliver-after-approve"
        ),
    )

    replay = service.approve(reviewer, pilot.pilot_id, request)

    assert replay == approved
    assert replay.status == PilotStatus.APPROVED
    assert service.get(owner, pilot.pilot_id) == delivered
    assert (
        db_session.query(PilotAuditEvent)
        .filter(
            PilotAuditEvent.pilot_id == pilot.pilot_id,
            PilotAuditEvent.event_type == "pilot_approved",
        )
        .count()
        == 1
    )


def test_idempotency_key_payload_mismatch_is_rejected(actors, project, service):
    owner, *_ = actors
    pilot = create_pilot(service, owner, project)
    service.submit(owner, pilot.pilot_id, transition_request(0, "reused-command-key"))

    with pytest.raises(IdempotencyKeyReusedError):
        service.submit(
            owner, pilot.pilot_id, transition_request(1, "reused-command-key")
        )


def test_create_and_delivery_retries_are_idempotent(
    actors, project, service, db_session
):
    owner, _, reviewer, *_ = actors
    first = create_pilot(service, owner, project, key="create-retry")
    assert create_pilot(service, owner, project, key="create-retry") == first

    pilot = service.submit(owner, first.pilot_id, transition_request(0, "retry-submit"))
    pilot = service.start_review(
        reviewer, pilot.pilot_id, transition_request(1, "retry-review")
    )
    pilot = service.approve(
        reviewer, pilot.pilot_id, transition_request(2, "retry-approve")
    )
    request = MarkDeliveredRequest(expected_version=3, idempotency_key="deliver-retry")
    delivered = service.mark_delivered(reviewer, pilot.pilot_id, request)
    assert service.mark_delivered(reviewer, pilot.pilot_id, request) == delivered
    for event_type in ("pilot_created", "pilot_delivered"):
        assert (
            db_session.query(PilotAuditEvent)
            .filter(
                PilotAuditEvent.pilot_id == pilot.pilot_id,
                PilotAuditEvent.event_type == event_type,
            )
            .count()
            == 1
        )


def test_change_reason_and_delivery_reference_validation_is_explicit():
    with pytest.raises(ValidationError):
        RequestChangesRequest(
            expected_version=1, idempotency_key="blank-reason", reason="   "
        )
    with pytest.raises(ValidationError):
        RequestChangesRequest(
            expected_version=1,
            idempotency_key="control-reason",
            reason="synthetic\nreason",
        )
    with pytest.raises(ValidationError):
        MarkDeliveredRequest(
            expected_version=1,
            idempotency_key="long-delivery-reference",
            delivery_reference="x" * 501,
        )


def test_stale_version_and_competing_reviewers_are_rejected(
    database, db_session, actors, project, service, tmp_path, clock
):
    owner, _, reviewer_one, reviewer_two, _ = actors
    pilot = create_pilot(service, owner, project)
    pilot = service.submit(
        owner, pilot.pilot_id, transition_request(0, "submit-for-race")
    )

    _, session_factory = database
    second_session = session_factory()
    second_service = PilotStateService(
        second_session,
        archive_root=tmp_path / "project-results",
        now_provider=clock,
    )
    try:
        second_service.get(reviewer_two, pilot.pilot_id)
        service.start_review(
            reviewer_one, pilot.pilot_id, transition_request(1, "first-reviewer")
        )
        with pytest.raises(PilotVersionConflictError):
            second_service.start_review(
                reviewer_two,
                pilot.pilot_id,
                transition_request(1, "second-reviewer"),
            )
    finally:
        second_session.close()


def test_only_assigned_reviewer_can_approve(actors, project, service):
    owner, _, reviewer_one, reviewer_two, _ = actors
    pilot = advance_to_under_review(service, owner, reviewer_one, project)

    with pytest.raises(PilotAccessDeniedError):
        service.approve(
            reviewer_two, pilot.pilot_id, transition_request(2, "wrong-reviewer")
        )


def test_permissions_and_missing_pilot_are_consistent(actors, project, service):
    owner, other, reviewer, _, guest = actors
    pilot = create_pilot(service, owner, project)

    with pytest.raises(PilotAccessDeniedError):
        service.get(other, pilot.pilot_id)
    with pytest.raises(PilotAccessDeniedError):
        service.get(guest, pilot.pilot_id)
    with pytest.raises(PilotAccessDeniedError):
        service.list_queue(owner)
    with pytest.raises(PilotNotFoundError):
        service.get(reviewer, "missing-pilot")


def test_queue_classification_pagination_and_privacy(
    db_session, actors, project, service
):
    owner, _, reviewer, *_ = actors
    first = create_pilot(service, owner, project)
    first = service.submit(
        owner, first.pilot_id, transition_request(0, "queue-submit-one")
    )
    second_project = create_project_run(db_session, owner, "project-beta", "run-beta")
    second = create_pilot(service, owner, second_project, key="queue-create-two")
    second = service.submit(
        owner, second.pilot_id, transition_request(0, "queue-submit-two")
    )
    service.start_review(
        reviewer, second.pilot_id, transition_request(1, "queue-start-two")
    )
    docx_path = build_project_result_archive_paths(
        archive_root=service.archive_root,
        project_id=project.id,
        run_id=project.run_id,
    )["docx"]
    docx_path.parent.mkdir(parents=True, exist_ok=True)
    docx_path.write_bytes(b"synthetic-docx-presence-sentinel")

    first_page = service.list_queue(reviewer, limit=1)
    second_page = service.list_queue(reviewer, limit=1, cursor=first_page.next_cursor)
    items = first_page.items + second_page.items

    assert {item.status for item in items} == {
        PilotStatus.READY_FOR_REVIEW,
        PilotStatus.UNDER_REVIEW,
    }
    assert len({item.pilot_id for item in items}) == 2
    first_item = next(item for item in items if item.pilot_id == first.pilot_id)
    assert first_item.docx_available is True
    assert first_item.project_ref != project.id
    assert first_item.run_ref != project.run_id
    serialized = first_item.model_dump()
    assert "file_path" not in serialized
    assert "original_filename" not in serialized
    assert "raw_content" not in serialized
    assert "bundle_id" not in serialized


def test_changes_approved_and_delivered_queue_membership(actors, project, service):
    owner, _, reviewer, *_ = actors
    pilot = advance_to_under_review(service, owner, reviewer, project)
    pilot = service.request_changes(
        reviewer,
        pilot.pilot_id,
        RequestChangesRequest(
            expected_version=2,
            idempotency_key="queue-changes",
            reason="Review the synthetic summary.",
        ),
    )
    changes = service.list_queue(reviewer, statuses=[PilotStatus.CHANGES_REQUESTED])
    assert [item.pilot_id for item in changes.items] == [pilot.pilot_id]

    pilot = service.resubmit(
        owner, pilot.pilot_id, transition_request(3, "queue-resubmit")
    )
    pilot = service.start_review(
        reviewer, pilot.pilot_id, transition_request(4, "queue-review-again")
    )
    pilot = service.approve(
        reviewer, pilot.pilot_id, transition_request(5, "queue-approve")
    )
    approved = service.list_queue(reviewer, statuses=[PilotStatus.APPROVED])
    assert [item.pilot_id for item in approved.items] == [pilot.pilot_id]

    pilot = service.mark_delivered(
        reviewer,
        pilot.pilot_id,
        MarkDeliveredRequest(expected_version=6, idempotency_key="queue-deliver"),
    )
    delivered = service.list_queue(reviewer, statuses=[PilotStatus.DELIVERED])
    assert [item.pilot_id for item in delivered.items] == [pilot.pilot_id]
    assert service.list_queue(reviewer).items == []


def test_audit_history_is_paginated_without_duplicates(actors, project, service):
    owner, _, reviewer, *_ = actors
    pilot = advance_to_under_review(service, owner, reviewer, project)
    first_page = service.get_audit_history(reviewer, pilot.pilot_id, limit=2)
    second_page = service.get_audit_history(
        reviewer, pilot.pilot_id, limit=2, cursor=first_page.next_cursor
    )

    events = first_page.items + second_page.items
    assert [event.event_type for event in events] == [
        "pilot_created",
        "pilot_submitted",
        "pilot_review_started",
    ]
    assert len({event.event_id for event in events}) == 3
    assert all("synthetic-hash" not in event.model_dump_json() for event in events)
    assert all("idempotency_key" not in event.model_dump() for event in events)


def test_state_and_audit_are_atomic_when_audit_insert_fails(
    db_session, actors, project, service
):
    owner, _, reviewer, *_ = actors
    pilot = advance_to_under_review(service, owner, reviewer, project)
    db_session.execute(text("""
            CREATE TRIGGER reject_pilot_approval_audit
            BEFORE INSERT ON pilot_audit_events
            WHEN NEW.event_type = 'pilot_approved'
            BEGIN
                SELECT RAISE(ABORT, 'synthetic audit failure');
            END;
            """))
    db_session.commit()

    with pytest.raises(PilotStorageError):
        service.approve(
            reviewer, pilot.pilot_id, transition_request(2, "atomic-approve")
        )

    db_session.expire_all()
    stored = (
        db_session.query(PilotStateRecord)
        .filter(PilotStateRecord.pilot_id == pilot.pilot_id)
        .one()
    )
    assert stored.status == PilotStatus.UNDER_REVIEW.value
    assert stored.version == 2
    assert (
        db_session.query(PilotAuditEvent)
        .filter(
            PilotAuditEvent.pilot_id == pilot.pilot_id,
            PilotAuditEvent.event_type == "pilot_approved",
        )
        .count()
        == 0
    )


def test_schema_contains_persistent_pilot_tables(database):
    engine, _ = database
    table_names = set(inspect(engine).get_table_names())
    assert {
        "pilot_states",
        "pilot_audit_events",
        "pilot_command_results",
    }.issubset(table_names)


def test_storage_rejects_noncanonical_status(db_session, actors, project):
    owner, *_ = actors
    now = datetime.now(timezone.utc)
    db_session.add(
        PilotStateRecord(
            pilot_id="pilot-invalid-status",
            project_id=project.id,
            run_id=project.run_id,
            status="rejected",
            version=0,
            created_at=now,
            updated_at=now,
            created_by_id=owner.id,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_router_exposes_create_transition_queue_and_safe_errors(
    db_session, actors, project
):
    owner, _, reviewer, *_ = actors
    app = FastAPI()
    app.include_router(pilot_state_router)

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: owner
    client = TestClient(app)

    created_response = client.post(
        "/pilot-states",
        json={
            "project_id": project.id,
            "run_id": project.run_id,
            "idempotency_key": "api-create",
        },
    )
    assert created_response.status_code == 201
    pilot_id = created_response.json()["pilot_id"]

    submit_response = client.post(
        f"/pilot-states/{pilot_id}/submit",
        json={"expected_version": 0, "idempotency_key": "api-submit"},
    )
    assert submit_response.status_code == 200
    app.dependency_overrides[get_current_user] = lambda: reviewer
    queue_response = client.get("/pilot-states/queue/pending")
    assert queue_response.status_code == 200
    assert queue_response.json()["items"][0]["pilot_id"] == pilot_id

    conflict_response = client.post(
        f"/pilot-states/{pilot_id}/deliver",
        json={"expected_version": 1, "idempotency_key": "api-invalid-deliver"},
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["detail"]["code"] == "pilot_transition_not_allowed"

    invalid_status_response = client.get("/pilot-states/queue?status=rejected")
    assert invalid_status_response.status_code == 422
