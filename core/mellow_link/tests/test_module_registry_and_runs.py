import uuid
import inspect
from types import SimpleNamespace
from pathlib import Path

import pytest

MELLOW_LINK_ROOT = Path(__file__).resolve().parents[1]

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


def _safe_bundle_payload():
    return {
        "goal": "이 JSP 주문 화면을 React 구조로 바꿔줘",
        "safe_bundle": {
            "bundle_id": f"safe_bundle_{uuid.uuid4().hex[:8]}",
            "project_id": "proj_test",
            "masking_level": "FULL",
            "asset_summary": [
                {
                    "asset_id": "asset_001",
                    "name": "legacy.jsp",
                    "temp_file_id": "temp_001",
                    "size": 10,
                    "kind_hint": "ui",
                    "language": "jsp",
                }
            ],
            "sources": [
                {
                    "asset_id": "asset_001",
                    "level": "FULL",
                    "language": "jsp",
                    "source_type": "canonical_anonymized",
                    "content": "class CLS_001 { function FUNC_001() {} }",
                    "replacement_stats": {"class": 1, "function": 1},
                }
            ],
            "structures": [
                {
                    "asset_id": "asset_001",
                    "level": "FULL",
                    "extracted_from": "canonical",
                    "nodes": [{"kind": "class", "id": "CLS_001"}],
                    "edges": [],
                }
            ],
            "guard": {
                "contains_original": False,
                "contains_mapping": False,
                "canonical_only": True,
                "structure_extracted_from_canonical": True,
            },
        },
        "constraints": [],
    }


def test_modules_api_lists_registered_modules(client):
    res = client.get("/api/modules")
    assert res.status_code == 200
    modules = res.json()["modules"]
    ids = {m["module_id"] for m in modules}
    assert {"sql_analytics", "research_assistant", "rebuild_assistant"}.issubset(ids)
    assert "ai_workflow_console" not in ids


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
    assert data["preferred_user_url"] == f"/runs?focus_run_id={run_id}"

    snap = client.get(f"/runs/{run_id}", headers=headers)
    assert snap.status_code == 200, snap.text
    body = snap.json()
    assert body["module_id"] == "sql_analytics"
    assert body["run_kind"] == "sql_analysis"


def test_ai_workflow_console_run_returns_preferred_user_url(client, monkeypatch):
    from mellow_link.modules.ai_workflow_console import api as workflow_api

    monkeypatch.setattr(
        workflow_api,
        "start_ai_workflow_run",
        lambda *args, **kwargs: None,
    )

    headers = _user_headers()
    res = client.post(
        "/modules/ai_workflow_console/runs",
        headers={**headers, "Content-Type": "application/json"},
        json={"task_type": "generation", "prompt": "간단한 생성 작업을 시작해줘"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["preferred_user_url"] == f"/runs?focus_run_id={data['run_id']}"


def test_research_assistant_reuses_temp_upload_flow(client, monkeypatch):
    from mellow_link.modules.research_assistant import api as research_api

    monkeypatch.setattr(
        research_api,
        "start_research_run",
        lambda *args, **kwargs: None,
    )

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
    assert data["preferred_user_url"] == f"/runs?focus_run_id={run_id}"

    snap = client.get(f"/runs/{run_id}", headers=headers)
    assert snap.status_code == 200, snap.text
    body = snap.json()
    assert body["module_id"] == "research_assistant"
    assert body["run_kind"] == "research_run"


def test_rebuild_assistant_bundle_run_has_module_metadata(client, monkeypatch):
    from mellow_link.modules.rebuild_assistant import api as rebuild_api

    monkeypatch.setattr(
        rebuild_api,
        "start_rebuild_assistant_safe_bundle_run",
        lambda *args, **kwargs: None,
    )

    headers = _user_headers()
    res = client.post(
        "/modules/rebuild_assistant/bundle-runs",
        headers={**headers, "Content-Type": "application/json"},
        json=_safe_bundle_payload(),
    )
    assert res.status_code == 200, res.text
    data = res.json()
    run_id = data["run_id"]

    snap = client.get(f"/runs/{run_id}", headers=headers)
    assert snap.status_code == 200, snap.text
    body = snap.json()
    assert body["module_id"] == "rebuild_assistant"
    assert body["run_kind"] == "rebuild_plan"


def test_rebuild_assistant_raw_public_route_is_blocked(client):
    headers = _user_headers()
    res = client.post(
        "/modules/rebuild_assistant/runs",
        headers={**headers, "Content-Type": "application/json"},
        json={"goal": "짧다", "assets": {"source_code": "legacy"}},
    )
    assert res.status_code == 403


def test_rebuild_assistant_bundle_run_requires_safe_bundle(client):
    headers = _user_headers()
    res = client.post(
        "/modules/rebuild_assistant/bundle-runs",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "goal": "이 기능을 단일 페이지 기준으로 재구성해줘",
            "constraints": [],
        },
    )
    assert res.status_code == 422


def test_start_project_wrapped_run_requires_safe_bundle():
    from mellow_link.modules.rebuild_assistant.api import start_project_wrapped_run

    try:
        start_project_wrapped_run(
            run_id="run_missing_bundle",
            session_id="session_missing_bundle",
            project_name="프로젝트",
            client_name="고객사",
            upload_session_id="upload",
            constraints=[],
            asset_manifest=[],
        )
    except TypeError as exc:
        assert "safe_bundle" in str(exc)
    else:
        raise AssertionError("safe_bundle must be required")


def test_rebuild_assistant_static_ui_does_not_call_raw_runs(client):
    res = client.get("/modules/rebuild_assistant")
    assert res.status_code == 200, res.text
    assert "/modules/rebuild_assistant/runs" not in res.text
    assert "Raw Run Disabled" in res.text
    assert "/projects/create" in res.text


def test_rebuild_assistant_compat_references_stay_in_allowed_files():
    root = MELLOW_LINK_ROOT
    allowed_compat = {
        str(root / "modules" / "rebuild_assistant" / "compat.py"),
        str(root / "tests" / "test_module_registry_and_runs.py"),
    }
    allowed_raw_route = {
        str(root / "modules" / "rebuild_assistant" / "api.py"),
        str(root / "modules" / "rebuild_assistant" / "README.md"),
        str(root / "docs" / "ANONYMIZATION_MVP_STATUS.md"),
        str(root / "tests" / "test_module_registry_and_runs.py"),
    }

    compat_hits = []
    raw_route_hits = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".md", ".html"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "start_rebuild_assistant_run_compat(" in text:
            compat_hits.append(str(path))
        if "/modules/rebuild_assistant/runs" in text:
            raw_route_hits.append(str(path))

    assert set(compat_hits) <= allowed_compat
    assert set(raw_route_hits) <= allowed_raw_route


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


def test_research_assistant_summary_sanitizes_markdown_and_redacted_path():
    from mellow_link.modules.research_assistant.service import ResearchAssistantService

    svc = ResearchAssistantService()
    formatted = svc.format_user_summary(
        """
한 줄 결론
- **명확한 MVP 구조**이나 [REDACTED_PATH] 데이터 파이프라인이 비어 있습니다.

핵심 요약
- **잘 설계된 점**: SQL 계층과 규칙 계층이 분리되어 있습니다.
- **빠진 점**: UI[REDACTED_PATH] 모듈과 피드백 루프 정의가 없습니다.
        """,
        question="문서를 평가해줘",
        has_document_context=True,
    )

    assert "**" not in formatted
    assert "[REDACTED_PATH]" not in formatted
    assert "UI 모듈" in formatted


def test_research_assistant_splits_compound_heading_items():
    from mellow_link.modules.research_assistant.service import ResearchAssistantService

    svc = ResearchAssistantService()
    formatted = svc.format_user_summary(
        """
한 줄 결론
- 구조는 명확합니다.

핵심 요약
- 잘 설계된 점: 규칙 엔진이 분리되어 있습니다. - 빠진 점: 데이터 파이프라인이 없습니다. - 추천 구현 순서: SQL -> 규칙 -> AI
        """,
        question="문서를 평가해줘",
        has_document_context=True,
    )

    assert "- 잘 설계된 점: 규칙 엔진이 분리되어 있습니다." in formatted
    assert "- 빠진 점: 데이터 파이프라인이 없습니다." in formatted
    assert "- 추천 구현 순서: SQL -> 규칙 -> AI" in formatted


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
    assert "고위험 상태" in formatted
    assert "환불률이 기준치를 초과했습니다." in formatted


def test_rebuild_assistant_structured_result_contract_uses_fixed_list_types():
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    prepared = svc.prepare_input(
        goal="이 JSP 주문 조회 화면을 React + REST API로 재구성해줘",
        assets=RebuildAssetsPayload(
            source_code="""
<%@ page language="java" %>
<%
String userId = request.getParameter("userId");
String sql = "SELECT * FROM orders WHERE user_id = ?";
%>
            """,
            database_schema="CREATE TABLE orders (id bigint, user_id varchar(50), status varchar(20));",
            sql_queries="SELECT o.id, o.status FROM orders o JOIN users u ON u.id = o.user_id",
            framework_info="JSP, Servlet, JDBC",
        ),
    )
    result = svc.build_result(prepared)

    dumped = result.model_dump()
    expected_keys = {
        "report_purpose",
        "report_scope",
        "report_questions",
        "one_line_conclusion",
        "core_business_rules",
        "executive_summary_v2",
        "grounded_business_rules",
        "decision_items",
        "retained_contracts",
        "priority_split_items",
        "verification_checkpoints",
        "design_options",
        "recommended_option",
        "execution_plan",
        "analysis_summary",
        "rebuild_strategy",
        "layer_reconstruction",
        "recomposition_draft",
        "risks",
        "extracted_rules",
        "recommended_directions",
        "confidence",
        "missing_context",
        "missing_context_details",
    }
    assert expected_keys <= set(dumped.keys())
    assert isinstance(dumped["report_purpose"], str)
    assert isinstance(dumped["report_scope"], list)
    assert isinstance(dumped["report_questions"], list)
    assert isinstance(dumped["one_line_conclusion"], str)
    assert isinstance(dumped["core_business_rules"], list)
    assert isinstance(dumped["analysis_summary"], list)
    assert isinstance(dumped["rebuild_strategy"], list)
    assert isinstance(dumped["risks"], list)
    assert isinstance(dumped["recommended_directions"], list)
    assert isinstance(dumped["executive_summary_v2"], list)
    assert isinstance(dumped["grounded_business_rules"], list)
    assert isinstance(dumped["decision_items"], list)
    assert isinstance(dumped["retained_contracts"], list)
    assert isinstance(dumped["priority_split_items"], list)
    assert isinstance(dumped["verification_checkpoints"], list)
    assert isinstance(dumped["design_options"], list)
    assert isinstance(dumped["execution_plan"], list)
    assert isinstance(dumped["missing_context"], list)
    assert isinstance(dumped["missing_context_details"], list)
    assert isinstance(dumped["confidence"], float)
    assert 0.0 <= dumped["confidence"] <= 1.0
    assert set(dumped["layer_reconstruction"].keys()) == {"database", "backend", "frontend"}
    assert set(dumped["recomposition_draft"].keys()) == {"database", "backend", "frontend"}
    assert set(dumped["extracted_rules"].keys()) == {"status_permissions", "search_filters", "save_validation"}
    assert all(isinstance(dumped["layer_reconstruction"][key], list) for key in ("database", "backend", "frontend"))
    assert all(isinstance(dumped["recomposition_draft"][key], list) for key in ("database", "backend", "frontend"))


def test_rebuild_assistant_scope_limiting_and_missing_context():
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    prepared = svc.prepare_input(
        goal="whole-system migration으로 전체 사이트를 배포 가능한 코드까지 다시 만들어줘",
        assets=RebuildAssetsPayload(source_code="<%-- minimal jsp --%>"),
    )
    result = svc.build_result(prepared)

    assert prepared.scope_limited is True
    assert result.rebuild_strategy
    assert result.missing_context
    assert result.confidence < 1.0


def test_rebuild_assistant_status_permissions_branching():
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    prepared = svc.prepare_input(
        goal="결재 상태와 권한에 따라 액션이 바뀌는 JSP 화면을 재구성해줘",
        assets=RebuildAssetsPayload(
            source_code="""
if ("APPROVED".equals(status) || userRole.equals("ADMIN")) { showApproveButton = true; }
if ("PENDING".equals(status)) { showRejectButton = true; }
            """,
            ui_template="""
<c:if test="${sessionScope.role eq 'ADMIN'}"><button>Approve</button></c:if>
<c:if test="${item.status eq 'PENDING'}"><button>Reject</button></c:if>
            """,
        ),
    )
    result = svc.build_result(prepared)

    assert prepared.signals.primary_feature_mode == "status_permissions"
    assert prepared.signals.status_permissions
    assert all("status_permissions" not in item for item in result.analysis_summary)
    assert any("권한 및 상태 규칙" in item for item in result.analysis_summary)
    assert any("정책 서비스" in item or "권한" in item for item in result.rebuild_strategy)
    assert result.recomposition_draft.backend
    rules = result.extracted_rules.status_permissions.model_dump()
    assert set(rules.keys()) == {
        "entities",
        "roles",
        "statuses",
        "actions",
        "role_action_matrix",
        "status_action_matrix",
        "transition_rules",
        "ui_visibility_rules",
        "policy_hints",
    }
    assert rules["entities"]
    assert "ADMIN".lower() in [item.lower() for item in rules["roles"]]
    assert rules["actions"]
    assert rules["transition_rules"]
    assert rules["ui_visibility_rules"] or rules["policy_hints"]


def test_rebuild_assistant_search_filters_branching():
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    prepared = svc.prepare_input(
        goal="검색 조건이 많은 주문 조회 화면을 재구성해줘",
        assets=RebuildAssetsPayload(
            source_code="""
String keyword = request.getParameter("keyword");
String statusFilter = request.getParameter("status");
String page = request.getParameter("page");
            """,
            sql_queries="""
SELECT * FROM orders
WHERE user_name LIKE ?
AND status = ?
ORDER BY created_at DESC
LIMIT ? OFFSET ?
            """,
        ),
    )
    result = svc.build_result(prepared)

    assert prepared.signals.primary_feature_mode == "search_filters"
    assert prepared.signals.search_filters
    assert all("search_filters" not in item for item in result.analysis_summary)
    assert any("조회 조건 규칙" in item for item in result.analysis_summary)
    assert any("조회" in item or "SQL 조건" in item for item in result.rebuild_strategy)
    assert any(
        "조회 모델" in item or "조회 상태" in item or "조회 파라미터" in item
        for item in result.recomposition_draft.backend + result.recomposition_draft.frontend
    )
    assert any("조회 조건 입력 영역" in item or "결과 목록 영역" in item for item in result.recomposition_draft.frontend)
    assert any("필터 상태" in item or "조회 조건" in item for item in result.recomposition_draft.frontend)
    assert any("결과 목록" in item or "조회 결과" in item for item in result.recomposition_draft.frontend)
    assert any("SQL 조건 매핑" in item or "조회 조건" in item for item in result.recomposition_draft.backend)
    assert "조회" in result.one_line_conclusion or "검색" in result.one_line_conclusion
    rules = result.extracted_rules.search_filters.model_dump()
    assert set(rules.keys()) == {
        "entities",
        "filter_fields",
        "query_params",
        "sort_rules",
        "paging_rules",
        "query_binding_rules",
        "default_filters",
        "result_shape_hints",
    }
    assert rules["entities"]
    assert rules["filter_fields"]
    assert rules["query_params"]
    assert rules["query_binding_rules"]
    assert rules["paging_rules"] or rules["sort_rules"] or rules["default_filters"] or rules["result_shape_hints"]


def test_rebuild_assistant_save_validation_branching():
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    prepared = svc.prepare_input(
        goal="저장 검증과 중복 체크가 많은 등록 기능을 재구성해줘",
        assets=RebuildAssetsPayload(
            source_code="""
if (name == null || name.isBlank()) throw new IllegalArgumentException("required");
if (repository.existsByCode(code)) throw new IllegalStateException("duplicate");
repository.save(entity);
            """,
            sql_queries="SELECT count(1) FROM products WHERE code = ?; INSERT INTO products(code, name) VALUES (?, ?);",
        ),
    )
    result = svc.build_result(prepared)

    assert prepared.signals.primary_feature_mode == "save_validation"
    assert prepared.signals.save_validation
    assert all("save_validation" not in item for item in result.analysis_summary)
    assert any("저장 검증 규칙" in item for item in result.analysis_summary)
    assert any("검증" in item or "중복" in item or "정책" in item for item in result.rebuild_strategy)
    assert any("커맨드" in item or "검증" in item or "정책" in item for item in result.recomposition_draft.backend)
    assert "우선 검토해야 합니다" in result.one_line_conclusion or "분리해야 합니다" in result.one_line_conclusion
    rules = result.extracted_rules.save_validation.model_dump()
    assert set(rules.keys()) == {
        "entities",
        "required_fields",
        "field_validation_rules",
        "duplicate_check_rules",
        "save_guard_rules",
        "exception_rules",
        "command_boundary_hints",
    }
    assert rules["entities"]
    assert rules["required_fields"]
    assert rules["field_validation_rules"]
    assert rules["duplicate_check_rules"]
    assert rules["save_guard_rules"]


def test_rebuild_assistant_confidence_varies_with_signal_coverage():
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    sparse = svc.prepare_input(
        goal="이 기능을 재구성해줘",
        assets=RebuildAssetsPayload(source_code="<% legacy %>"),
    )
    rich = svc.prepare_input(
        goal="주문 검색/저장/권한 기능을 React + REST API로 재구성해줘",
        assets=RebuildAssetsPayload(
            source_code="""
String keyword = request.getParameter("keyword");
if (userRole.equals("ADMIN")) { canApprove = true; }
if (repository.existsByCode(code)) throw new RuntimeException("duplicate");
            """,
            ui_template="<c:if test=\"${item.status eq 'PENDING'}\"><button>Approve</button></c:if>",
            database_schema="CREATE TABLE orders (id bigint, status varchar(20), code varchar(20));",
            sql_queries="SELECT * FROM orders WHERE status = ? AND name LIKE ? ORDER BY created_at DESC; INSERT INTO orders(code) VALUES (?);",
            framework_info="JSP + Spring MVC + MyBatis",
        ),
    )

    assert svc.estimate_confidence(rich) > svc.estimate_confidence(sparse)


def test_rebuild_assistant_summary_mentions_scope_metadata():
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    prepared = svc.prepare_input(
        goal="이 JSP 주문 조회 화면을 React + REST API로 재구성해줘",
        assets=RebuildAssetsPayload(source_code="<% String sql = \"SELECT * FROM orders\"; %>"),
    )
    result = svc.build_result(prepared)
    summary = svc.format_user_summary(result, scope_limited=prepared.scope_limited, needs_more_input=bool(result.missing_context))

    assert "## 결정 요약" in summary
    assert "## 판단 근거" in summary
    assert "## 실행 조치" in summary
    assert "실행 계획" in summary
    assert "근거 자산" in summary
    assert "유지 계약" in summary
    assert "레이어별 재구성" in summary
    assert "초안" in summary
    assert "리스크" in summary
    assert "confidence:" in summary


def _build_safe_bundle_for_rebuild_tests(asset_specs):
    from mellow_link.services.anonymization.bundle_builder import SafeBundleBuilder
    from mellow_link.services.anonymization.schemas import AnonymizationAsset, CanonicalAnonymizedSource, MaskingLevel, StructureArtifact

    assets = []
    sources = []
    structures = []
    for index, spec in enumerate(asset_specs, start=1):
        asset_id = f"asset_{index:03d}"
        name = spec["name"]
        content = spec.get("content", "")
        assets.append(
            AnonymizationAsset(
                asset_id=asset_id,
                name=name,
                temp_file_id=f"temp_{index:03d}",
                size=len(content.encode("utf-8")),
            )
        )
        sources.append(
            CanonicalAnonymizedSource(
                asset_id=asset_id,
                level=MaskingLevel.FULL,
                language=spec.get("language", ""),
                content=content,
            )
        )
        structures.append(
            StructureArtifact(
                asset_id=asset_id,
                level=MaskingLevel.FULL,
                extracted_from="canonical",
                nodes=[],
                edges=[],
            )
        )
    return SafeBundleBuilder().build(
        project_id="proj_safe_bundle_test",
        masking_level=MaskingLevel.FULL,
        assets=assets,
        canonical_sources=sources,
        structures=structures,
    )


def _accounting_payload_json(*, method="MOVING_AVERAGE", strict=True, include_exchange_rates=True, include_vouchers=True, include_account_mappings=True):
    exchange_rates = [
        {"currency": "USD", "rate_date": "2026-03-01", "rate": 1200},
        {"currency": "USD", "rate_date": "2026-03-02", "rate": 1300},
        {"currency": "USD", "rate_date": "2026-03-03", "rate": 1400},
    ] if include_exchange_rates else []
    vouchers = [
        {
            "voucher_id": "V001",
            "occurred_at": "2026-03-03",
            "lines": [
                {"account_code": "1110", "side": "debit", "amount_krw": 210000, "amount_fc": 150, "currency": "USD", "rate_used": 1400, "source_tx_ids": ["TX003"]},
                {"account_code": "5120", "side": "credit", "amount_krw": 187500, "source_tx_ids": ["TX003"]},
                {"account_code": "7190", "side": "credit", "amount_krw": 22500, "source_tx_ids": ["TX003"]},
            ],
        }
    ] if include_vouchers else []
    account_mappings = [
        {"purpose": "FX_GAIN", "account_code": "7190"},
        {"purpose": "FX_LOSS", "account_code": "7290"},
    ] if include_account_mappings else []
    return """
{
  "strict": %s,
  "transactions": [
    {"tx_id": "TX001", "tx_type": "BUY_FX", "occurred_at": "2026-03-01", "currency": "USD", "amount_fc": 100, "rate": 1200, "fx_account_id": "USD_MAIN"},
    {"tx_id": "TX002", "tx_type": "BUY_FX", "occurred_at": "2026-03-02", "currency": "USD", "amount_fc": 100, "rate": 1300, "fx_account_id": "USD_MAIN"},
    {"tx_id": "TX003", "tx_type": "PAY", "occurred_at": "2026-03-03", "currency": "USD", "amount_fc": 150, "rate": 1400, "fx_account_id": "USD_MAIN"}
  ],
  "exchange_rates": %s,
  "vouchers": %s,
  "account_mappings": %s,
  "policies": [
    {"policy_id": "P001", "fx_cost_method": "%s", "effective_from": "2026-01-01", "version": 1, "tolerance_krw": 1}
  ]
}
""" % (
        "true" if strict else "false",
        str(exchange_rates).replace("'", '"'),
        str(vouchers).replace("'", '"'),
        str(account_mappings).replace("'", '"'),
        method,
    )


def test_rebuild_assistant_safe_bundle_with_schema_and_query_sql_removes_db_request():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy.jsp", "content": "<c:if test=\"${status eq 'PENDING'}\">Approve</c:if>"},
            {"name": "schema.sql", "content": "CREATE TABLE orders (id bigint, status varchar(20));"},
            {"name": "query.sql", "content": "SELECT * FROM orders WHERE status = ?"},
        ]
    )

    prepared = svc.prepare_safe_bundle_input(goal="주문 마감 기능을 재구성해줘", safe_bundle=bundle, constraints=[])
    details = svc.build_missing_context_details(prepared)
    materials = [item.required_material for item in details]
    assert "DB 스키마 또는 핵심 SQL" not in materials
    assert "DB 스키마" not in materials
    assert "핵심 SQL" not in materials


def test_rebuild_assistant_safe_bundle_with_query_only_requests_schema_only():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy.jsp", "content": "<c:if test=\"${status eq 'PENDING'}\">Approve</c:if>"},
            {"name": "query.sql", "content": "SELECT * FROM orders WHERE status = ?"},
        ]
    )

    prepared = svc.prepare_safe_bundle_input(goal="주문 마감 기능을 재구성해줘", safe_bundle=bundle, constraints=[])
    materials = [item.required_material for item in svc.build_missing_context_details(prepared)]
    assert "DB 스키마" in materials
    assert "핵심 SQL" not in materials
    assert "DB 스키마 또는 핵심 SQL" not in materials


def test_rebuild_assistant_safe_bundle_with_schema_only_requests_sql_only():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy.jsp", "content": "<c:if test=\"${status eq 'PENDING'}\">Approve</c:if>"},
            {"name": "schema.sql", "content": "CREATE TABLE orders (id bigint, status varchar(20));"},
        ]
    )

    prepared = svc.prepare_safe_bundle_input(goal="주문 마감 기능을 재구성해줘", safe_bundle=bundle, constraints=[])
    materials = [item.required_material for item in svc.build_missing_context_details(prepared)]
    assert "핵심 SQL" in materials
    assert "DB 스키마" not in materials
    assert "DB 스키마 또는 핵심 SQL" not in materials


def test_rebuild_assistant_user_facing_strings_hide_internal_feature_modes():
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    prepared = svc.prepare_input(
        goal="저장 검증과 중복 체크가 많은 청구 조정 기능을 재구성해줘",
        assets=RebuildAssetsPayload(
            source_code="""
if (name == null || name.isBlank()) throw new IllegalArgumentException("required");
if (repository.existsByCode(code)) throw new IllegalStateException("duplicate");
repository.save(entity);
            """,
            sql_queries="SELECT count(1) FROM claim_adjustment WHERE code = ?; INSERT INTO claim_adjustment(code) VALUES (?);",
        ),
    )
    result = svc.build_result(prepared)
    formatted = svc.format_user_summary(result, scope_limited=prepared.scope_limited, needs_more_input=bool(result.missing_context))
    joined = "\n".join(
        [result.one_line_conclusion, *result.analysis_summary, *result.rebuild_strategy, *result.recommended_directions, formatted]
    )

    assert "status_permissions" not in joined
    assert "search_filters" not in joined
    assert "save_validation" not in joined


def test_rebuild_assistant_java_sample_anchor_and_core_rules():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {
                "name": "legacy.jsp",
                "content": '<button>마감</button><c:if test="${status eq \'READY\'}">close</c:if>',
            },
            {
                "name": "OrderCloseService.java",
                "content": """
if ("VIP".equals(order.getCustomerGrade()) && ("22".equals(currentHour) || "23".equals(currentHour) || "00".equals(currentHour))) return "vip_night_block";
if ("AGENCY".equals(order.getChannelCode()) && order.getOrderAmount() >= 5000000 && !"HQ".equals(userRole)) return "agency_high_amount_hq_only";
if ("Y".equals(order.getDeliveryHoldFlag())) return "delivery_hold_release_required";
if ("EXPORT".equals(order.getOrderType()) && order.getOrderAmount() >= 7000000) { order.setStatus("REVIEW_REQUIRED"); }
                """,
            },
            {"name": "schema.sql", "content": "CREATE TABLE orders (id bigint, status varchar(20));"},
            {"name": "query.sql", "content": "SELECT * FROM orders WHERE status = ?"},
        ]
    )
    prepared = svc.prepare_safe_bundle_input(
        goal="주문 관리 화면 현대화",
        safe_bundle=bundle,
        constraints=[
            "VIP 고객 야간 마감 제한 규칙은 변경 금지",
            "대리점 채널 승인 규칙은 유지",
            "배송보류 해제 프로세스는 별도 기능으로 분리하되 의미는 유지",
            "단일 마감 기능 범위만 대상으로 분석",
        ],
    )
    result = svc.build_result(prepared)
    formatted = svc.format_user_summary(result, scope_limited=prepared.scope_limited, needs_more_input=bool(result.missing_context))

    assert "주문 마감" in result.one_line_conclusion or "주문 마감" in formatted
    expected = [
        "VIP 고객은 야간 시간대에 주문 마감을 수행할 수 없습니다.",
        "대리점 채널의 고액 주문은 본사 권한으로만 마감할 수 있습니다.",
        "배송보류 상태가 해제되기 전에는 주문 마감을 진행할 수 없습니다.",
        "수출 주문의 고액 건은 즉시 마감하지 않고 REVIEW_REQUIRED 상태로 전환해야 합니다.",
    ]
    hits = [item for item in expected if item in formatted]
    assert len(hits) >= 3


def test_rebuild_assistant_python_sample_anchor_and_core_rules():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "claim_adjustment.html", "content": "<h1>Claim Adjustment</h1><button>승인 가능</button>"},
            {
                "name": "legacy_app.py",
                "content": """
if claim["status"] in ["CLOSED", "CANCELLED"]: return "마감 또는 취소 건은 조정 불가"
if claim["accident_type"] == "FRAUD" and user_role != "HQ_REVIEWER": return "특수 사고건은 본사 심사만 가능"
if claim["claim_amount"] >= 3000000 and user_role == "BRANCH_MANAGER": return "지점장 한도 초과"
if claim["claim_amount"] >= 10000000 and dept_code != "CLAIM_AUDIT": return "고액 청구는 심사전담부서만 조정 가능"
if claim["branch_code"] == "B99" and claim["is_urgent"] == "Y" and user_role == "BRANCH_MANAGER": return "특수지점 긴급건은 본사 선승인 필요"
                """,
            },
            {"name": "schema.sql", "content": "CREATE TABLE insurance_claim (claim_id varchar(20), status varchar(20));"},
            {"name": "query.sql", "content": "SELECT claim_id, status, claim_amount FROM insurance_claim WHERE claim_id = ?"},
        ]
    )
    prepared = svc.prepare_safe_bundle_input(
        goal="청구 조정 기능을 현대적인 서비스 구조 재구성",
        safe_bundle=bundle,
        constraints=[
            "기존 승인 상태 체계는 유지",
            "긴급 청구의 우선 처리 규칙은 변경 금지",
            "지점장 승인 한도와 심사팀 승인 한도는 유지",
        ],
    )
    result = svc.build_result(prepared)
    formatted = svc.format_user_summary(result, scope_limited=prepared.scope_limited, needs_more_input=bool(result.missing_context))

    assert "청구 조정" in result.one_line_conclusion or "청구 조정" in formatted
    expected = [
        "FRAUD 사고건은 HQ_REVIEWER 권한으로만 청구 조정을 수행할 수 있습니다.",
        "지점장은 300만원 이상 청구건을 조정할 수 없습니다.",
        "1천만원 이상 청구건은 CLAIM_AUDIT 부서만 조정할 수 있습니다.",
        "B99 지점의 긴급 청구건은 본사 선승인 없이 조정할 수 없습니다.",
        "CLOSED 또는 CANCELLED 상태의 청구건은 조정할 수 없습니다.",
    ]
    hits = [item for item in expected if item in formatted]
    assert len(hits) >= 4


def test_rebuild_assistant_grounded_rules_include_evidence_and_confidence_reason():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "claim_adjustment.html", "content": "<h1>Claim Adjustment</h1>"},
            {
                "name": "legacy_app.py",
                "content": """
if claim["status"] in ["CLOSED", "CANCELLED"]: return "조정 불가"
if claim["accident_type"] == "FRAUD" and user_role != "HQ_REVIEWER": return "본사 심사만 가능"
if claim["claim_amount"] >= 3000000 and user_role == "BRANCH_MANAGER": return "지점장 한도 초과"
if claim["claim_amount"] >= 10000000 and dept_code != "CLAIM_AUDIT": return "심사전담부서만 가능"
                """,
            },
            {"name": "schema.sql", "content": "CREATE TABLE insurance_claim (claim_id varchar(20), status varchar(20));"},
            {"name": "query.sql", "content": "SELECT claim_id, status, claim_amount FROM insurance_claim WHERE claim_id = ?"},
        ]
    )
    prepared = svc.prepare_safe_bundle_input(
        goal="청구 조정 기능을 현대적인 서비스 구조 재구성",
        safe_bundle=bundle,
        constraints=["기존 승인 상태 체계는 유지", "지점장 승인 한도와 심사팀 승인 한도는 유지"],
    )
    result = svc.build_result(prepared)

    assert result.grounded_business_rules
    assert all(rule.evidence for rule in result.grounded_business_rules)
    assert all(rule.confidence_reason for rule in result.grounded_business_rules)


def test_rebuild_assistant_retained_contracts_and_verification_do_not_overlap():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy.jsp", "content": '<button>마감</button><c:if test="${status eq \'READY\'}">close</c:if>'},
            {
                "name": "OrderCloseService.java",
                "content": """
if ("VIP".equals(order.getCustomerGrade()) && "22".equals(currentHour)) return "vip_night_block";
if ("Y".equals(order.getDeliveryHoldFlag())) return "delivery_hold_release_required";
if ("EXPORT".equals(order.getOrderType()) && order.getOrderAmount() >= 7000000) { order.setStatus("REVIEW_REQUIRED"); }
                """,
            },
            {"name": "schema.sql", "content": "CREATE TABLE orders (id bigint, status varchar(20));"},
            {"name": "query.sql", "content": "SELECT * FROM orders WHERE status = ?"},
        ]
    )
    prepared = svc.prepare_safe_bundle_input(goal="주문 관리 화면 현대화", safe_bundle=bundle, constraints=["주문 상태 코드는 유지"])
    result = svc.build_result(prepared)

    retained = {item.item for item in result.retained_contracts}
    verification = {item.item for item in result.verification_checkpoints}
    assert retained
    assert verification
    assert retained.isdisjoint(verification)
    assert any(
        "status 값" in item
        or "상태값" in item
        or "delivery_hold_flag" in item
        or "channel_code" in item
        for item in retained
    )
    assert all("상태 코드는 유지" not in item for item in retained)
    status_items = [item for item in retained if "status" in item.lower()]
    assert status_items
    assert all("BRANCH" not in item and "VIP" not in item for item in status_items)
    assert any("REVIEW_REQUIRED" in item or "READY" in item or "PAID" in item for item in status_items)


def test_rebuild_assistant_design_options_have_single_recommendation_and_selection_reason():
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    prepared = svc.prepare_input(
        goal="청구 조정 기능을 현대적인 서비스 구조 재구성",
        assets=RebuildAssetsPayload(
            source_code='if claim["accident_type"] == "FRAUD" and user_role != "HQ_REVIEWER": return "no"',
            sql_queries="SELECT claim_id, status, claim_amount FROM insurance_claim WHERE claim_id = ?",
        ),
        constraints=["기존 승인 상태 체계는 유지"],
    )
    result = svc.build_result(prepared)

    assert len([item for item in result.design_options if item.recommended]) == 1
    assert all(item.selection_reason for item in result.design_options)
    assert result.recommended_option is not None
    assert result.recommended_option.selection_reason
    assert any(token in result.recommended_option.selection_reason for token in ("승인 주체", "승인 권한", "부서", "고액 승인"))


def test_rebuild_assistant_order_selection_reason_uses_grounded_rules():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy.jsp", "content": '<button>마감</button><c:if test="${status eq \'READY\'}">close</c:if>'},
            {
                "name": "OrderCloseService.java",
                "content": """
if ("VIP".equals(order.getCustomerGrade()) && "22".equals(currentHour)) return "vip_night_block";
if ("Y".equals(order.getDeliveryHoldFlag())) return "delivery_hold_release_required";
if ("AGENCY".equals(order.getChannelCode()) && order.getOrderAmount() >= 5000000 && !"HQ".equals(user.getOrgCode())) return "hq_only";
if ("EXPORT".equals(order.getOrderType()) && order.getOrderAmount() >= 7000000) { order.setStatus("REVIEW_REQUIRED"); }
                """,
            },
            {"name": "schema.sql", "content": "CREATE TABLE orders (id bigint, status varchar(20), delivery_hold_flag varchar(1), channel_code varchar(10));"},
            {"name": "query.sql", "content": "SELECT * FROM orders WHERE status IN ('PAID', 'READY', 'REVIEW_REQUIRED')"},
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(
            goal="주문 관리 화면 현대화",
            safe_bundle=bundle,
            constraints=["주문 상태 코드는 유지", "배송보류 해제 프로세스는 별도 기능으로 분리하되 의미는 유지"],
        )
    )

    reason = result.recommended_option.selection_reason if result.recommended_option else ""
    assert reason
    assert any(token in reason for token in ("상태 전이", "권한", "배송보류", "REVIEW_REQUIRED"))
    assert "단일 기능 범위에서 규칙 분리와 계약 유지의 균형이 가장 좋습니다." not in reason
    assert "구조를 함께 관리할 수 있는 구조" not in reason
    assert "가장 적합합니다" not in reason
    assert "옵션 A." not in reason


def test_rebuild_assistant_claim_selection_reason_uses_grounded_rules():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "claim_adjustment.html", "content": "<h1>Claim Adjustment</h1>"},
            {
                "name": "legacy_app.py",
                "content": """
if claim["status"] in ["CLOSED", "CANCELLED"]: return "조정 불가"
if claim["accident_type"] == "FRAUD" and user_role != "HQ_REVIEWER": return "본사 심사만 가능"
if claim["claim_amount"] >= 3000000 and user_role == "BRANCH_MANAGER": return "지점장 한도 초과"
if claim["claim_amount"] >= 10000000 and dept_code != "CLAIM_AUDIT": return "심사전담부서만 가능"
                """,
            },
            {"name": "schema.sql", "content": "CREATE TABLE insurance_claim (claim_id varchar(20), status varchar(20), claim_amount integer, dept_code varchar(20));"},
            {"name": "query.sql", "content": "SELECT claim_id, status, claim_amount FROM insurance_claim WHERE claim_id = ?"},
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(
            goal="청구 조정 기능을 현대적인 서비스 구조 재구성",
            safe_bundle=bundle,
            constraints=["기존 승인 상태 체계는 유지", "지점장 승인 한도와 심사팀 승인 한도는 유지"],
        )
    )

    reason = result.recommended_option.selection_reason if result.recommended_option else ""
    assert reason
    assert any(token in reason for token in ("금액 한도", "승인 권한", "CLAIM_AUDIT", "상태 제한"))
    assert "단일 기능 범위에서 규칙 분리와 계약 유지의 균형이 가장 좋습니다." not in reason
    assert "구조를 함께 관리할 수 있는 구조" not in reason
    assert "가장 적합합니다" not in reason
    assert "옵션 A." not in reason


def test_rebuild_assistant_domain_specific_options_and_plans_are_differentiated():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()

    order_bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy.jsp", "content": '<button>마감</button><c:if test="${status eq \'READY\'}">close</c:if>'},
            {
                "name": "OrderCloseService.java",
                "content": """
if ("VIP".equals(order.getCustomerGrade()) && "22".equals(currentHour)) return "vip_night_block";
if ("Y".equals(order.getDeliveryHoldFlag())) return "delivery_hold_release_required";
if ("EXPORT".equals(order.getOrderType()) && order.getOrderAmount() >= 7000000) { order.setStatus("REVIEW_REQUIRED"); }
                """,
            },
            {"name": "schema.sql", "content": "CREATE TABLE orders (id bigint, status varchar(20), delivery_hold_flag varchar(1));"},
            {"name": "query.sql", "content": "SELECT * FROM orders WHERE status IN ('PAID', 'READY', 'REVIEW_REQUIRED')"},
        ]
    )
    claim_bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "claim_adjustment.html", "content": "<h1>Claim Adjustment</h1>"},
            {
                "name": "legacy_app.py",
                "content": """
if claim["status"] in ["CLOSED", "CANCELLED"]: return "조정 불가"
if claim["claim_amount"] >= 3000000 and user_role == "BRANCH_MANAGER": return "지점장 한도 초과"
if claim["claim_amount"] >= 10000000 and dept_code != "CLAIM_AUDIT": return "심사전담부서만 가능"
                """,
            },
            {"name": "schema.sql", "content": "CREATE TABLE insurance_claim (claim_id varchar(20), status varchar(20), claim_amount integer, dept_code varchar(20));"},
            {"name": "query.sql", "content": "SELECT claim_id, status, claim_amount, dept_code FROM insurance_claim WHERE claim_id = ?"},
        ]
    )

    order_result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="주문 관리 화면 현대화", safe_bundle=order_bundle, constraints=["주문 상태 코드는 유지"])
    )
    claim_result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="청구 조정 기능을 현대적인 서비스 구조 재구성", safe_bundle=claim_bundle, constraints=["기존 승인 상태 체계는 유지"])
    )

    assert any("상태 전이" in item.name or "상태 전이" in item.structure_summary for item in order_result.design_options)
    assert any("권한" in item.name or "승인" in item.structure_summary or "부서" in item.structure_summary for item in claim_result.design_options)
    assert any("REVIEW_REQUIRED" in " ".join(week.tasks) for week in order_result.execution_plan)
    assert any("300만원" in " ".join(week.tasks) or "CLAIM_AUDIT" in " ".join(week.tasks) for week in claim_result.execution_plan)
    assert all(item.linked_rules or item.linked_contracts for item in order_result.priority_split_items)
    assert all(item.linked_rules or item.linked_contracts for item in claim_result.priority_split_items)
    assert all(week.related_rules or week.related_contracts for week in order_result.execution_plan)
    assert all(week.related_rules or week.related_contracts for week in claim_result.execution_plan)
    assert all("validation" not in week.goal.lower() for week in claim_result.execution_plan)
    assert [week.goal for week in order_result.execution_plan] != [week.goal for week in claim_result.execution_plan]
    assert any(token in order_result.priority_split_items[0].reason for token in ("VIP", "REVIEW_REQUIRED", "대리점"))
    assert any(token in claim_result.priority_split_items[0].reason for token in ("CLAIM_AUDIT", "승인", "부서", "권한"))
    assert any("REVIEW_REQUIRED" in risk or "배송보류" in risk for risk in order_result.risks)
    assert any("금액 한도" in risk or "B99" in risk or "FRAUD" in risk or "CLAIM_AUDIT" in risk or "권한 규칙" in risk for risk in claim_result.risks)


def test_rebuild_assistant_applies_transition_and_access_templates_for_order_sample():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy.jsp", "content": '<button>마감</button><c:if test="${status eq \'READY\'}">close</c:if>'},
            {
                "name": "OrderCloseService.java",
                "content": """
if ("VIP".equals(order.getCustomerGrade()) && "22".equals(currentHour)) return "vip_night_block";
if ("AGENCY".equals(order.getChannelCode()) && order.getOrderAmount() >= 5000000 && !"HQ".equals(user.getOrgCode())) return "hq_only";
if ("EXPORT".equals(order.getOrderType()) && order.getOrderAmount() >= 7000000) { order.setStatus("REVIEW_REQUIRED"); }
                """,
            },
            {"name": "schema.sql", "content": "CREATE TABLE orders (id bigint, status varchar(20), channel_code varchar(20));"},
            {"name": "query.sql", "content": "SELECT * FROM orders WHERE status IN ('PAID', 'READY', 'REVIEW_REQUIRED')"},
        ]
    )

    prepared = svc.prepare_safe_bundle_input(goal="주문 관리 화면 현대화", safe_bundle=bundle, constraints=["주문 상태 코드는 유지"])
    grounded = svc.build_grounded_business_rules(prepared, svc.extract_core_business_rules(prepared))
    retained = svc.build_retained_contracts(prepared, grounded)
    applied = svc.build_applied_templates(prepared, grounded, retained)

    template_ids = [item.template_id for item in applied]
    assert "state_transition" in template_ids
    assert "access_control" in template_ids


def test_rebuild_assistant_state_transition_sample_keeps_state_transition_primary_with_validation_signals():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy.jsp", "content": '<button>마감</button><c:if test="${status eq \'READY\'}">close</c:if>'},
            {
                "name": "OrderCloseService.java",
                "content": """
if ("Y".equals(order.getDeliveryHoldFlag())) return "blocked";
if ("EXPORT".equals(order.getOrderType()) && order.getOrderAmount() >= 7000000) { order.setStatus("REVIEW_REQUIRED"); }
orderRepository.save(order);
                """,
            },
            {"name": "query.sql", "content": "UPDATE orders SET status = 'REVIEW_REQUIRED' WHERE order_id = ?"},
            {"name": "schema.sql", "content": "CREATE TABLE orders (id bigint, status varchar(20), delivery_hold_flag char(1));"},
        ]
    )

    prepared = svc.prepare_safe_bundle_input(goal="주문 관리 화면 현대화", safe_bundle=bundle, constraints=["주문 상태 코드는 유지"])
    grounded = svc.build_grounded_business_rules(prepared, svc.extract_core_business_rules(prepared))
    retained = svc.build_retained_contracts(prepared, grounded)
    applied = svc.build_applied_templates(prepared, grounded, retained)
    primary = svc._primary_template(prepared, applied)
    result = svc.build_result(prepared)

    assert primary is not None
    assert primary.template_id == "state_transition"
    assert "차단 조건" not in result.one_line_conclusion
    assert "검증 순서" not in result.one_line_conclusion
    assert result.recommended_option is not None
    assert "검증 규칙 중심" not in result.recommended_option.name
    assert any(token in result.one_line_conclusion for token in ("상태 전이", "처리 가능 상태", "전이 조건"))
    assert any(token in " ".join(result.executive_summary_v2) for token in ("상태 전이", "처리 가능 상태"))
    assert all("검증" not in item.statement for item in result.decision_items)
    assert all("검증" not in item.item for item in result.priority_split_items[:2])
    assert all("검증" not in week.goal for week in result.execution_plan[:3])
    backend_draft = " ".join(result.recomposition_draft.backend)
    assert "검증 계층" not in backend_draft
    assert "상태 전이" in backend_draft or "처리 가능 여부" in backend_draft


def test_rebuild_assistant_applies_validation_template_for_claim_sample():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "claim_adjustment.html", "content": "<h1>Claim Adjustment</h1>"},
            {
                "name": "legacy_app.py",
                "content": """
if claim["status"] in ["CLOSED", "CANCELLED"]: return "조정 불가"
if claim["claim_amount"] >= 3000000 and user_role == "BRANCH_MANAGER": return "지점장 한도 초과"
if claim["claim_amount"] >= 10000000 and dept_code != "CLAIM_AUDIT": return "심사전담부서만 가능"
                """,
            },
            {"name": "schema.sql", "content": "CREATE TABLE insurance_claim (claim_id varchar(20), status varchar(20), claim_amount integer, dept_code varchar(20));"},
        ]
    )

    prepared = svc.prepare_safe_bundle_input(goal="청구 조정 기능 현대화", safe_bundle=bundle, constraints=["지점장 승인 한도는 유지"])
    grounded = svc.build_grounded_business_rules(prepared, svc.extract_core_business_rules(prepared))
    retained = svc.build_retained_contracts(prepared, grounded)
    applied = svc.build_applied_templates(prepared, grounded, retained)

    template_ids = [item.template_id for item in applied]
    assert "validation" in template_ids
    assert "access_control" in template_ids


def test_rebuild_assistant_search_filter_sample_applies_query_filter_template():
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    prepared = svc.prepare_input(
        goal="검색 조건이 많은 주문 조회 화면을 재구성해줘",
        assets=RebuildAssetsPayload(
            source_code='String keyword = request.getParameter("keyword"); String statusFilter = request.getParameter("status");',
            sql_queries="SELECT * FROM orders WHERE user_name LIKE ? AND status = ? ORDER BY created_at DESC",
        ),
    )
    grounded = svc.build_grounded_business_rules(prepared, svc.extract_core_business_rules(prepared))
    retained = svc.build_retained_contracts(prepared, grounded)
    applied = svc.build_applied_templates(prepared, grounded, retained)
    primary = svc._primary_template(prepared, applied)
    result = svc.build_result(prepared)

    assert any(item.template_id == "query_filter" for item in applied)
    assert primary is not None
    assert primary.template_id == "query_filter"
    assert "조회 조건" in result.one_line_conclusion or "조회 조건" in " ".join(result.executive_summary_v2)
    assert result.recommended_option is not None
    assert "조회 모델" in result.recommended_option.name or "필터" in result.recommended_option.name
    top_rule_text = " ".join(f"{item.title} {item.description}" for item in grounded[:4])
    assert "상태 전이와 액션 노출 조건" not in top_rule_text
    assert not any("상태 전이" in item for item in result.risks[:3])
    assert "조회/필터 기능" in result.one_line_conclusion or "조회/필터 기능" in " ".join(result.executive_summary_v2)
    rendered = "\n".join(
        result.executive_summary_v2
        + [result.one_line_conclusion]
        + [item.statement for item in result.decision_items]
        + [item.item for item in result.priority_split_items]
        + [item.reason for item in result.priority_split_items]
        + result.risks
    )
    assert "조회 조회" not in rendered
    assert "분리을" not in rendered
    assert "규칙 규칙" not in rendered
    assert "정합성를" not in rendered
    assert len(retained) >= 2
    retained_text = " ".join(item.item for item in retained)
    assert "조회 조건 파라미터 계약" in retained_text or "정렬과 페이징 기본값 계약" in retained_text
    assert not retained or "status 컬럼의 상태값" not in retained[0].item
    execution_text = " ".join(week.goal + " " + " ".join(week.tasks) for week in result.execution_plan)
    assert "조회 조회" not in execution_text
    assert "분리을" not in execution_text
    assert "규칙 규칙" not in execution_text
    assert "정합성를" not in execution_text
    draft_text = " ".join(result.recomposition_draft.database + result.recomposition_draft.backend + result.recomposition_draft.frontend)
    assert "조회 조회" not in draft_text
    assert "정합성를" not in draft_text


def test_rebuild_assistant_amount_threshold_sample_applies_amount_threshold_template():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {
                "name": "cs_expense_policy.cs",
                "content": 'if (isExecutive && amount <= 300000) { return "AUTO_APPROVED"; } if (amount <= dailyLimit) { return "WITHIN_LIMIT"; } if (amount > dailyLimit && amount <= 1000000) { return "REQUIRES_MANAGER_APPROVAL"; } return "REQUIRES_FINANCE_APPROVAL";',
            },
            {
                "name": "sql_order_limit.sql",
                "content": "SELECT order_amount, CASE WHEN order_amount <= 50000 THEN 'SMALL' WHEN order_amount > 50000 AND order_amount <= 300000 THEN 'MEDIUM' WHEN order_amount > 300000 THEN 'LARGE' END AS amount_grade FROM purchase_order WHERE order_amount > 0 AND order_amount <= limit_amount;",
            },
            {
                "name": "schema.sql",
                "content": "CREATE TABLE purchase_order (order_id bigint, order_amount integer, limit_amount integer, amount_grade varchar(20));",
            },
        ]
    )
    prepared = svc.prepare_safe_bundle_input(goal="금액 한도 규칙이 많은 주문 처리 기능", safe_bundle=bundle, constraints=["고액 주문 한도는 유지"])
    grounded = svc.build_grounded_business_rules(prepared, svc.extract_core_business_rules(prepared))
    retained = svc.build_retained_contracts(prepared, grounded)
    applied = svc.build_applied_templates(prepared, grounded, retained)
    primary = svc._primary_template(prepared, applied)
    result = svc.build_result(prepared)

    assert any(item.template_id == "amount_threshold" for item in applied)
    assert primary is not None
    assert primary.template_id == "amount_threshold"
    assert "금액" in result.one_line_conclusion or "한도" in result.one_line_conclusion
    assert result.recommended_option is not None
    assert "금액 한도" in result.recommended_option.name or "한도" in result.recommended_option.selection_reason
    top_rule_text = " ".join(f"{item.title} {item.description}" for item in grounded[:3])
    assert "조회 조건과 SQL 파라미터 조합 규칙" not in top_rule_text
    assert "정렬" not in top_rule_text
    assert "검증" not in top_rule_text
    assert len(retained) >= 2
    assert any(("금액" in item.item or "한도" in item.item) for item in retained)
    retained_text = " ".join(item.item for item in retained)
    assert "금액 구간 경계(50000, 300000)" in retained_text
    assert "dailyLimit 한도 기준 계약" in retained_text or "limit_amount 한도 기준 계약" in retained_text
    assert "고액 처리 경계(50000)" not in retained_text
    assert "금액 기준(300000, 1000000)" not in retained_text
    assert "승인 필요 경계(1000000)" in retained_text
    verification_text = " ".join(item.item for item in result.verification_checkpoints)
    assert "검증" not in verification_text
    assert "한도 초과 이후 후속 처리 기준" in verification_text or not verification_text
    draft_text = " ".join(result.recomposition_draft.database + result.recomposition_draft.backend + result.recomposition_draft.frontend)
    assert "금액 구간" in draft_text or "한도" in draft_text or "고액 처리" in draft_text
    executive = " ".join(result.executive_summary_v2[:3]) + " " + result.one_line_conclusion
    assert "차단 조건" not in executive
    assert "검증 순서" not in executive
    assert "저장 전 검증" not in executive
    execution_text = " ".join(week.goal + " " + " ".join(week.tasks) for week in result.execution_plan)
    assert "검증 흐름" not in execution_text
    assert "저장 전 검증" not in execution_text
    assert "차단 조건" not in execution_text
    assert "검증" not in " ".join(week.goal for week in result.execution_plan)
    rendered = "\n".join(
        result.executive_summary_v2
        + [result.one_line_conclusion]
        + [item.statement for item in result.decision_items]
        + [item.item for item in result.priority_split_items]
        + [item.reason for item in result.priority_split_items]
        + [option.name for option in result.design_options]
        + [risk for option in result.design_options for risk in option.risks]
        + [item.item for item in result.verification_checkpoints]
        + result.risks
    )
    assert "규칙 규칙" not in rendered
    assert "검증" not in rendered
    assert "금액 구간" in execution_text
    assert "한도" in execution_text
    assert "승인" in execution_text


def test_rebuild_assistant_workflow_single_approval_detected():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {
                "name": "approval_service.java",
                "content": """
if ("SUBMITTED".equals(request.getStatus()) && "MANAGER".equals(approverRole)) {
    return approve ? "APPROVED" : "REJECTED";
}
                """,
            },
            {
                "name": "schema.sql",
                "content": "CREATE TABLE approval_request (request_id bigint, status varchar(20), approver_role varchar(20));",
            },
        ]
    )

    prepared = svc.prepare_safe_bundle_input(goal="단일 승인 흐름이 있는 요청 처리 기능", safe_bundle=bundle, constraints=["승인 권한 체계는 유지"])
    result = svc.build_result(prepared)
    grounded = result.grounded_business_rules
    retained = result.retained_contracts
    applied = svc.build_applied_templates(prepared, grounded, retained)
    primary = svc._primary_template(prepared, applied)

    top_titles = [item.title for item in grounded[:4]]
    retained_text = " ".join(item.item for item in retained)
    rendered = " ".join(result.executive_summary_v2 + [result.one_line_conclusion] + [item.statement for item in result.decision_items])

    assert primary is not None
    assert primary.template_id == "workflow"
    assert any(item.template_id == "workflow" for item in applied)
    assert any(title in top_titles for title in ("승인 트리거 조건", "승인 단계 구조", "의사결정 분기 조건", "예외 처리 흐름"))
    assert sum(1 for title in top_titles if title in ("승인 트리거 조건", "승인 단계 구조", "의사결정 분기 조건", "예외 처리 흐름")) >= 2
    assert len(retained) >= 2
    assert "승인 경로" in retained_text or "단계" in retained_text
    assert "여부을" not in rendered


def test_rebuild_assistant_workflow_multistep_detected():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {
                "name": "approval_service.java",
                "content": """
if (approvalStep == 1 && "TEAM_MANAGER".equals(approverRole) && approve) {
    return "MANAGER_APPROVED";
}
if (approvalStep == 2 && "FINANCE_MANAGER".equals(approverRole) && approve) {
    return "FINANCE_APPROVED";
}
                """,
            },
            {
                "name": "schema.sql",
                "content": "CREATE TABLE approval_request (request_id bigint, approval_step integer, approver_role varchar(30), status varchar(20));",
            },
        ]
    )

    result = svc.build_result(svc.prepare_safe_bundle_input(goal="다단계 승인 흐름이 있는 요청 기능", safe_bundle=bundle, constraints=["승인 단계는 유지"]))

    top_titles = [item.title for item in result.grounded_business_rules[:4]]
    assert any(item.title == "승인 단계 구조" for item in result.grounded_business_rules)
    assert any(item.title == "승인 주체 정의" for item in result.grounded_business_rules)
    assert sum(1 for title in top_titles if title in ("승인 트리거 조건", "승인 단계 구조", "의사결정 분기 조건", "예외 처리 흐름")) >= 2
    assert any("단계별 승인 순서" in item.item or "승인 경로와 처리 순서" in item.item for item in result.retained_contracts)


def test_rebuild_assistant_workflow_exception_flow_detected():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {
                "name": "approval_service.java",
                "content": """
if (urgent && amount < 100000) { return "AUTO_APPROVED"; }
if (delegateApprover != null && approvalStep == 1) { return "DELEGATED"; }
if (reject) { return "REJECTED"; }
if (hold) { return "ON_HOLD"; }
                """,
            },
            {
                "name": "schema.sql",
                "content": "CREATE TABLE approval_request (request_id bigint, approval_step integer, delegate_approver varchar(30), status varchar(20));",
            },
        ]
    )

    result = svc.build_result(svc.prepare_safe_bundle_input(goal="예외 승인과 대리 승인이 있는 요청 기능", safe_bundle=bundle, constraints=["예외 승인 흐름은 유지"]))

    rendered = "\n".join(
        result.executive_summary_v2
        + [result.one_line_conclusion]
        + [item.title for item in result.grounded_business_rules]
        + [item.item for item in result.retained_contracts]
        + [week.goal for week in result.execution_plan]
    )
    assert "승인 트리거" in rendered
    assert "승인 주체" in rendered
    assert "승인 단계" in rendered
    assert "예외" in rendered
    assert "여부을" not in rendered
    assert any("승인 경로" in item.item or "예외 승인" in item.item for item in result.retained_contracts)


def test_rebuild_assistant_workflow_safe_bundle_pipeline_keeps_workflow_result():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
    from mellow_link.services.anonymization import (
        AnonymizationAsset,
        AnonymizationRunRequest,
        AnonymizationService,
        MaskingLevel,
    )

    root = Path(__file__).resolve().parents[1]
    sample_dir = root / "modules" / "rebuild_assistant" / "samples" / "06. workflow"
    files = [
        sample_dir / "cs_leave_workflow.cs",
        sample_dir / "ts_approval_flow.ts",
    ]

    svc = RebuildAssistantService()
    assets = [
        AnonymizationAsset(
            asset_id=f"asset_{index:03d}",
            name=path.name,
            temp_file_id=f"temp_{index:03d}",
            size=path.stat().st_size,
            content_text=path.read_text(encoding="utf-8", errors="ignore"),
            original_bytes=path.read_bytes(),
        )
        for index, path in enumerate(files, start=1)
    ]
    bundle = AnonymizationService().run_anonymization_pipeline(
        AnonymizationRunRequest(
            project_id="proj_workflow_pipeline",
            upload_session_id="workflow_pipeline_session",
            masking_level=MaskingLevel.FULL,
            assets=assets,
        )
    ).safe_bundle

    prepared = svc.prepare_safe_bundle_input(
        goal="승인형 문서",
        safe_bundle=bundle,
        constraints=["승인 단계 구조 유지", "예외 승인 규칙 유지"],
    )
    result = svc.build_result(prepared)
    applied = svc.build_applied_templates(prepared, result.grounded_business_rules, result.retained_contracts)
    primary = svc._primary_template(prepared, applied)
    grounded_titles = [item.title for item in result.grounded_business_rules[:4]]
    retained_text = " ".join(item.item for item in result.retained_contracts)

    assert primary is not None
    assert primary.template_id == "workflow"
    assert sum(1 for title in grounded_titles if title in ("승인 트리거 조건", "승인 단계 구조", "의사결정 분기 조건", "예외 처리 흐름")) >= 2
    assert len(result.retained_contracts) >= 2
    assert "승인 경로" in retained_text or "단계별 승인 순서" in retained_text
    assert result.recommended_option is not None
    assert "승인 흐름 중심" in result.recommended_option.name
    assert result.primary_judgment == "workflow"
    assert result.primary_judgment_reason
    assert any(item.name == "workflow" and item.matched and item.reasons for item in result.pattern_candidates)


def test_rebuild_assistant_workflow_beats_amount_threshold_when_approval_flow_exists():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {
                "name": "approval_amount.java",
                "content": """
if ("SUBMITTED".equals(status) && amount > 1000000 && "MANAGER".equals(approverRole)) {
    return "MANAGER_APPROVED";
}
if ("MANAGER_APPROVED".equals(status) && "FINANCE".equals(approverRole)) {
    return "FINANCE_APPROVED";
}
                """,
            },
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(
            goal="금액 기준으로 승인 단계가 시작되는 결재 기능",
            safe_bundle=bundle,
            constraints=["승인 단계 구조 유지"],
        )
    )

    assert result.primary_judgment == "workflow"
    assert any(item.name == "amount_threshold" for item in result.pattern_candidates)


def test_rebuild_assistant_workflow_beats_access_control_when_stage_exists():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {
                "name": "approval_roles.java",
                "content": """
if (approvalStep == 1 && "MANAGER".equals(approverRole)) { return "MANAGER_APPROVED"; }
if (approvalStep == 2 && "FINANCE".equals(approverRole)) { return approve ? "FINANCE_APPROVED" : "REJECTED"; }
                """,
            },
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(
            goal="승인 역할과 단계가 함께 있는 결재 기능",
            safe_bundle=bundle,
            constraints=["승인 단계 유지"],
        )
    )

    assert result.primary_judgment == "workflow"


def test_rebuild_assistant_query_filter_beats_amount_threshold_when_amount_is_only_filter():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload

    svc = RebuildAssistantService()
    assets = RebuildAssetsPayload(
        source_code='function search(amount, status, sort, page) { return fetch(`/api/orders?amount=${amount}&status=${status}&sort=${sort}&page=${page}`); }',
        sql_queries="SELECT * FROM orders WHERE order_amount <= 300000 AND status = :status ORDER BY created_at DESC LIMIT :limit OFFSET :offset",
    )
    result = svc.build_result(
        svc.prepare_input(
            goal="금액 필터가 포함된 주문 목록 조회 기능",
            assets=assets,
            constraints=["조회 조건은 유지"],
        )
    )

    assert result.primary_judgment == "query_filter"


def test_rebuild_assistant_state_transition_beats_access_control_when_status_move_is_explicit():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload

    svc = RebuildAssistantService()
    assets = RebuildAssetsPayload(
        source_code='if ("READY".equals(order.getStatus()) && "MANAGER".equals(role)) { order.setStatus("APPROVED"); }',
        sql_queries="UPDATE purchase_order SET status = 'APPROVED' WHERE status IN ('READY')",
    )
    result = svc.build_result(
        svc.prepare_input(
            goal="권한 조건이 있지만 핵심은 상태 이동인 주문 처리 기능",
            assets=assets,
            constraints=["상태 코드는 유지"],
        )
    )

    assert result.primary_judgment == "state_transition"


def test_rebuild_assistant_uses_validation_fallback_when_no_pattern_is_strong():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload

    svc = RebuildAssistantService()
    assets = RebuildAssetsPayload(source_code="<div>legacy form</div>")
    result = svc.build_result(
        svc.prepare_input(
            goal="단순 레거시 폼 현대화",
            assets=assets,
            constraints=[],
        )
    )

    assert result.primary_judgment == "validation"


def test_rebuild_assistant_workflow_falls_back_to_state_transition_without_actor_or_gate():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {
                "name": "state_service.java",
                "content": """
if ("SUBMITTED".equals(order.getStatus())) {
    order.setStatus("APPROVED");
}
                """,
            },
            {
                "name": "state.sql",
                "content": "UPDATE purchase_order SET status = 'APPROVED' WHERE status IN ('SUBMITTED')",
            },
        ]
    )

    prepared = svc.prepare_safe_bundle_input(goal="상태 변경이 있는 주문 처리 기능", safe_bundle=bundle, constraints=["상태 코드는 유지"])
    grounded = svc.build_grounded_business_rules(prepared, svc.extract_core_business_rules(prepared))
    retained = svc.build_retained_contracts(prepared, grounded)
    applied = svc.build_applied_templates(prepared, grounded, retained)
    primary = svc._primary_template(prepared, applied)

    assert primary is not None
    assert primary.template_id == "state_transition"
    assert all(item.template_id != "workflow" for item in applied[:1])


def test_rebuild_assistant_generation_methods_do_not_branch_on_domain_names():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    targets = [
        RebuildAssistantService.build_decision_items,
        RebuildAssistantService.build_priority_split_items,
        RebuildAssistantService.build_design_options,
        RebuildAssistantService.build_execution_plan,
    ]
    for target in targets:
        source = inspect.getsource(target)
        assert "주문 마감" not in source
        assert "청구 조정" not in source


def test_rebuild_assistant_role_or_dept_is_not_emitted_as_status_contract():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "access_control_sample.py", "content": 'if claim["claim_amount"] >= 10000000 and dept_code != "CLAIM_AUDIT": return "심사전담부서만 가능"'},
            {"name": "schema.sql", "content": "CREATE TABLE insurance_claim (claim_id varchar(20), status varchar(20), claim_amount integer, dept_code varchar(20));"},
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="접근 제어 규칙이 많은 청구 조정 기능", safe_bundle=bundle, constraints=["심사팀 승인 한도는 유지"])
    )

    retained = " ".join(item.item for item in result.retained_contracts)
    assert "status 컬럼의 상태값(CLAIM_AUDIT)" not in retained
    assert ".status 값(CLAIM_AUDIT)" not in retained


def test_rebuild_assistant_validation_sample_prefers_validation_template():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "validation_sample.java", "content": 'if (claimAmount >= 3000000) return "limit"; if ("Y".equals(delivery_hold_flag)) return "blocked"; if (duplicate) return "dup";'},
            {"name": "validation_sample.sql", "content": "SELECT claim_amount, delivery_hold_flag FROM claim_adjustment WHERE claim_id = ?"},
        ]
    )
    prepared = svc.prepare_safe_bundle_input(goal="검증 규칙이 많은 청구 조정 기능", safe_bundle=bundle, constraints=["중복 체크 규칙은 유지", "선행 차단 규칙은 유지"])
    grounded = svc.build_grounded_business_rules(prepared, svc.extract_core_business_rules(prepared))
    retained = svc.build_retained_contracts(prepared, grounded)
    applied = svc.build_applied_templates(prepared, grounded, retained)
    primary = svc._primary_template(prepared, applied)

    assert primary is not None
    assert primary.template_id == "validation"


def test_rebuild_assistant_validation_sample_uses_validation_centered_outputs():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "validation_sample.java", "content": 'if (claim.status == "CLOSED" || claim.status == "CANCELLED") return "blocked"; if (claimAmount >= 3000000) return "limit"; if (repository.existsByCode(code)) return "dup"; repository.save(claim);'},
            {"name": "validation_sample.sql", "content": "SELECT status, claim_amount FROM TBL_001 WHERE claim_id = ?"},
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="검증 규칙이 많은 청구 조정 기능", safe_bundle=bundle, constraints=["중복 체크 규칙은 유지", "선행 차단 규칙은 유지"])
    )

    top_titles = [rule.title for rule in result.grounded_business_rules[:2]]
    assert any(token in " ".join(top_titles) for token in ("금액 한도", "중복 체크", "저장 전 차단", "선행"))
    assert top_titles[0] != "마감/취소 상태 조정 금지"
    assert "차단 조건" in result.one_line_conclusion or "검증 순서" in result.one_line_conclusion
    assert result.recommended_option is not None
    assert "검증" in result.recommended_option.name
    assert "상태 전이 중심" not in result.recommended_option.name
    assert "검증" in result.priority_split_items[0].item
    assert "검증" in result.execution_plan[0].goal
    assert "상태 전이 중심" not in result.one_line_conclusion


def test_rebuild_assistant_validation_sample_has_complete_structure_and_validation_contracts():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {
                "name": "validation_sample.java",
                "content": 'if (repository.existsByCode(code)) return "dup"; if (claim.status == "PENDING") return "blocked"; if (!requiredFlag) return "required"; repository.save(claim);',
            },
            {
                "name": "validation_sample.sql",
                "content": "SELECT status, count(1) FROM claim_adjustment WHERE claim_id = ?",
            },
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="검증 규칙이 많은 청구 조정 기능", safe_bundle=bundle, constraints=["중복 체크 규칙은 유지", "선행 차단 규칙은 유지"])
    )

    assert len(result.decision_items) >= 3
    assert {item.priority for item in result.priority_split_items} == {1, 2, 3}
    retained_items = [item.item for item in result.retained_contracts]
    assert len(retained_items) >= 2
    assert any("중복" in item for item in retained_items)
    assert any("저장 전 차단" in item or "검증 순서" in item or "선행 조건" in item for item in retained_items)
    assert not all("상태값" in item for item in retained_items)


def test_rebuild_assistant_access_control_sample_has_multiple_grounded_rules():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {
                "name": "access_control_sample.py",
                "content": 'if claim["claim_amount"] >= 10000000 and dept_code != "CLAIM_AUDIT": return "심사전담부서만 가능"; if user_role != "HQ_REVIEWER": return "본사 승인만 가능"; if urgent_flag == "Y" and approver_org != "HQ": return "본사 선승인 경로만 가능";',
            },
            {
                "name": "constraints.txt",
                "content": "심사팀 승인 한도는 유지\n예외 승인 경로는 분리 유지",
            },
            {
                "name": "schema.sql",
                "content": "CREATE TABLE insurance_claim (claim_id varchar(20), status varchar(20), claim_amount integer, dept_code varchar(20));",
            },
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="접근 제어 규칙이 많은 청구 조정 기능", safe_bundle=bundle, constraints=["심사팀 승인 한도는 유지", "예외 승인 경로는 분리 유지"])
    )

    assert len(result.grounded_business_rules) == 3
    rule_texts = [f"{rule.title} {rule.description}" for rule in result.grounded_business_rules[:3]]
    joined_rules = " ".join(rule_texts)
    has_amount_axis = any(token in joined_rules for token in ("1천만원", "고액", "금액", "전담 부서"))
    has_actor_axis = any(token in joined_rules for token in ("본사", "승인 주체", "부서", "HQ_REVIEWER", "권한 위임"))
    has_route_axis = any(token in joined_rules for token in ("선승인", "예외 승인", "처리 경로", "승인 요청", "통지"))
    assert sum((has_amount_axis, has_actor_axis, has_route_axis)) >= 2
    recommendation = result.recommended_option.selection_reason if result.recommended_option else ""
    priority_reason = result.priority_split_items[0].reason if result.priority_split_items else ""
    transition_backend = " ".join(result.recomposition_draft.backend)
    combined = f"{recommendation} {priority_reason} {transition_backend}"
    axes = sum(token in combined for token in ("권한", "부서", "승인 주체", "전담 부서"))
    assert axes >= 2
    assert "검증" not in result.one_line_conclusion
    assert "차단 조건" not in result.one_line_conclusion
    assert "저장 전" not in result.one_line_conclusion
    assert all("검증" not in item and "차단 조건" not in item and "저장 전" not in item for item in result.executive_summary_v2[:3])
    assert "검증" not in recommendation
    assert "차단 조건" not in recommendation
    assert "저장 전" not in recommendation
    assert all("검증" not in item.reason and "차단 조건" not in item.reason and "저장 전" not in item.reason for item in result.priority_split_items[:2])
    assert "상태 전이 계층" not in transition_backend
    assert "상태 전이 이후" not in " ".join(item.item for item in result.verification_checkpoints)
    assert all("상태 전이" not in item.statement for item in result.decision_items)
    verification_text = " ".join(item.item for item in result.verification_checkpoints)
    assert len(result.verification_checkpoints) >= 2
    assert "권한 위임 세부 범위" in verification_text
    assert any(token in verification_text for token in ("통지", "후속 처리", "예외 승인"))


def test_rebuild_assistant_access_control_sparse_sample_still_enriches_rules_and_verification():
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    prepared = svc.prepare_input(
        goal="접근제어",
        assets=RebuildAssetsPayload(
            source_code='if claim.amount >= 10000000:\n    if user.dept != "CLAIM_AUDIT":\n        raise PermissionError("승인 권한 없음")',
            sql_queries="SELECT * FROM claims WHERE amount >= 10000000 AND dept_code = 'CLAIM_AUDIT';",
        ),
        constraints=[],
    )
    result = svc.build_result(prepared)

    assert len(result.grounded_business_rules) == 3
    titles = [item.title for item in result.grounded_business_rules]
    assert "1천만원 이상 전담 부서 처리" in titles
    assert "권한 위임 가능 여부" in titles
    assert "승인 요청 및 처리 흐름" in titles
    assert len(result.verification_checkpoints) >= 2
    verification_text = " ".join(item.item for item in result.verification_checkpoints)
    assert "권한 위임 세부 범위" in verification_text
    assert any(token in verification_text for token in ("예외 승인", "통지", "후속 처리"))


def test_rebuild_assistant_state_transition_draft_starts_with_state_transition_axis():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy.jsp", "content": '<button>마감</button><c:if test="${status eq \'READY\'}">close</c:if>'},
            {
                "name": "state_transition_sample.java",
                "content": 'if ("Y".equals(order.getDeliveryHoldFlag())) return "blocked"; if ("EXPORT".equals(order.getOrderType())) { order.setStatus("REVIEW_REQUIRED"); }',
            },
            {"name": "state_transition_sample.sql", "content": "UPDATE orders SET status = 'REVIEW_REQUIRED' WHERE order_id = ?"},
            {"name": "schema.sql", "content": "CREATE TABLE orders (id bigint, status varchar(20), delivery_hold_flag char(1));"},
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="주문 관리 화면 현대화", safe_bundle=bundle, constraints=["주문 상태 코드는 유지"])
    )

    assert result.recomposition_draft.database
    assert "상태" in result.recomposition_draft.database[0]
    assert "저장 전 검증" not in result.recomposition_draft.database[0]
    assert all("저장 전 검증" not in item for item in result.recomposition_draft.database[:2])
    assert result.risks
    assert "상태 전이" in result.risks[0] or "처리 가능 상태" in result.risks[0]


def test_rebuild_assistant_state_transition_status_contract_keeps_input_and_result_statuses():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy.jsp", "content": '<button>마감</button><c:if test="${status eq \'READY\'}">close</c:if>'},
            {
                "name": "state_transition_sample.java",
                "content": 'if ("EXPORT".equals(order.getOrderType())) { order.setStatus("REVIEW_REQUIRED"); } if ("READY".equals(order.getStatus())) { order.setStatus("COMPLETED"); }',
            },
            {"name": "state_transition_sample.sql", "content": "UPDATE orders SET status = 'REVIEW_REQUIRED' WHERE order_id = ?; SELECT * FROM orders WHERE status IN ('PAID', 'READY', 'REVIEW_REQUIRED')"},
            {"name": "schema.sql", "content": "CREATE TABLE orders (id bigint, status varchar(20));"},
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="주문 관리 화면 현대화", safe_bundle=bundle, constraints=["주문 상태 코드는 유지"])
    )

    status_items = [item.item for item in result.retained_contracts if "status" in item.item.lower()]
    assert status_items
    joined = " ".join(status_items)
    assert "READY" in joined
    assert "REVIEW_REQUIRED" in joined
    assert "COMPLETED" in joined


def test_rebuild_assistant_state_transition_status_contract_accepts_ui_input_status_and_result_status():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy.jsp", "content": '<c:if test="${status eq \'READY\'}">close</c:if>'},
            {
                "name": "state_transition_sample.java",
                "content": 'if ("READY".equals(order.getStatus())) { order.setStatus("COMPLETED"); }',
            },
            {"name": "state_transition_sample.sql", "content": "UPDATE orders SET status = 'REVIEW_REQUIRED' WHERE order_id = ?"},
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(
            goal="상태전환",
            safe_bundle=bundle,
            constraints=["상태 코드는 유지"],
        )
    )

    status_items = [item.item for item in result.retained_contracts if "status" in item.item.lower()]
    assert status_items
    joined = " ".join(status_items)
    assert "READY" in joined
    assert "COMPLETED" in joined or "REVIEW_REQUIRED" in joined


def test_rebuild_assistant_state_transition_status_contract_accepts_equals_status_input():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {
                "name": "state_transition_sample.java",
                "content": 'if ("READY".equals(order.getStatus())) { order.setStatus("COMPLETED"); }',
            },
            {"name": "state_transition_sample.sql", "content": "UPDATE orders SET status = 'REVIEW_REQUIRED' WHERE order_id = ?"},
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="상태전환", safe_bundle=bundle, constraints=["상태 코드는 유지"])
    )

    status_items = [item.item for item in result.retained_contracts if "status" in item.item.lower()]
    assert status_items
    joined = " ".join(status_items)
    assert "READY" in joined
    assert "COMPLETED" in joined or "REVIEW_REQUIRED" in joined


def test_rebuild_assistant_claim_real_sample_stays_access_control_centered():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "claim_adjustment.html", "content": "<h1>Claim Adjustment</h1>"},
            {
                "name": "legacy_app.py",
                "content": """
if claim["status"] in ["CLOSED", "CANCELLED"]: return "조정 불가"
if claim["accident_type"] == "FRAUD" and user_role != "HQ_REVIEWER": return "본사 심사만 가능"
if claim["claim_amount"] >= 3000000 and user_role == "BRANCH_MANAGER": return "지점장 한도 초과"
if claim["claim_amount"] >= 10000000 and dept_code != "CLAIM_AUDIT": return "심사전담부서만 가능"
if claim["branch_code"] == "B99" and claim["is_urgent"] == "Y" and user_role == "BRANCH_MANAGER": return "특수지점 긴급건은 본사 선승인 필요"
                """,
            },
            {"name": "schema.sql", "content": "CREATE TABLE insurance_claim (claim_id varchar(20), status varchar(20), claim_amount integer, dept_code varchar(20));"},
            {"name": "query.sql", "content": "SELECT claim_id, status, claim_amount, dept_code FROM insurance_claim WHERE claim_id = ?"},
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(
            goal="청구 조정 기능을 현대적인 서비스 구조 재구성",
            safe_bundle=bundle,
            constraints=["기존 승인 상태 체계는 유지", "긴급 청구의 우선 처리 규칙은 변경 금지", "지점장 승인 한도와 심사팀 승인 한도는 유지"],
        )
    )

    summary = " ".join(result.executive_summary_v2)
    recommendation = result.recommended_option.selection_reason if result.recommended_option else ""
    priority = " ".join(item.reason for item in result.priority_split_items[:2])
    combined = " ".join([summary, result.one_line_conclusion, recommendation, priority])
    grounded_titles = [item.title for item in result.grounded_business_rules[:4]]
    retained_items = [item.item for item in result.retained_contracts[:4]]
    assert any(token in combined for token in ("권한", "부서", "승인 주체", "예외 승인"))
    assert "차단 조건" not in result.executive_summary_v2[0]
    assert "저장 전 검증" not in result.executive_summary_v2[0]
    assert "검증 순서" not in result.executive_summary_v2[0]
    assert "차단 조건" not in result.one_line_conclusion
    assert "저장 전 검증" not in result.one_line_conclusion
    assert "검증 순서" not in result.one_line_conclusion
    assert "차단 조건" not in recommendation
    assert "저장 전 검증" not in recommendation
    assert result.recommended_option is not None
    assert "권한 정책 중심" in result.recommended_option.name
    assert "금액 한도 검증" != grounded_titles[0]
    assert any(title in grounded_titles[:3] for title in ("지점장 300만원 한도", "B99 긴급건 본사 선승인", "FRAUD 본사 심사 전용"))
    assert len(result.retained_contracts) >= 2
    assert any("승인" in item or "심사" in item or "CLAIM_AUDIT" in item for item in retained_items[:2])
    assert not any("저장 전 차단 조건" in item or "선행 조건 확인과 검증 순서" in item for item in retained_items[:2])
    rendered = "\n".join(result.executive_summary_v2 + [result.one_line_conclusion] + grounded_titles + retained_items)
    assert "한도을" not in rendered


def test_rebuild_assistant_claim_real_sample_prefers_access_control_primary_template():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "claim_adjustment.html", "content": "<h1>Claim Adjustment</h1>"},
            {
                "name": "legacy_app.py",
                "content": """
if claim["status"] in ["CLOSED", "CANCELLED"]: return "조정 불가"
if claim["accident_type"] == "FRAUD" and user_role != "HQ_REVIEWER": return "본사 심사만 가능"
if claim["claim_amount"] >= 3000000 and user_role == "BRANCH_MANAGER": return "지점장 한도 초과"
if claim["claim_amount"] >= 10000000 and dept_code != "CLAIM_AUDIT": return "심사전담부서만 가능"
if claim["branch_code"] == "B99" and claim["is_urgent"] == "Y" and user_role == "BRANCH_MANAGER": return "특수지점 긴급건은 본사 선승인 필요"
                """,
            },
            {"name": "schema.sql", "content": "CREATE TABLE insurance_claim (claim_id varchar(20), status varchar(20), claim_amount integer, dept_code varchar(20));"},
            {"name": "query.sql", "content": "SELECT claim_id, status, claim_amount, dept_code FROM insurance_claim WHERE claim_id = ?"},
        ]
    )
    prepared = svc.prepare_safe_bundle_input(
        goal="청구 조정 기능을 현대적인 서비스 구조 재구성",
        safe_bundle=bundle,
        constraints=["기존 승인 상태 체계는 유지", "긴급 청구의 우선 처리 규칙은 변경 금지", "지점장 승인 한도와 심사팀 승인 한도는 유지"],
    )
    core_rules = svc.extract_core_business_rules(prepared)
    grounded = svc.build_grounded_business_rules(prepared, core_rules)
    retained = svc.build_retained_contracts(prepared, grounded)
    applied = svc.build_applied_templates(prepared, grounded, retained)
    primary = svc._primary_template(prepared, applied)

    assert primary is not None
    assert primary.template_id == "access_control"


def test_rebuild_assistant_access_control_status_contract_does_not_absorb_dept_codes():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {
                "name": "access_control_sample.py",
                "content": 'if claim["claim_amount"] >= 10000000 and dept_code in ("CLAIM_AUDIT", "HQ"): return "심사전담부서만 가능"',
            },
            {"name": "access_control_sample.sql", "content": "SELECT * FROM insurance_claim WHERE dept_code IN ('CLAIM_AUDIT', 'HQ')"},
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="접근제어", safe_bundle=bundle, constraints=["부서 승인 규칙은 유지"])
    )

    status_items = [item.item for item in result.retained_contracts if "status" in item.item.lower()]
    joined = " ".join(status_items)
    assert "CLAIM_AUDIT" not in joined
    assert "HQ" not in joined


def test_rebuild_assistant_selection_reason_does_not_list_three_axes():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "claim_adjustment.html", "content": "<h1>Claim Adjustment</h1>"},
            {"name": "legacy_app.py", "content": 'if claim["claim_amount"] >= 3000000 and user_role == "BRANCH_MANAGER": return "limit"; if claim["status"] in ["CLOSED", "CANCELLED"]: return "blocked"'},
            {"name": "schema.sql", "content": "CREATE TABLE insurance_claim (claim_id varchar(20), status varchar(20), claim_amount integer);"},
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="청구 조정 기능 현대화", safe_bundle=bundle, constraints=["지점장 한도는 유지"])
    )

    reason = result.recommended_option.selection_reason if result.recommended_option else ""
    axis_tokens = ["상태 전이", "권한", "금액 한도", "차단 조건", "검증 순서", "승인 주체"]
    assert sum(token in reason for token in axis_tokens) <= 2


def test_rebuild_assistant_output_avoids_status_prefix_and_duplicate_contract_words():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "access_control_sample.py", "content": 'if claim["claim_amount"] >= 10000000 and dept_code != "CLAIM_AUDIT": return "심사전담부서만 가능"'},
            {"name": "schema.sql", "content": "CREATE TABLE insurance_claim (claim_id varchar(20), status varchar(20), claim_amount integer, dept_code varchar(20));"},
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="접근 제어 규칙이 많은 청구 조정 기능", safe_bundle=bundle, constraints=["심사팀 승인 한도는 유지"])
    )
    rendered = svc.format_user_summary(result, scope_limited=False, needs_more_input=False)

    assert ".status 값" not in rendered
    assert "계약 계약" not in rendered
    assert "status 컬럼 컬럼" not in rendered
    assert "TBL_001status" not in rendered
    assert "처리을" not in rendered
    assert "검증를" not in rendered


def test_sql_analytics_classifies_risk_analysis_question():
    from mellow_link.modules.sql_analytics.service import SQLAnalyticsService

    svc = SQLAnalyticsService()

    assert svc.classify_question("최근 30일 환불률과 문의 증가율 기준으로 이상 징후를 알려줘") == "risk_analysis"


def test_sql_analytics_classifies_schema_like_question():
    from mellow_link.modules.sql_analytics.service import SQLAnalyticsService

    svc = SQLAnalyticsService()

    assert svc.classify_question("현재 데이터에 어떤 테이블이 있고 각 컬럼이 무엇인지 알려줘") == "schema_like"


def test_sql_analytics_formats_schema_like_summary_without_risk_claims():
    from mellow_link.modules.sql_analytics.service import SQLAnalyticsService

    svc = SQLAnalyticsService()
    formatted = svc.format_unsupported_summary(
        question="현재 데이터에 어떤 테이블이 있고 각 컬럼이 무엇인지 알려줘",
        intent="schema_like",
    )

    assert "리스크 분석 전용" in formatted
    assert "테이블/컬럼 조회" in formatted or "테이블/컬럼" in formatted
    assert "환불률" in formatted


def test_sql_analytics_analyze_question_skips_pipeline_for_unsupported(monkeypatch):
    from mellow_link.modules.sql_analytics.service import SQLAnalyticsService

    svc = SQLAnalyticsService()

    def fail_analyze(*args, **kwargs):
        raise AssertionError("pipeline should not run for schema_like question")

    monkeypatch.setattr(svc, "analyze", fail_analyze)
    result = svc.analyze_question("현재 데이터에 어떤 테이블이 있고 각 컬럼이 무엇인지 알려줘")

    assert result["intent"] == "schema_like"
    assert result["supported"] is False
    assert "리스크 분석 전용" in result["summary"]


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


def test_rebuild_todos_view_uses_module_mapping():
    from mellow_link.infra.run_events import build_todos_view

    raw_todos = [
        {"todo_id": "B1", "title": "입력 준비"},
        {"todo_id": "B2", "title": "레거시 분석"},
        {"todo_id": "B3", "title": "재구성 설계"},
        {"todo_id": "B4", "title": "초안 생성"},
        {"todo_id": "B5", "title": "결과 정리"},
    ]
    events = [
        {"type": "todo_started", "payload": {"todo_id": "B1"}},
        {"type": "todo_done", "payload": {"todo_id": "B1"}},
        {"type": "todo_started", "payload": {"todo_id": "B2"}},
        {"type": "todo_done", "payload": {"todo_id": "B2"}},
        {"type": "todo_started", "payload": {"todo_id": "B3"}},
        {"type": "todo_done", "payload": {"todo_id": "B3"}},
        {"type": "todo_started", "payload": {"todo_id": "B4"}},
        {"type": "todo_done", "payload": {"todo_id": "B4"}},
        {"type": "todo_started", "payload": {"todo_id": "B5"}},
        {"type": "todo_done", "payload": {"todo_id": "B5"}},
    ]

    todos_view = build_todos_view("rebuild_assistant", raw_todos, None, events, run_status="completed")

    assert [stage["title"] for stage in todos_view] == ["준비", "처리", "완료"]
    assert todos_view[0]["raw_todo_ids"] == ["B1", "B2"]
    assert todos_view[1]["raw_todo_ids"] == ["B3", "B4"]
    assert todos_view[2]["raw_todo_ids"] == ["B5"]
    assert [stage["status"] for stage in todos_view] == ["completed", "completed", "completed"]


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


def _run_research_abort_case(monkeypatch, abort_stage: str):
    from mellow_link import app_state
    from mellow_link.modules.research_assistant import runner as research_runner
    from mellow_link.routers.runs import RUN_CONTROL_STATE

    run_id = f"run_abort_{abort_stage}"
    temp_session_id = f"temp_{abort_stage}"
    events = []
    base_service = research_runner.ResearchAssistantService

    class InlineThread:
        def __init__(self, target=None, daemon=None, *args, **kwargs):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    class FakeLLM:
        def __init__(self):
            self.calls = 0
            self._current_model = "qwen3.5:9b"

        def get_model_for_mode(self, mode):
            return self._current_model

        async def generate(self, *args, **kwargs):
            self.calls += 1
            if abort_stage == "attempt_1" and self.calls == 1:
                RUN_CONTROL_STATE[run_id]["abort_requested"] = True
            if abort_stage == "attempt_2" and self.calls == 1:
                return SimpleNamespace(content="")
            return SimpleNamespace(
                content=(
                    "한 줄 결론\n- 구조는 명확하지만 MVP 범위 조정이 필요합니다.\n\n"
                    "핵심 요약\n- 규칙 엔진과 SQL 계층 분리는 타당합니다.\n"
                    "- 다만 AI 해석 레이어는 아직 범위가 넓고 구현 기준이 덜 정리되었습니다.\n"
                    "- 초기 단계에서는 규칙과 데이터 처리에 집중하는 것이 현실적입니다."
                )
            )

        def clear_context(self, context_id):
            return None

        async def unload_model(self):
            self._current_model = None

        async def cleanup_stale_models(self, current_model=None):
            return None

    class FakeService(base_service):
        def build_prompt(self, question: str, context_note: str = "", document_context: str = "") -> str:
            return "primary prompt"

        def build_reduced_prompt(self, question: str, context_note: str = "", document_context: str = "") -> str:
            if abort_stage == "attempt_2":
                RUN_CONTROL_STATE[run_id]["abort_requested"] = True
            return "reduced prompt"

        def format_user_summary(self, raw_summary: str, question: str, has_document_context: bool) -> str:
            if abort_stage == "finalize":
                RUN_CONTROL_STATE[run_id]["abort_requested"] = True
            return super().format_user_summary(raw_summary, question, has_document_context)

    def fake_emit(run_id_arg, event_type, payload, **kwargs):
        events.append({"run_id": run_id_arg, "type": event_type, "payload": payload})

    fake_llm = FakeLLM()
    RUN_CONTROL_STATE.clear()
    RUN_CONTROL_STATE[run_id] = {"paused": False, "abort_requested": False, "running": True}
    monkeypatch.setattr(research_runner.threading, "Thread", InlineThread)
    monkeypatch.setattr(research_runner, "emit_event", fake_emit)
    monkeypatch.setattr(research_runner, "ResearchAssistantService", FakeService)
    monkeypatch.setattr(app_state, "llm_service", fake_llm, raising=False)
    monkeypatch.setattr(app_state, "TEMP_CONTEXT_STORE", {temp_session_id: "document context"}, raising=False)

    research_runner.start_research_run(
        run_id=run_id,
        session_id="session-test",
        question="문서를 평가해줘",
        context_note="",
        temp_session_id=temp_session_id,
    )

    finished = [event for event in events if event["type"] == "run_finished"]
    assert len(finished) == 1
    return finished[0]["payload"], fake_llm.calls, events


def test_rebuild_assistant_runner_emits_structured_result(monkeypatch):
    from mellow_link import app_state
    from mellow_link.modules.rebuild_assistant import compat as rebuild_compat
    from mellow_link.modules.rebuild_assistant import runner as rebuild_runner

    events = []

    class InlineThread:
        def __init__(self, target=None, daemon=None, *args, **kwargs):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    def fake_emit(run_id_arg, event_type, payload, **kwargs):
        events.append({"run_id": run_id_arg, "type": event_type, "payload": payload})

    monkeypatch.setattr(rebuild_runner.threading, "Thread", InlineThread)
    monkeypatch.setattr(rebuild_runner, "emit_event", fake_emit)
    monkeypatch.setattr(app_state, "TEMP_CONTEXT_STORE", {"rebuild-temp": "--- [legacy.jsp] ---\n<% String sql = \"SELECT * FROM orders\"; %>"}, raising=False)

    rebuild_compat.start_rebuild_assistant_run_compat(
        run_id="run_rebuild_test",
        session_id="session-test",
        goal="이 JSP 주문 조회 화면을 React + REST API로 재구성해줘",
        assets=rebuild_compat.RebuildAssetsPayload(
            source_code="<% String sql = \"SELECT * FROM orders\"; %>",
            sql_queries="SELECT * FROM orders",
        ),
        constraints=["기존 DB 호환 유지"],
        temp_session_id="rebuild-temp",
    )

    finished = [event for event in events if event["type"] == "run_finished"]
    assert len(finished) == 1
    payload = finished[0]["payload"]
    judgment_logs = [
        event["payload"]
        for event in events
        if event["type"] == "log" and event["payload"].get("message") == "primary judgment selected"
    ]
    assert payload["success"] is True
    assert payload["module_id"] == "rebuild_assistant"
    assert payload["run_kind"] == "rebuild_plan"
    assert isinstance(payload["structured_result"]["analysis_summary"], list)
    assert isinstance(payload["structured_result"]["core_business_rules"], list)
    assert isinstance(payload["structured_result"]["recommended_directions"], list)
    assert isinstance(payload["structured_result"]["missing_context_details"], list)
    assert set(payload["structured_result"]["layer_reconstruction"].keys()) == {"database", "backend", "frontend"}
    assert set(payload["structured_result"]["extracted_rules"].keys()) == {"status_permissions", "search_filters", "save_validation"}
    assert payload["primary_judgment"] == payload["structured_result"]["primary_judgment"]
    assert payload["judgment_template_key"] == payload["structured_result"]["primary_judgment"]
    assert isinstance(payload["structured_result"]["pattern_candidates"], list)
    assert payload["polish_bundle"]["primary_judgment"] == payload["structured_result"]["primary_judgment"]
    assert payload["polish_bundle"]["original_result"]["primary_judgment"] == payload["structured_result"]["primary_judgment"]
    assert isinstance(payload["polish_bundle"]["polished_sections"], list)
    assert payload["polish_bundle"]["delivery_mode"] == "client_report"
    assert payload["polish_bundle"]["audience"] == "manager"
    assert payload["structured_result"]["report_purpose"]
    assert isinstance(payload["structured_result"]["report_scope"], list)
    assert isinstance(payload["structured_result"]["report_questions"], list)
    assert isinstance(payload["confidence"], float)
    assert len(judgment_logs) == 1
    assert judgment_logs[0]["primary_judgment"] == payload["structured_result"]["primary_judgment"]
    assert judgment_logs[0]["primary_judgment_reason"]
    assert isinstance(judgment_logs[0]["pattern_candidates"], list)


def test_rebuild_assistant_safe_bundle_runner_emits_anonymization_contract(monkeypatch):
    from mellow_link.modules.rebuild_assistant import runner as rebuild_runner
    from mellow_link.services.anonymization.bundle_builder import SafeBundleBuilder
    from mellow_link.services.anonymization.schemas import (
        AnonymizationAsset,
        CanonicalAnonymizedSource,
        MaskingLevel,
        StructureArtifact,
    )

    events = []

    class InlineThread:
        def __init__(self, target=None, daemon=None, *args, **kwargs):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    def fake_emit(run_id_arg, event_type, payload, **kwargs):
        events.append({"run_id": run_id_arg, "type": event_type, "payload": payload})

    bundle = SafeBundleBuilder().build(
        project_id="proj_runner_contract",
        masking_level=MaskingLevel.FULL,
        assets=[AnonymizationAsset(asset_id="asset_001", name="legacy.jsp", temp_file_id="temp_001", size=12)],
        canonical_sources=[
            CanonicalAnonymizedSource(
                asset_id="asset_001",
                level=MaskingLevel.FULL,
                language="jsp",
                content='class CLS_001 { function FUNC_001() { return "customer@example.com"; } }',
                replacement_stats={"class": 1, "function": 1},
            )
        ],
        structures=[StructureArtifact(asset_id="asset_001", level=MaskingLevel.FULL, extracted_from="canonical", nodes=[], edges=[])],
    )

    monkeypatch.setattr(rebuild_runner.threading, "Thread", InlineThread)
    monkeypatch.setattr(rebuild_runner, "emit_event", fake_emit)

    rebuild_runner.start_rebuild_assistant_safe_bundle_run(
        run_id="run_rebuild_safe_bundle_contract",
        session_id="session-test",
        goal="이 JSP 주문 조회 화면을 React + REST API로 재구성해줘",
        safe_bundle=bundle,
        constraints=["기존 DB 호환 유지"],
    )

    debug_event = next(event for event in events if event["type"] == "debug_anonymization_report")
    log_event = next(event for event in events if event["type"] == "log" and event["payload"].get("message") == "anonymization bundle ready")
    finished = next(event for event in events if event["type"] == "run_finished")

    assert debug_event["payload"]["policy_version"] == "safe_bundle_exposure_v0"
    assert "report_summary" in debug_event["payload"]
    assert "validation" in debug_event["payload"]
    assert "bundle_debug" in debug_event["payload"]
    assert "source_previews" in debug_event["payload"]
    assert log_event["payload"] == {
        "level": "info",
        "message": "anonymization bundle ready",
        "policy_version": "safe_bundle_exposure_v0",
        "masking_level": "FULL",
        "applied": True,
        "total_replacements": 2,
        "validation_passed": True,
    }
    assert "anonymization_summary" in finished["payload"]
    assert finished["payload"]["anonymization_summary"]["total_replacements"] == 2
    assert "source_previews" not in finished["payload"]
    assert "bundle_debug" not in finished["payload"]
    todo_ids = [event["payload"].get("todo_id") for event in events if event["type"] == "todo_started"]
    assert todo_ids == ["B1", "B2", "B3", "B4", "B5"]


def test_rebuild_assistant_polish_bundle_preserves_original_result_and_facts():
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    prepared = svc.prepare_input(
        goal="금액 구간과 한도 기준이 많은 승인 기능을 재구성해줘",
        assets=RebuildAssetsPayload(
            source_code="""
if (orderAmount <= 50000) return "AUTO";
if (orderAmount <= 300000) return "MANAGER";
if (amount > dailyLimit && amount <= 1000000) return "DIRECTOR";
            """,
            sql_queries="""
SELECT CASE
  WHEN order_amount <= 50000 THEN 'SMALL'
  WHEN order_amount <= 300000 THEN 'MEDIUM'
  ELSE 'LARGE'
END
FROM orders
WHERE order_amount > dailyLimit
            """,
        ),
    )
    result = svc.build_result(prepared)
    original = result.model_dump()
    bundle = svc.build_polish_bundle(result, audience="manager", delivery_mode="client_report")
    combined = "\n".join(section.polished_text for section in bundle.polished_sections)

    assert bundle.primary_judgment == result.primary_judgment
    assert bundle.template_judgment == (result.template_judgment or result.primary_judgment)
    assert bundle.structural_judgment == result.structural_judgment
    assert bundle.narrative_axis == result.narrative_axis
    assert bundle.feature_signal_mode == result.feature_signal_mode
    assert bundle.original_result == original
    assert "50000" in combined
    assert "300000" in combined
    assert any("50000" in fact or "300000" in fact for fact in bundle.preserved_facts)
    assert bundle.use_ai_rewrite is False


def test_rebuild_assistant_polish_bundle_removes_duplicate_and_particle_errors():
    from mellow_link.modules.rebuild_assistant.postprocess.service import StructuredResultPolishService
    from mellow_link.modules.rebuild_assistant.schemas import (
        ExecutionPlanWeek,
        GroundedBusinessRule,
        RecommendedOption,
        StructuredRebuildResult,
    )

    result = StructuredRebuildResult(
        primary_judgment="query_filter",
        one_line_conclusion="조회 조회 조건 분리을 통해 결과 목록 정합성를 유지해야 합니다.",
        grounded_business_rules=[
            GroundedBusinessRule(
                title="결과 목록 구성 규칙 규칙",
                description="조회 조회 API가 정합성를 깨지 않도록 해야 합니다.",
            )
        ],
        recommended_option=RecommendedOption(
            name="옵션 A. 조회 조회 API 구조",
            structure_summary="조회 조건 분리을 유지합니다.",
            selection_reason="조회 조회 조건을 우선 정리합니다.",
        ),
        execution_plan=[ExecutionPlanWeek(week_label="1주차", goal="조회 조회 정책 분리을 정리", tasks=["정합성를 확인"])],
    )

    bundle = StructuredResultPolishService().polish_result(result)
    combined = "\n".join(section.polished_text for section in bundle.polished_sections)

    assert "규칙 규칙" not in combined
    assert "조회 조회" not in combined
    assert "정합성를" not in combined
    assert "분리을" not in combined


def test_rebuild_assistant_polish_bundle_creates_audience_and_delivery_variants():
    from mellow_link.modules.rebuild_assistant.postprocess.service import StructuredResultPolishService
    from mellow_link.modules.rebuild_assistant.schemas import StructuredRebuildResult

    bundle = StructuredResultPolishService().polish_result(
        StructuredRebuildResult(
            primary_judgment="workflow",
            one_line_conclusion="승인 트리거와 승인 단계 구조를 기준으로 승인 흐름을 분리해야 합니다.",
        ),
        audience="client",
        delivery_mode="proposal_appendix",
    )
    section = next(item for item in bundle.polished_sections if item.section_key == "one_line_conclusion")

    assert set(section.audience_variants.keys()) == {"developer", "manager", "client"}
    assert set(section.delivery_variants.keys()) == {"internal_review", "client_report", "proposal_appendix"}
    assert section.audience_variants["developer"].startswith("참고 판단:") or section.audience_variants["developer"].startswith("구현 기준:")
    assert section.delivery_variants["proposal_appendix"].startswith("부록 기준:")
    assert "승인 단계 구조" in section.delivery_variants["client_report"]


def test_rebuild_assistant_polish_bundle_keeps_pattern_purity():
    from mellow_link.modules.rebuild_assistant.postprocess.service import StructuredResultPolishService
    from mellow_link.modules.rebuild_assistant.schemas import StructuredRebuildResult

    query_bundle = StructuredResultPolishService().polish_result(
        StructuredRebuildResult(
            primary_judgment="query_filter",
            one_line_conclusion="조회 조건과 정렬 기준을 분리해야 합니다.",
        )
    )
    amount_bundle = StructuredResultPolishService().polish_result(
        StructuredRebuildResult(
            primary_judgment="amount_threshold",
            one_line_conclusion="금액 구간과 한도 경계를 기준으로 처리 정책을 나눠야 합니다.",
        )
    )
    workflow_bundle = StructuredResultPolishService().polish_result(
        StructuredRebuildResult(
            primary_judgment="workflow",
            one_line_conclusion="승인 단계 구조와 예외 처리 흐름을 분리해야 합니다.",
        )
    )

    assert not query_bundle.warnings
    assert not amount_bundle.warnings
    assert not workflow_bundle.warnings


def test_rebuild_assistant_polish_bundle_uses_narrative_axis_for_pattern_warnings():
    from mellow_link.modules.rebuild_assistant.postprocess.service import StructuredResultPolishService
    from mellow_link.modules.rebuild_assistant.schemas import StructuredRebuildResult

    bundle = StructuredResultPolishService().polish_result(
        StructuredRebuildResult(
            primary_judgment="query_filter",
            template_judgment="query_filter",
            structural_judgment="refactor",
            narrative_axis="workflow",
            one_line_conclusion="승인 흐름은 권한 정책 중심 모듈형 구조보다 승인 단계 구조를 기준으로 정리하는 편이 적절합니다.",
        )
    )

    assert bundle.primary_judgment == "query_filter"
    assert bundle.narrative_axis == "workflow"
    assert any("workflow 문서에 금지 표현이 남아 있습니다" in warning for warning in bundle.warnings)


def test_rebuild_assistant_accounting_extension_moving_average_pipeline():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_service.java", "content": "if (policy.equals(\"moving average\")) { return calculateFx(); }"},
            {"name": "accounting_payload.json", "content": _accounting_payload_json(method="MOVING_AVERAGE")},
        ]
    )

    prepared = svc.prepare_safe_bundle_input(goal="외화 회계 계산이 있는 레거시 기능을 재구성", safe_bundle=bundle, constraints=["회계 정책은 유지"])
    result = svc.build_result(prepared)
    accounting = result.extensions["accounting"]

    assert accounting["calculation_status"]["can_calculate"] is True
    assert accounting["calculation_status"]["reason"] == "all required inputs present"
    assert accounting["fx_calculation"]["realized_gain_loss_krw"] == 22500
    assert "이동평균법" in accounting["summary_sentence"]
    assert any("transaction" in (step.get("source_tags") or []) for step in accounting["fx_calculation"]["detail_steps"])
    assert result.report_purpose == "외환 거래의 환차손익을 계산하고, 적용된 회계 방식과 전표 정합성을 함께 검토하기 위한 보고서입니다."
    assert result.report_scope == ["외화 거래 데이터", "환율 데이터", "회계 정책", "전표 검토 결과"]
    assert result.report_questions == [
        "이 거래에서 환차익 또는 환차손은 얼마인가?",
        "어떤 계산 방식이 적용되었는가?",
        "전표와 계산 결과는 일치하는가?",
    ]


def test_rebuild_assistant_accounting_extension_fifo_policy_changes_result():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_service.java", "content": "if (mode.equals(\"FIFO\")) { return calculateFx(); }"},
            {"name": "accounting_payload.json", "content": _accounting_payload_json(method="FIFO")},
        ]
    )

    result = svc.build_result(svc.prepare_safe_bundle_input(goal="외화 회계 계산이 있는 레거시 기능을 재구성", safe_bundle=bundle, constraints=[]))
    accounting = result.extensions["accounting"]

    assert accounting["fx_calculation"]["method"] == "FIFO"
    assert accounting["fx_calculation"]["realized_gain_loss_krw"] == 25000


def test_rebuild_assistant_accounting_extension_missing_exchange_rates_fails_explicitly():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_service.java", "content": "calculateFx();"},
            {"name": "accounting_payload.json", "content": _accounting_payload_json(include_exchange_rates=False)},
        ]
    )

    result = svc.build_result(svc.prepare_safe_bundle_input(goal="외화 회계 계산이 있는 레거시 기능을 재구성", safe_bundle=bundle, constraints=[]))
    accounting = result.extensions["accounting"]

    assert accounting["calculation_status"]["can_calculate"] is False
    assert accounting["calculation_status"]["blocking_issue"] == "missing required inputs: exchange_rates"
    assert "회계 계산을 수행할 수 없습니다." in accounting["summary_sentence"]
    assert "환율 데이터가 누락" in accounting["summary_sentence"]
    assert result.report_purpose == "외환 거래의 환차손익을 계산하고, 적용된 회계 방식과 전표 정합성을 함께 검토하기 위한 보고서입니다."
    assert result.report_purpose != accounting["summary_sentence"]
    assert result.report_questions


def test_rebuild_assistant_accounting_success_rewrites_top_narrative():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_service.java", "content": "if (policy.equals(\"moving average\")) { return calculateFx(); }"},
            {"name": "accounting_payload.json", "content": _accounting_payload_json(method="MOVING_AVERAGE")},
        ]
    )

    result = svc.build_result(svc.prepare_safe_bundle_input(goal="외화 회계 계산이 있는 레거시 기능을 재구성", safe_bundle=bundle, constraints=[]))
    summary_text = " ".join(result.executive_summary_v2)
    option_text = f"{result.recommended_option.name if result.recommended_option else ''} {result.recommended_option.structure_summary if result.recommended_option else ''}"
    execution_text = " ".join(f"{week.goal} {' '.join(week.tasks)}" for week in result.execution_plan)
    combined = " ".join([result.one_line_conclusion, summary_text, option_text, execution_text])

    assert "이동평균법" in combined
    assert "22,500원" in combined
    assert "전표 검토 결과" in summary_text or "전표 검토는 입력 부족" in summary_text or "전표 검토 결과 차변·대변" in summary_text
    assert "단계적으로 분리" not in combined
    assert "검증 규칙 중심 모듈형 구조" not in combined
    assert "핵심 규칙과 유지 계약을 같은 실행 계획 안에서 고정" not in combined
    assert result.recommended_option is not None
    assert result.recommended_option.name == "옵션 A. 현재 회계 방식 유지 및 입력 통제 강화"
    assert all("API" not in week.goal and "화면" not in week.goal and "모듈" not in week.goal for week in result.execution_plan)


def test_rebuild_assistant_accounting_failure_rewrites_top_narrative():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_service.java", "content": "calculateFx();"},
            {"name": "accounting_payload.json", "content": _accounting_payload_json(include_exchange_rates=False)},
        ]
    )

    result = svc.build_result(svc.prepare_safe_bundle_input(goal="외화 회계 계산이 있는 레거시 기능을 재구성", safe_bundle=bundle, constraints=[]))
    summary_text = " ".join(result.executive_summary_v2)
    option_text = f"{result.recommended_option.name if result.recommended_option else ''} {result.recommended_option.structure_summary if result.recommended_option else ''}"
    execution_text = " ".join(f"{week.goal} {' '.join(week.tasks)}" for week in result.execution_plan)
    combined = " ".join([result.one_line_conclusion, summary_text, option_text, execution_text])

    assert "회계 계산을 수행할 수 없습니다" in combined
    assert "환율 데이터 누락" in combined
    assert "22,500원" not in combined
    assert "단계적으로 분리" not in combined
    assert "검증 규칙 중심 모듈형 구조" not in combined
    assert result.recommended_option is not None
    assert result.recommended_option.name == "옵션 A. 누락 입력 보완 후 동일 방식으로 재계산"
    assert any("누락 입력" in week.goal or any("누락 입력" in task for task in week.tasks) for week in result.execution_plan)


def test_rebuild_assistant_accounting_warning_rewrites_top_narrative():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    payload = """
{
  "strict": false,
  "transactions": [
    {"tx_id": "TX001", "tx_type": "BUY_FX", "occurred_at": "2026-03-01", "currency": "USD", "amount_fc": 100, "fx_account_id": "USD_MAIN"},
    {"tx_id": "TX002", "tx_type": "SELL_FX", "occurred_at": "2026-03-01", "currency": "USD", "amount_fc": 50, "fx_account_id": "USD_MAIN"}
  ],
  "exchange_rates": [
    {"currency": "USD", "rate_date": "2026-03-01", "rate": 1200},
    {"currency": "USD", "rate_date": "2026-03-01", "rate": 1210}
  ],
  "vouchers": [],
  "account_mappings": [],
  "policies": [
    {"policy_id": "P001", "fx_cost_method": "MOVING_AVERAGE", "effective_from": "2026-01-01", "version": 1}
  ]
}
"""
    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_service.java", "content": "calculateFx();"},
            {"name": "accounting_payload.json", "content": payload},
        ]
    )

    result = svc.build_result(svc.prepare_safe_bundle_input(goal="외화 회계 계산", safe_bundle=bundle, constraints=[]))
    summary_text = " ".join(result.executive_summary_v2)
    option_text = f"{result.recommended_option.name if result.recommended_option else ''} {result.recommended_option.structure_summary if result.recommended_option else ''}"
    execution_text = " ".join(f"{week.goal} {' '.join(week.tasks)}" for week in result.execution_plan)
    combined = " ".join([result.one_line_conclusion, summary_text, option_text, execution_text])

    assert result.extensions["accounting"]["calculation_status"]["can_calculate"] is True
    assert "검토용 초안" in combined
    assert "복수 환율" in combined
    assert "이동평균법" in combined
    assert "단계적으로 분리" not in combined
    assert "검증 규칙 중심 모듈형 구조" not in combined
    assert result.recommended_option is not None
    assert result.recommended_option.name == "옵션 A. 현재 계산 결과를 초안으로 유지하고 입력 보완"


@pytest.mark.parametrize(
    ("goal", "assets", "expected_judgment", "expected_purpose"),
    [
        (
            "조회 조건과 필터 규칙이 많은 화면을 재구성해줘",
            {
                "source_code": "const page = req.query.page; const sort = req.query.sort; const status = req.query.status;",
                "sql_queries": "SELECT * FROM requests WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            },
            "query_filter",
            "조회 조건, 필터 조합, 정렬 및 결과 구성 규칙을 분석하기 위한 보고서입니다.",
        ),
        (
            "다단계 승인 흐름이 있는 요청 기능을 재구성해줘",
            {
                "source_code": 'if (approvalStep == 1 && approverRole == "TEAM_MANAGER") { approve(); } if (approvalStep == 2 && approverRole == "FINANCE_MANAGER") { reject(); }',
            },
            "workflow",
            "승인 트리거, 승인 단계, 예외 처리 흐름을 분석하기 위한 보고서입니다.",
        ),
        (
            "저장 전 차단 조건이 많은 등록 화면을 재구성해줘",
            {
                "source_code": "if (!name) throw invalid; if (existsDuplicate(code)) throw duplicate; save();",
            },
            "validation",
            "입력 검증, 저장 전 차단 조건, 예외 처리 기준을 분석하기 위한 보고서입니다.",
        ),
    ],
)
def test_rebuild_assistant_general_report_purpose_follows_primary_judgment(goal, assets, expected_judgment, expected_purpose):
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    prepared = svc.prepare_input(goal=goal, assets=RebuildAssetsPayload(**assets))
    result = svc.build_result(prepared)

    assert result.primary_judgment == expected_judgment
    assert result.report_purpose == expected_purpose
    assert result.report_scope
    assert result.report_questions


def test_rebuild_assistant_report_purpose_does_not_echo_raw_user_question():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    goal = "이 거래에서 환차익이 얼마인지 알고 싶다"
    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_service.java", "content": "if (policy.equals(\"moving average\")) { return calculateFx(); }"},
            {"name": "accounting_payload.json", "content": _accounting_payload_json(method="MOVING_AVERAGE")},
        ]
    )

    result = svc.build_result(svc.prepare_safe_bundle_input(goal=goal, safe_bundle=bundle, constraints=[]))

    assert goal not in result.report_purpose
    assert all(goal not in item for item in result.report_questions)


def test_rebuild_assistant_report_purpose_follows_narrative_axis_for_claim_and_amount_samples():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()

    claim_sample = MELLOW_LINK_ROOT / "modules" / "rebuild_assistant" / "samples" / "02. python_claim_adjustment_case_01"
    claim_bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": path.name, "content": path.read_text(encoding="utf-8")}
            for path in claim_sample.iterdir()
            if path.name.lower() not in {"readme.md", "goal.txt", "constraints.txt"}
        ]
    )
    claim_constraints = [line.strip() for line in claim_sample.joinpath("constraints.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    claim_goal = claim_sample.joinpath("goal.txt").read_text(encoding="utf-8").strip()
    claim_result = svc.build_result(
        svc.prepare_safe_bundle_input(goal=claim_goal, safe_bundle=claim_bundle, constraints=claim_constraints)
    )

    amount_sample = MELLOW_LINK_ROOT / "modules" / "rebuild_assistant" / "samples" / "04. amount_limit"
    amount_bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": path.name, "content": path.read_text(encoding="utf-8")}
            for path in amount_sample.iterdir()
        ]
    )
    amount_result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="금액 한도형 샘플", safe_bundle=amount_bundle, constraints=[])
    )

    assert claim_result.report_purpose == "권한 체계, 승인 주체, 조직별 처리 범위를 분석하기 위한 보고서입니다."
    assert amount_result.report_purpose == "금액 기준, 한도 정책, 경계 조건을 분석하기 위한 보고서입니다."


def test_rebuild_assistant_rca_exception_sample_keeps_single_workflow_narrative():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    sample_dir = MELLOW_LINK_ROOT / "modules" / "rebuild_assistant" / "samples" / "00. rca_exception_case_01"
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": path.name, "content": path.read_text(encoding="utf-8")}
            for path in sample_dir.iterdir()
            if path.name.lower() not in {"readme.md", "goal.txt", "constraints.txt"}
        ]
    )
    goal = sample_dir.joinpath("goal.txt").read_text(encoding="utf-8").strip()
    constraints = [line.strip() for line in sample_dir.joinpath("constraints.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    result = svc.build_result(
        svc.prepare_safe_bundle_input(goal=goal, safe_bundle=bundle, constraints=constraints)
    )

    retained_items = [item.item for item in result.retained_contracts[:3]]
    assert result.primary_judgment == "workflow"
    assert result.report_purpose == "승인 트리거, 승인 단계, 예외 처리 흐름을 분석하기 위한 보고서입니다."
    assert "조회 조건과 결과 구성을 별도 조회 모델로 분리" not in result.one_line_conclusion
    assert any(title in [rule.title for rule in result.grounded_business_rules[:4]] for title in ("의사결정 분기 조건", "예외 처리 흐름", "승인 단계 구조"))
    assert retained_items
    assert not any("조회 조건 파라미터 계약" in item or "정렬과 페이징 기본값 계약" in item for item in retained_items)
    assert any("승인" in item or "단계" in item for item in retained_items)


def test_rebuild_assistant_accounting_extension_voucher_review_input_missing_is_not_treated_as_no():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    payload = _accounting_payload_json().replace('"vouchers": [', '"vouchers_disabled": [').replace('"account_mappings": [', '"account_mappings_disabled": [')
    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_service.java", "content": "calculateFx();"},
            {"name": "accounting_payload.json", "content": payload},
        ]
    )

    result = svc.build_result(svc.prepare_safe_bundle_input(goal="전표 입력이 빠진 외화 회계 기능", safe_bundle=bundle, constraints=[]))
    accounting = result.extensions["accounting"]
    polish_bundle = svc.build_polish_bundle(result, audience="manager", delivery_mode="client_report")
    voucher_section = next(section for section in polish_bundle.polished_sections if section.section_key == "voucher_review")

    assert accounting["voucher_review"]["status"] == "input_missing"
    assert accounting["voucher_review"]["balance_ok"] is None
    assert accounting["voucher_review"]["policy_consistent"] is None
    assert "전표 데이터와 계정 매핑이 없어 전표 검토를 수행할 수 없습니다." in accounting["voucher_review"]["failure_reason"]
    assert "차변/대변 균형: 검토 불가" in voucher_section.polished_text
    assert "정책 일치: 검토 불가" in voucher_section.polished_text


def test_rebuild_assistant_accounting_extension_strict_mode_blocks_ambiguous_rate_but_non_strict_warns():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    payload = """
{
  "strict": true,
  "transactions": [
    {"tx_id": "TX001", "tx_type": "BUY_FX", "occurred_at": "2026-03-01", "currency": "USD", "amount_fc": 100, "fx_account_id": "USD_MAIN"},
    {"tx_id": "TX002", "tx_type": "SELL_FX", "occurred_at": "2026-03-01", "currency": "USD", "amount_fc": 50, "fx_account_id": "USD_MAIN"}
  ],
  "exchange_rates": [
    {"currency": "USD", "rate_date": "2026-03-01", "rate": 1200},
    {"currency": "USD", "rate_date": "2026-03-01", "rate": 1210}
  ],
  "vouchers": [],
  "account_mappings": [],
  "policies": [
    {"policy_id": "P001", "fx_cost_method": "MOVING_AVERAGE", "effective_from": "2026-01-01", "version": 1}
  ]
}
"""
    svc = RebuildAssistantService()
    strict_bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_service.java", "content": "calculateFx();"},
            {"name": "accounting_payload.json", "content": payload},
        ]
    )
    strict_result = svc.build_result(svc.prepare_safe_bundle_input(goal="외화 회계 계산", safe_bundle=strict_bundle, constraints=[]))
    strict_accounting = strict_result.extensions["accounting"]

    non_strict_bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_service.java", "content": "calculateFx();"},
            {"name": "accounting_payload.json", "content": payload.replace('"strict": true', '"strict": false')},
        ]
    )
    non_strict_result = svc.build_result(svc.prepare_safe_bundle_input(goal="외화 회계 계산", safe_bundle=non_strict_bundle, constraints=[]))
    non_strict_accounting = non_strict_result.extensions["accounting"]

    assert strict_accounting["calculation_status"]["can_calculate"] is False
    assert "ambiguous exchange rate" in strict_accounting["calculation_status"]["blocking_issue"]
    assert non_strict_accounting["calculation_status"]["can_calculate"] is True
    assert any("복수 환율" in warning for warning in non_strict_accounting["fx_calculation"]["warnings"])


def test_rebuild_assistant_accounting_extension_voucher_review_detects_mismatch():
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    payload = _accounting_payload_json().replace('"amount_krw": 210000', '"amount_krw": 209000')
    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_service.java", "content": "calculateFx();"},
            {"name": "accounting_payload.json", "content": payload},
        ]
    )

    result = svc.build_result(svc.prepare_safe_bundle_input(goal="전표 검토가 필요한 외화 기능", safe_bundle=bundle, constraints=[]))
    accounting = result.extensions["accounting"]

    assert accounting["voucher_review"]["status"] == "completed"
    assert accounting["voucher_review"]["mismatches"]


def test_rebuild_assistant_accounting_result_package_and_polish_bundle_include_accounting_sections():
    from datetime import datetime, timezone

    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
    from mellow_link.routers.projects import _result_package_markdown, build_result_package

    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_service.java", "content": "if (mode.equals(\"moving average\")) { calculateFx(); }"},
            {"name": "accounting_payload.json", "content": _accounting_payload_json(method="MOVING_AVERAGE")},
        ]
    )
    result = svc.build_result(svc.prepare_safe_bundle_input(goal="외화 회계 계산이 있는 레거시 기능을 재구성", safe_bundle=bundle, constraints=[]))
    polish_bundle = svc.build_polish_bundle(result, audience="manager", delivery_mode="client_report")

    project = SimpleNamespace(
        id="proj_accounting",
        project_name="회계 MVP",
        client_name="ACME",
        template_key="rebuild_assistant",
        status="completed",
        created_at=datetime.now(timezone.utc),
    )
    pkg = build_result_package(
        project,
        {"status": "completed", "run_id": "run_accounting"},
        result,
        assets=[],
        polish_bundle=polish_bundle.model_dump(),
        app_version="0.1.0",
    )
    markdown = _result_package_markdown(pkg)

    assert pkg["accounting"]["calculation_status"]["can_calculate"] is True
    assert pkg["report_purpose"] == "외환 거래의 환차손익을 계산하고, 적용된 회계 방식과 전표 정합성을 함께 검토하기 위한 보고서입니다."
    assert pkg["report_scope"] == ["외화 거래 데이터", "환율 데이터", "회계 정책", "전표 검토 결과"]
    assert len(pkg["report_questions"]) == 3
    assert pkg["polish_bundle"]["audience"] == "manager"
    assert pkg["polish_bundle"]["delivery_mode"] == "client_report"
    assert "### 문서 맥락" in markdown
    assert "외환 거래의 환차손익을 계산하고, 적용된 회계 방식과 전표 정합성을 함께 검토하기 위한 보고서입니다." in markdown
    assert "### 회계 참고" in markdown
    assert "외화 계산 상태" in markdown
    assert any(section.section_key == "accounting_summary" for section in polish_bundle.polished_sections)
    assert any(section.section_key == "report_purpose" for section in polish_bundle.polished_sections)
    assert any(fact in ("22500", "22,500") for fact in polish_bundle.preserved_facts)
    assert "검증 규칙 중심 모듈형 구조" not in markdown
    assert "단계적으로 분리" not in markdown


def test_rebuild_assistant_accounting_invalid_schema_failure_is_humanized_in_result_package():
    from datetime import datetime, timezone

    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
    from mellow_link.routers.projects import _result_package_markdown, build_result_package

    invalid_payload = """
{
  "strict": true,
  "transactions": [
    {"tx_id": "T1", "tx_type": "BUY_FX", "currency": "USD", "amount_fc": 100, "rate": 1200}
  ],
  "exchange_rates": [
    {"currency": "USD", "rate_date": "2026-03-01", "rate": 1200}
  ],
  "vouchers": [],
  "account_mappings": [],
  "policies": [
    {"policy_id": "P001", "fx_cost_method": "MOVING_AVERAGE", "effective_from": "2026-01-01", "version": 1}
  ]
}
"""
    svc = RebuildAssistantService()
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_context.txt", "content": "accounting failure sample"},
            {"name": "accounting_payload.json", "content": invalid_payload},
        ]
    )
    result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="전산회계 입력 검토", safe_bundle=bundle, constraints=[])
    )
    pkg = build_result_package(
        SimpleNamespace(
            id="proj_invalid_accounting",
            project_name="invalid accounting payload",
            client_name="ACME",
            template_key="rebuild_assistant",
            status="completed",
            created_at=datetime.now(timezone.utc),
        ),
        {"status": "completed", "run_id": "run_invalid_accounting"},
        result,
        assets=[],
        polish_bundle=svc.build_polish_bundle(result, audience="manager", delivery_mode="client_report").model_dump(),
        app_version="0.1.0",
    )
    markdown = _result_package_markdown(pkg)

    assert "거래일(occurred_at) 입력이 누락되었습니다." in markdown
    assert "invalid accounting payload schema" not in markdown


def test_rebuild_assistant_success_full_result_package_hides_placeholders_and_humanizes_accounting():
    from datetime import datetime, timezone

    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
    from mellow_link.routers.projects import _result_package_markdown, build_result_package

    sample_dir = MELLOW_LINK_ROOT / "modules" / "rebuild_assistant" / "samples" / "01_success_full"
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_context.txt", "content": sample_dir.joinpath("legacy_context.txt").read_text(encoding="utf-8")},
            {"name": "accounting_payload.json", "content": sample_dir.joinpath("accounting_payload.json").read_text(encoding="utf-8")},
        ]
    )

    svc = RebuildAssistantService()
    result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="전산회계 MVP 기능을 재구성", safe_bundle=bundle, constraints=[])
    )
    pkg = build_result_package(
        SimpleNamespace(
            id="proj_success_fx",
            project_name="success full",
            client_name="ACME",
            template_key="rebuild_assistant",
            status="completed",
            created_at=datetime.now(timezone.utc),
        ),
        {"status": "completed", "run_id": "run_success_fx"},
        result,
        assets=[],
        polish_bundle=svc.build_polish_bundle(result, audience="manager", delivery_mode="client_report").model_dump(),
        app_version="0.1.0",
    )
    markdown = _result_package_markdown(pkg)

    assert "## 핵심 업무 규칙\n- ready" not in markdown
    assert "## 유지해야 할 계약\n- ready" not in markdown
    assert "all required inputs present" not in markdown
    assert "MOVING_AVERAGE" not in markdown
    assert "voucher_review requires vouchers and account_mappings" not in markdown
    assert "account 기능" not in markdown
    assert "회계 기능" in markdown
    assert "### 문서 맥락" in markdown
    assert "외환 거래의 환차손익을 계산하고, 적용된 회계 방식과 전표 정합성을 함께 검토하기 위한 보고서입니다." in markdown
    assert "필수 입력이 모두 제공되었습니다." in markdown
    assert "이동평균법" in markdown
    assert "환차익은 22,500원입니다." in markdown
    assert "전표 검토 상태: 완료" in markdown
    assert "차변/대변 균형: 아니오" in markdown
    assert "정책 일치: 아니오" in markdown
    assert "입니다. 입니다." not in markdown
    assert "습니다.와" not in markdown

    statements = [item["statement"] for item in pkg["decision_items"]]
    assert statements
    assert len(statements) == len(set(statements))


def test_rebuild_assistant_success_full_accounting_overrides_lower_sections():
    from datetime import datetime, timezone

    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
    from mellow_link.routers.projects import _result_package_markdown, build_result_package

    sample_dir = MELLOW_LINK_ROOT / "modules" / "rebuild_assistant" / "samples" / "01_success_full"
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_context.txt", "content": sample_dir.joinpath("legacy_context.txt").read_text(encoding="utf-8")},
            {"name": "accounting_payload.json", "content": sample_dir.joinpath("accounting_payload.json").read_text(encoding="utf-8")},
        ]
    )

    svc = RebuildAssistantService()
    result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="전산회계 MVP 기능을 재구성", safe_bundle=bundle, constraints=[])
    )
    pkg = build_result_package(
        SimpleNamespace(
            id="proj_success_fx_lower",
            project_name="success full",
            client_name="ACME",
            template_key="rebuild_assistant",
            status="completed",
            created_at=datetime.now(timezone.utc),
        ),
        {"status": "completed", "run_id": "run_success_fx_lower"},
        result,
        assets=[],
        polish_bundle=svc.build_polish_bundle(result, audience="manager", delivery_mode="client_report").model_dump(),
        app_version="0.1.0",
    )
    markdown = _result_package_markdown(pkg)

    assert any(rule.title == "적용 회계 방식" for rule in result.grounded_business_rules)
    assert any("환차손익은 이동평균법 기준으로 계산됩니다." in rule.description for rule in result.grounded_business_rules)
    assert any("환율 기준 계약" in item.item for item in result.retained_contracts)
    assert any("회계 정책 적용 기준 계약" in item.item for item in result.retained_contracts)
    assert result.recomposition_draft.database
    assert result.recomposition_draft.backend
    assert result.recomposition_draft.frontend
    assert not any("API 분리" in item or "모듈형 구조" in item for item in result.recomposition_draft.database + result.recomposition_draft.backend + result.recomposition_draft.frontend)
    assert "직접 확인된 핵심 업무 규칙이 없습니다." not in markdown
    assert "직접 확인된 유지 계약이 없습니다." not in markdown
    assert "V1 전표의 차변/대변이 일치하지 않습니다." in markdown


def test_rebuild_assistant_failure_missing_exchange_rates_sample_uses_humanized_failure_narrative():
    from datetime import datetime, timezone

    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
    from mellow_link.routers.projects import _result_package_markdown, build_result_package

    sample_dir = MELLOW_LINK_ROOT / "modules" / "rebuild_assistant" / "samples" / "02_failure_missing_exchange_rates"
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_context.txt", "content": sample_dir.joinpath("legacy_context.txt").read_text(encoding="utf-8")},
            {"name": "accounting_payload.json", "content": sample_dir.joinpath("accounting_payload.json").read_text(encoding="utf-8")},
        ]
    )

    svc = RebuildAssistantService()
    result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="전산회계 MVP 기능을 재구성", safe_bundle=bundle, constraints=[])
    )
    pkg = build_result_package(
        SimpleNamespace(
            id="proj_failure_fx",
            project_name="failure missing exchange rates",
            client_name="ACME",
            template_key="rebuild_assistant",
            status="completed",
            created_at=datetime.now(timezone.utc),
        ),
        {"status": "completed", "run_id": "run_failure_fx"},
        result,
        assets=[],
        polish_bundle=svc.build_polish_bundle(result, audience="manager", delivery_mode="client_report").model_dump(),
        app_version="0.1.0",
    )
    markdown = _result_package_markdown(pkg)

    assert "환율 데이터 누락입니다." in markdown
    assert "환율 데이터가 누락되었습니다." in markdown
    assert "입니다. 입니다." not in markdown
    assert "습니다.와" not in markdown
    assert "단계적으로 분리" not in markdown
    assert "검증 규칙 중심 모듈형 구조" not in markdown


def test_rebuild_assistant_sentence_polish_fixes_known_fragments():
    from mellow_link.modules.rebuild_assistant.postprocess.rules import apply_sentence_polish

    raw = "환율 데이터 누락로 명확하므로 규칙야 합니다. 이동평균법로 계산합니다. 금지을 확인합니다. 입니다. 입니다."
    polished = apply_sentence_polish(raw)

    assert "누락로" not in polished
    assert "규칙야 합니다" not in polished
    assert "이동평균법로" not in polished
    assert "금지을" not in polished
    assert "입니다. 입니다." not in polished
    assert "누락으로" in polished
    assert "규칙이어야 합니다" in polished
    assert "이동평균법으로" in polished


def test_rebuild_assistant_warning_lenient_policy_sample_uses_warning_narrative():
    from datetime import datetime, timezone

    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
    from mellow_link.routers.projects import _result_package_markdown, build_result_package

    sample_dir = MELLOW_LINK_ROOT / "modules" / "rebuild_assistant" / "samples" / "03_warning_lenient_policy"
    bundle = _build_safe_bundle_for_rebuild_tests(
        [
            {"name": "legacy_context.txt", "content": sample_dir.joinpath("legacy_context.txt").read_text(encoding="utf-8")},
            {"name": "accounting_payload.json", "content": sample_dir.joinpath("accounting_payload.json").read_text(encoding="utf-8")},
        ]
    )

    svc = RebuildAssistantService()
    result = svc.build_result(
        svc.prepare_safe_bundle_input(goal="전산회계 MVP 기능을 재구성", safe_bundle=bundle, constraints=[])
    )
    pkg = build_result_package(
        SimpleNamespace(
            id="proj_warning_fx",
            project_name="warning lenient policy",
            client_name="ACME",
            template_key="rebuild_assistant",
            status="completed",
            created_at=datetime.now(timezone.utc),
        ),
        {"status": "completed", "run_id": "run_warning_fx"},
        result,
        assets=[],
        polish_bundle=svc.build_polish_bundle(result, audience="manager", delivery_mode="client_report").model_dump(),
        app_version="0.1.0",
    )
    markdown = _result_package_markdown(pkg)

    assert "검토용 초안" in markdown
    assert "복수 정책 충돌" in markdown
    assert "회계 기능은 이동평균법 기준으로 계산을 수행했지만" in markdown
    assert "회계 계산을 수행할 수 없습니다." not in markdown
    assert "입니다. 입니다." not in markdown
    assert "습니다.와" not in markdown


def test_project_result_static_ui_renders_accounting_polish_controls():
    html_path = MELLOW_LINK_ROOT / "static" / "project_result.html"
    html = html_path.read_text(encoding="utf-8")

    assert 'id="accountingSection"' in html
    assert 'id="polishAudienceSelect"' in html
    assert 'id="polishDeliverySelect"' in html
    assert "accounting_summary" in html
    assert "accounting_status" in html
    assert "회계 확장" in html
    assert "문서 맥락" in html
    assert "분석 범위" in html
    assert "검증 질문" in html
    assert "열람 대상" in html
    assert "납품 톤" in html
    assert "표현 보정 경고" in html
    assert "회계 계산 요약" in html
    assert "계산 가능 여부" in html
    assert "fx_calculation" in html
    assert "검토 불가" in html
    assert "renderAccountingSection(pkg)" in html


def test_rebuild_assistant_extracted_rules_shape_is_kept_for_sparse_input():
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
    from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

    svc = RebuildAssistantService()
    prepared = svc.prepare_input(
        goal="이 기능을 재구성해줘",
        assets=RebuildAssetsPayload(source_code="<% legacy %>"),
    )
    result = svc.build_result(prepared)
    dumped = result.extracted_rules.model_dump()

    assert set(dumped.keys()) == {"status_permissions", "search_filters", "save_validation"}
    assert set(dumped["status_permissions"].keys()) == {
        "entities",
        "roles",
        "statuses",
        "actions",
        "role_action_matrix",
        "status_action_matrix",
        "transition_rules",
        "ui_visibility_rules",
        "policy_hints",
    }
    assert set(dumped["search_filters"].keys()) == {
        "entities",
        "filter_fields",
        "query_params",
        "sort_rules",
        "paging_rules",
        "query_binding_rules",
        "default_filters",
        "result_shape_hints",
    }
    assert set(dumped["save_validation"].keys()) == {
        "entities",
        "required_fields",
        "field_validation_rules",
        "duplicate_check_rules",
        "save_guard_rules",
        "exception_rules",
        "command_boundary_hints",
    }


def _run_rebuild_case(monkeypatch, *, run_id: str, goal: str, assets, temp_context: str = ""):
    from mellow_link import app_state
    from mellow_link.modules.rebuild_assistant import compat as rebuild_compat
    from mellow_link.modules.rebuild_assistant import runner as rebuild_runner

    events = []

    class InlineThread:
        def __init__(self, target=None, daemon=None, *args, **kwargs):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    def fake_emit(run_id_arg, event_type, payload, **kwargs):
        events.append({"run_id": run_id_arg, "type": event_type, "payload": payload})

    monkeypatch.setattr(rebuild_runner.threading, "Thread", InlineThread)
    monkeypatch.setattr(rebuild_runner, "emit_event", fake_emit)
    monkeypatch.setattr(app_state, "TEMP_CONTEXT_STORE", {"rebuild-regression-temp": temp_context}, raising=False)

    rebuild_compat.start_rebuild_assistant_run_compat(
        run_id=run_id,
        session_id="session-test",
        goal=goal,
        assets=assets,
        constraints=[],
        temp_session_id="rebuild-regression-temp" if temp_context else None,
    )

    finished = [event for event in events if event["type"] == "run_finished"]
    assert len(finished) == 1
    return finished[0]["payload"]


def test_rebuild_assistant_regression_status_permissions_mode(monkeypatch):
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload

    payload = _run_rebuild_case(
        monkeypatch,
        run_id="run_rebuild_regression_status",
        goal="결재 상태와 권한에 따라 액션이 바뀌는 JSP 화면을 재구성해줘",
        assets=RebuildAssetsPayload(
            source_code="""
if ("APPROVED".equals(status) || userRole.equals("ADMIN")) { showApproveButton = true; }
if ("PENDING".equals(status)) { showRejectButton = true; }
if ("REJECTED".equals(status)) { showResubmitButton = true; }
            """,
            ui_template="""
<c:if test="${sessionScope.role eq 'ADMIN'}"><button>Approve</button></c:if>
<c:if test="${item.status eq 'PENDING'}"><button>Reject</button></c:if>
<c:if test="${item.status eq 'REJECTED'}"><button>Resubmit</button></c:if>
            """,
        ),
    )

    structured = payload["structured_result"]
    assert payload["primary_feature_mode"] == "status_permissions"
    assert {"grounded_business_rules", "decision_items", "retained_contracts", "design_options", "recommended_option", "execution_plan"} <= set(structured.keys())
    rules = structured["extracted_rules"]["status_permissions"]
    assert rules["roles"]
    assert rules["statuses"]
    assert rules["actions"]
    assert rules["transition_rules"]
    assert set(structured["extracted_rules"].keys()) == {"status_permissions", "search_filters", "save_validation"}
    assert "정책" in structured["one_line_conclusion"] or "액션" in structured["one_line_conclusion"] or "상태" in structured["one_line_conclusion"]
    assert len(structured["decision_items"]) >= 3


def test_rebuild_assistant_regression_search_filters_mode(monkeypatch):
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload

    payload = _run_rebuild_case(
        monkeypatch,
        run_id="run_rebuild_regression_search",
        goal="검색 조건이 많은 주문 조회 화면을 재구성해줘",
        assets=RebuildAssetsPayload(
            source_code="""
<form id="searchForm">
String keyword = request.getParameter("keyword");
String statusFilter = request.getParameter("status");
String page = request.getParameter("page");
</form>
<table id="results"></table>
            """,
            sql_queries="""
SELECT * FROM orders
WHERE user_name LIKE ?
AND status = ?
ORDER BY created_at DESC
LIMIT ? OFFSET ?
            """,
        ),
    )

    structured = payload["structured_result"]
    assert payload["primary_feature_mode"] == "search_filters"
    assert {"grounded_business_rules", "decision_items", "design_options", "execution_plan"} <= set(structured.keys())
    rules = structured["extracted_rules"]["search_filters"]
    assert rules["filter_fields"]
    assert rules["query_params"]
    assert rules["query_binding_rules"]
    assert rules["sort_rules"] or rules["default_filters"] or rules["result_shape_hints"]
    conclusion = structured["one_line_conclusion"]
    assert "조회" in conclusion or "검색" in conclusion or "필터" in conclusion or "쿼리" in conclusion


def test_rebuild_assistant_regression_save_validation_mode(monkeypatch):
    from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload

    payload = _run_rebuild_case(
        monkeypatch,
        run_id="run_rebuild_regression_save",
        goal="저장 검증과 중복 체크가 많은 등록 기능을 재구성해줘",
        assets=RebuildAssetsPayload(
            source_code="""
if (name == null || name.isBlank()) throw new IllegalArgumentException("required");
if (repository.existsByCode(code)) throw new IllegalStateException("duplicate");
if (!userRole.equals("ADMIN")) throw new SecurityException("forbidden");
repository.save(entity);
            """,
            sql_queries="SELECT count(1) FROM products WHERE code = ?; INSERT INTO products(code, name) VALUES (?, ?);",
        ),
    )

    structured = payload["structured_result"]
    assert payload["primary_feature_mode"] == "save_validation"
    assert {"grounded_business_rules", "decision_items", "retained_contracts", "recommended_option"} <= set(structured.keys())
    rules = structured["extracted_rules"]["save_validation"]
    assert rules["required_fields"] or rules["field_validation_rules"]
    assert rules["duplicate_check_rules"]
    assert rules["save_guard_rules"]
    conclusion = structured["one_line_conclusion"]
    assert "검증" in conclusion or "저장" in conclusion or "중복" in conclusion


def test_research_assistant_abort_during_attempt_1_stops_current_run(monkeypatch):
    payload, llm_calls, events = _run_research_abort_case(monkeypatch, "attempt_1")

    assert payload["success"] is False
    assert payload["finish_reason"] == "operator_abort"
    assert payload["failure_reason"] == "aborted_by_user"
    assert payload["abort_requested"] is True
    assert payload["abort_handled"] is True
    assert payload["abort_stage"] == "attempt_1"
    assert llm_calls == 1
    assert not any(event["type"] == "run_finished" and event["payload"].get("success") is True for event in events)


def test_research_assistant_abort_before_attempt_2_skips_retry(monkeypatch):
    payload, llm_calls, events = _run_research_abort_case(monkeypatch, "attempt_2")

    assert payload["success"] is False
    assert payload["finish_reason"] == "operator_abort"
    assert payload["failure_reason"] == "aborted_by_user"
    assert payload["abort_stage"] == "attempt_2"
    assert llm_calls == 1
    assert not any(event["type"] == "run_finished" and event["payload"].get("success") is True for event in events)


def test_research_assistant_abort_before_finalize_skips_result_write(monkeypatch):
    payload, llm_calls, events = _run_research_abort_case(monkeypatch, "finalize")

    assert payload["success"] is False
    assert payload["finish_reason"] == "operator_abort"
    assert payload["failure_reason"] == "aborted_by_user"
    assert payload["abort_stage"] == "finalize"
    assert payload["summary"] == "Run aborted by operator."
    assert llm_calls == 1
    assert not any(event["type"] == "run_finished" and event["payload"].get("success") is True for event in events)
