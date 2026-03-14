import uuid

import pytest

try:
    from fastapi.testclient import TestClient
    _has_fastapi = True
except ImportError:
    _has_fastapi = False

_app = None
_skip_reason = None


def _get_app():
    global _app, _skip_reason
    if _app is not None:
        return _app
    if _skip_reason is not None:
        return None
    if not _has_fastapi:
        _skip_reason = "FastAPI/testclient not installed"
        return None
    try:
        from mellow_link.main import app
        _app = app
        return _app
    except Exception as e:
        _skip_reason = f"Could not import app: {e}"
        return None


@pytest.fixture(scope="module")
def client():
    app = _get_app()
    if app is None:
        pytest.skip(_skip_reason or "FastAPI app not available")
    return TestClient(app)


def _user_headers():
    from mellow_link.infra.database import SessionLocal
    from mellow_link.infra import User, UserRole, create_default_folders_for_user, create_access_token

    username = f"mod_{uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        user = User(username=username, hashed_password="test-hash", role=UserRole.USER.value)
        db.add(user)
        db.commit()
        db.refresh(user)
        create_default_folders_for_user(db, user.id, role=UserRole.USER.value)
        token = create_access_token(data={"sub": username}, role=user.role)
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def test_modules_api_lists_registered_modules(client):
    res = client.get("/api/modules")
    assert res.status_code == 200
    modules = res.json()["modules"]
    ids = {m["module_id"] for m in modules}
    assert {"sql_analytics", "research_assistant", "ai_workflow_console"}.issubset(ids)


def test_sql_analytics_run_has_module_metadata(client):
    headers = _user_headers()
    res = client.post(
        "/modules/sql_analytics/runs",
        headers={**headers, "Content-Type": "application/json"},
        json={"question": "지난 7일 환불률을 알려줘"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    run_id = data["run_id"]

    snap = client.get(f"/runs/{run_id}", headers=headers)
    assert snap.status_code == 200, snap.text
    body = snap.json()
    assert body["module_id"] == "sql_analytics"
    assert body["run_kind"] == "sql_analysis"


def test_research_assistant_reuses_temp_upload_flow(client):
    headers = _user_headers()
    temp_session_id = f"research-temp-{uuid.uuid4().hex[:8]}"

    upload = client.post(
        "/chat/upload-temp",
        data={"session_id": temp_session_id},
        files={"file": ("brief.txt", b"Quarterly revenue increased by 18 percent. Refunds decreased by 4 percent.")},
    )
    assert upload.status_code == 200, upload.text

    res = client.post(
        "/modules/research_assistant/runs",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "question": "업로드한 문서를 기준으로 핵심 변화를 요약해줘",
            "context_note": "간단한 요약으로 정리",
            "temp_session_id": temp_session_id,
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    run_id = data["run_id"]

    snap = client.get(f"/runs/{run_id}", headers=headers)
    assert snap.status_code == 200, snap.text
    body = snap.json()
    assert body["module_id"] == "research_assistant"
    assert body["run_kind"] == "research_run"


def test_research_assistant_formats_user_facing_summary():
    from mellow_link.modules.research_assistant.service import ResearchAssistantService

    svc = ResearchAssistantService()
    formatted = svc.format_user_summary(
        "매출은 전분기 대비 18% 증가했습니다. 다만 특정 제품군의 수익성은 낮습니다. "
        "환불률은 4% 감소했습니다. 다음 분기에는 저수익 제품군 정리가 필요합니다.",
        question="업로드한 문서를 기준으로 핵심 변화를 요약해줘",
        has_document_context=True,
    )

    assert "한 줄 결론" in formatted
    assert "핵심 요약" in formatted
    assert "주요 쟁점" in formatted
    assert "다음 액션" in formatted
    assert "18% 증가" in formatted
    assert "환불률은 4% 감소" in formatted


def test_research_assistant_detects_bootstrap_payload_as_weak_summary():
    from mellow_link.modules.research_assistant.service import ResearchAssistantService

    svc = ResearchAssistantService()
    weak = svc.is_weak_summary(
        '{"status":"initialized","message":"시스템 지침 인식 완료","workspace_directory":"mellow_link/workspace/","available_tools":["read_file"]}'
    )

    assert weak is True


def test_research_assistant_fallback_summary_mentions_incomplete_generation():
    from mellow_link.modules.research_assistant.service import ResearchAssistantService

    svc = ResearchAssistantService()
    formatted = svc.format_user_summary(
        "",
        question="문서를 읽고 SQL 유스케이스 적합성을 평가해줘",
        has_document_context=True,
    )

    assert "충분한 문서 기반 응답을 생성하지 못했습니다" in formatted
    assert "질문 범위를 더 좁혀 재실행하세요" in formatted


def test_sql_analytics_formats_user_facing_summary():
    from mellow_link.modules.sql_analytics.service import SQLAnalyticsService

    svc = SQLAnalyticsService()
    formatted = svc.format_user_summary(
        result={
            "decision": "high_risk",
            "normalized_request": {"filters": {"segment": "all"}},
            "sql_results": {
                "rows": [
                    {
                        "refund_rate": 0.081,
                        "inquiry_growth": 0.17,
                        "churn_rate": 0.05,
                    }
                ]
            },
            "rule_results": [
                {"matched": True, "message": "환불률이 기준치를 초과했습니다."},
                {"matched": True, "message": "문의량 증가가 감지되었습니다."},
            ],
        },
        question="현재 데이터에 어떤 이상 징후가 있는지 알려줘",
    )

    assert "한 줄 결론" in formatted
    assert "핵심 요약" in formatted
    assert "주요 쟁점" in formatted
    assert "다음 액션" in formatted
    assert "환불률 8.1%" in formatted
    assert "문의 증가율 17.0%" in formatted
    assert "환불률이 기준치를 초과했습니다." in formatted


def test_research_todos_view_uses_module_mapping():
    from mellow_link.infra.run_events import build_todos_view

    raw_todos = [
        {"todo_id": "R1", "title": "질문 정리"},
        {"todo_id": "R2", "title": "문서 문맥 수집"},
        {"todo_id": "R3", "title": "문서 기반 분석"},
        {"todo_id": "R4", "title": "결과 요약"},
    ]
    events = [
        {"type": "todo_started", "payload": {"todo_id": "R1"}},
        {"type": "todo_done", "payload": {"todo_id": "R1"}},
        {"type": "todo_started", "payload": {"todo_id": "R2"}},
        {"type": "todo_done", "payload": {"todo_id": "R2"}},
        {"type": "todo_started", "payload": {"todo_id": "R3"}},
        {"type": "todo_done", "payload": {"todo_id": "R3"}},
        {"type": "todo_started", "payload": {"todo_id": "R4"}},
        {"type": "todo_done", "payload": {"todo_id": "R4"}},
    ]

    todos_view = build_todos_view("research_assistant", raw_todos, None, events, run_status="completed")

    assert [stage["title"] for stage in todos_view] == ["준비", "처리", "완료"]
    assert [stage["status"] for stage in todos_view] == ["completed", "completed", "completed"]
    assert todos_view[0]["raw_todo_ids"] == ["R1", "R2"]
    assert todos_view[1]["raw_todo_ids"] == ["R3"]
    assert todos_view[2]["raw_todo_ids"] == ["R4"]


def test_unknown_module_fallback_returns_three_stages_and_progress_rounding():
    from mellow_link.infra.run_events import build_todos_view, _compute_normalized_progress_percent

    raw_todos = [{"todo_id": "X1", "title": "Only step"}]
    events = [{"type": "todo_started", "payload": {"todo_id": "X1"}}]

    todos_view = build_todos_view("unknown_module", raw_todos, "X1", events, run_status="running")

    assert len(todos_view) == 3
    assert todos_view[0]["raw_todo_ids"] == []
    assert todos_view[1]["raw_todo_ids"] == ["X1"]
    assert todos_view[2]["raw_todo_ids"] == []
    assert [stage["status"] for stage in todos_view] == ["completed", "in_progress", "pending"]
    assert _compute_normalized_progress_percent(todos_view, "running") == 50


def test_stage_status_priority_prefers_aborted_over_other_states():
    from mellow_link.infra.run_events import build_todos_view

    raw_todos = [
        {"todo_id": "A1", "title": "prep one"},
        {"todo_id": "A2", "title": "prep two"},
    ]
    events = [
        {"type": "todo_started", "payload": {"todo_id": "A1"}},
        {"type": "todo_done", "payload": {"todo_id": "A1"}},
        {"type": "todo_started", "payload": {"todo_id": "A2"}},
    ]

    todos_view = build_todos_view("unknown_module", raw_todos, "A2", events, run_status="failed")

    assert todos_view[0]["status"] == "completed"
    assert todos_view[1]["status"] == "aborted"
    assert todos_view[2]["status"] == "aborted"


def test_llm_service_resolves_request_timeout_override():
    from mellow_link.services.llm_service import LLMService

    svc = LLMService(timeout=30.0)

    timeout_seconds, source = svc._resolve_request_timeout(
        mode="research",
        request_timeout_seconds=90.0,
    )

    assert timeout_seconds == 90.0
    assert source == "http_client"


def test_llm_service_uses_default_timeout_without_override():
    from mellow_link.services.llm_service import LLMService

    svc = LLMService(timeout=30.0)

    timeout_seconds, source = svc._resolve_request_timeout(
        mode="fast",
        request_timeout_seconds=None,
    )

    assert timeout_seconds == 30.0
    assert source == "http_client"
