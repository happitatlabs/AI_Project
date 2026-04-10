from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from .anonymization_sample_cases import (
    AMBIGUOUS_IDENTIFIER_RETENTION,
    ANONYMIZATION_SAMPLE_CASES,
    EVENT_STREAM_SPLIT_CONTRACT,
    SERVICE_BACKED_SAMPLE_CASES,
    execute_sample_case,
)

try:
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False

_APP = None
_SKIP_REASON = None


def _get_app():
    global _APP, _SKIP_REASON
    if _APP is not None:
        return _APP
    if _SKIP_REASON is not None:
        return None
    if not _HAS_FASTAPI:
        _SKIP_REASON = "FastAPI/testclient not installed"
        return None
    try:
        from mellow_link.main import app

        _APP = app
        return _APP
    except Exception as exc:
        _SKIP_REASON = f"Could not import app: {exc}"
        return None


@pytest.fixture(scope="module")
def client():
    app = _get_app()
    if app is None:
        pytest.skip(_SKIP_REASON or "FastAPI app not available")
    return TestClient(app)


def _register_user(username_prefix: str) -> dict[str, object]:
    from mellow_link.infra import User, UserRole, create_access_token, create_default_folders_for_user
    from mellow_link.infra.database import SessionLocal

    username = f"{username_prefix}_{uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        user = User(username=username, hashed_password="test-hash", role=UserRole.USER.value)
        db.add(user)
        db.commit()
        db.refresh(user)
        create_default_folders_for_user(db, user.id, role=UserRole.USER.value)
        token = create_access_token(data={"sub": username}, role=user.role)
    return {
        "username": username,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}", "Accept": "application/json"},
    }


def _register_admin(username_prefix: str) -> dict[str, object]:
    from mellow_link.infra import User, UserRole, create_access_token, create_default_folders_for_user
    from mellow_link.infra.database import SessionLocal

    username = f"{username_prefix}_{uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        user = User(username=username, hashed_password="test-hash", role=UserRole.ADMIN.value)
        db.add(user)
        db.commit()
        db.refresh(user)
        create_default_folders_for_user(db, user.id, role=UserRole.ADMIN.value)
        token = create_access_token(data={"sub": username}, role=user.role)
    return {
        "username": username,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}", "Accept": "application/json"},
    }


def _combined_canonical_text(executed) -> str:
    return "\n".join(source.content for source in executed.safe_bundle.sources)


def _combined_preview_text(report: dict) -> str:
    return "\n".join(item["preview_text"] for item in report["source_previews"])


@pytest.mark.parametrize("case", SERVICE_BACKED_SAMPLE_CASES, ids=lambda item: item.sample_name)
def test_anonymization_sample_cases_match_current_contracts(case, tmp_path: Path):
    executed = execute_sample_case(case, tmp_path=tmp_path)
    expectation = case.expectation
    report = executed.report
    summary = report["report_summary"]
    validation = report["validation"]
    findings = {item["code"] for item in validation["findings"]}
    preview_text = _combined_preview_text(report)
    canonical_text = _combined_canonical_text(executed)

    assert summary["applied"] is True
    assert summary["canonical_source_count"] == len(case.assets)
    assert summary["structure_count"] == len(case.assets)
    assert len(summary["asset_counts"]) == len(case.assets)
    assert summary["validation_passed"] is expectation.validation_passed
    assert validation["passed"] is expectation.validation_passed
    assert report["bundle_debug"]["validation_passed"] is expectation.validation_passed
    assert summary["total_replacements"] >= expectation.min_total_replacements
    if expectation.max_total_replacements is not None:
        assert summary["total_replacements"] <= expectation.max_total_replacements

    for code in expectation.required_risk_flags:
        assert code in summary["risk_flags"]
    if expectation.validation_passed:
        assert summary["risk_flags"] == []
        assert validation["findings"] == []
    for code in expectation.required_findings:
        assert code in findings

    if expectation.preview_visible:
        assert report["source_previews"]
        assert report["bundle_debug"]["omitted_preview_count"] == 0
    else:
        assert report["source_previews"] == []
        assert report["bundle_debug"]["omitted_preview_count"] == len(case.assets)

    for token in expectation.canonical_must_include:
        assert token in canonical_text
    for token in expectation.canonical_must_exclude:
        assert token not in canonical_text
    for token in expectation.preview_must_include:
        assert token in preview_text
    for token in expectation.preview_must_exclude:
        assert token not in preview_text

    prepared_sections = {
        "source_code": executed.prepared_source_code,
        "sql_queries": executed.prepared_sql_queries,
        "ui_template": executed.prepared_ui_template,
        "framework_info": executed.prepared_framework_info,
    }
    for section_name in expectation.required_prepared_sections:
        assert prepared_sections[section_name].strip()


def test_ambiguous_identifier_case_keeps_non_structural_terms_in_canonical_output(tmp_path: Path):
    executed = execute_sample_case(AMBIGUOUS_IDENTIFIER_RETENTION, tmp_path=tmp_path)
    canonical_text = _combined_canonical_text(executed)
    summary = executed.report["report_summary"]

    assert "data" in canonical_text
    assert "mode" in canonical_text
    assert "helperFlag" in canonical_text
    assert "rowValue" in canonical_text
    assert summary["total_replacements"] <= 3


def test_anonymization_sample_catalog_covers_required_categories():
    names = {case.sample_name for case in ANONYMIZATION_SAMPLE_CASES}

    assert len(ANONYMIZATION_SAMPLE_CASES) >= 5
    assert "normal_balanced_bundle" in names
    assert "ambiguous_identifier_retention" in names
    assert "sensitive_signal_heavy_bundle" in names
    assert "failure_guard_mapping_visible" in names
    assert "event_stream_split_contract" in names


def test_event_stream_split_sample_keeps_debug_report_off_user_surfaces(client, tmp_path: Path):
    from mellow_link.infra import User
    from mellow_link.infra.database import SessionLocal
    from mellow_link.infra.run_events import (
        EVENT_TYPE_DEBUG_ANONYMIZATION_REPORT,
        EVENT_TYPE_RUN_FINISHED,
        EVENT_TYPE_RUN_STARTED,
        create_run,
        emit_event,
    )
    from mellow_link.routers.runs import _resolve_run_session_id

    executed = execute_sample_case(EVENT_STREAM_SPLIT_CONTRACT, tmp_path=tmp_path)
    report = executed.report
    summary = report["report_summary"]
    owner = _register_user("anon_sample_owner")
    admin = _register_admin("anon_sample_admin")

    with SessionLocal() as db:
        db_user = db.query(User).filter(User.username == owner["username"]).first()
        assert db_user is not None
        session_id = _resolve_run_session_id(db, db_user, None)
        run_id = create_run(session_id=session_id, db=db, module_id="rebuild_assistant", run_kind="rebuild_plan")
        emit_event(
            run_id,
            EVENT_TYPE_RUN_STARTED,
            {"user_input": EVENT_STREAM_SPLIT_CONTRACT.input_summary, "mode": "fast", "session_id": session_id},
            db=db,
        )
        emit_event(run_id, EVENT_TYPE_DEBUG_ANONYMIZATION_REPORT, report, db=db)
        emit_event(
            run_id,
            EVENT_TYPE_RUN_FINISHED,
            {
                "success": True,
                "summary": "completed",
                "module_id": "rebuild_assistant",
                "run_kind": "rebuild_plan",
                "anonymization_summary": summary,
            },
            db=db,
        )

    snapshot = client.get(f"/runs/{run_id}", headers=owner["headers"])
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["anonymization_summary"] == summary
    assert "source_previews" not in snapshot.json()

    user_events = client.get(f"/runs/{run_id}/events?format=json", headers=owner["headers"])
    assert user_events.status_code == 200, user_events.text
    assert all(item["type"] != EVENT_TYPE_DEBUG_ANONYMIZATION_REPORT for item in user_events.json()["events"])

    owner_dev = client.get(f"/runs/{run_id}/dev", headers=owner["headers"])
    assert owner_dev.status_code == 200, owner_dev.text
    assert all(item["type"] != EVENT_TYPE_DEBUG_ANONYMIZATION_REPORT for item in owner_dev.json()["events"])

    admin_events = client.get(f"/api/dev/runs/{run_id}/events", headers=admin["headers"])
    assert admin_events.status_code == 200, admin_events.text
    debug_event = next(item for item in admin_events.json()["events"] if item["type"] == EVENT_TYPE_DEBUG_ANONYMIZATION_REPORT)
    assert debug_event["payload"]["report_summary"] == summary
    assert "validation" in debug_event["payload"]
    assert "source_previews" in debug_event["payload"]
