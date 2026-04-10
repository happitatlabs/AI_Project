import uuid

import pytest

try:
    from fastapi.testclient import TestClient

    _has_fastapi = True
except ImportError:
    _has_fastapi = False

from mellow_link import app_state
from mellow_link.infra import ModernizationProject
from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.routers.projects import build_result_package
from mellow_link.services.refactoring_support_engine import ExplanationPresenter, ResultQuestionAnsweringService
from mellow_link.tests.refactoring_support_test_utils import build_safe_bundle
from mellow_link.tests.test_phase1_run_flow import _create_persisted_project, _get_app, _register


def _build_ready_result_package():
    service = RebuildAssistantService()
    bundle = build_safe_bundle(
        [
            {
                "name": "order_service.py",
                "content": """
class OrderService:
    def submit(self, order, repo):
        if not order.amount:
            raise ValueError("required")
        if order.status == "READY":
            repo.save(order)
            return approve(order)
                """,
            },
            {
                "name": "order_page.html",
                "content": '<button onclick="submitOrder()">submit</button>',
            },
            {
                "name": "order_query.sql",
                "content": "SELECT * FROM orders WHERE status = 'READY' AND amount > 1000",
            },
        ]
    )
    prepared = service.prepare_safe_bundle_input(goal="modernize order creation flow", safe_bundle=bundle, constraints=[])
    result = service.build_result(prepared)
    polish_bundle = service.build_polish_bundle(result, audience="manager", delivery_mode="client_report").model_dump()
    project = ModernizationProject(
        id="proj_phase3_ready",
        user_id=1,
        session_id="sess_phase3_ready",
        run_id="run_phase3_ready",
        project_name="주문 생성 현대화",
        client_name="OO생명",
        template_key="default_modernization_v1",
        template_mode="recommended",
        constraints_json="[]",
        upload_session_id="upload_phase3_ready",
        asset_manifest_json="[]",
        status="completed",
    )
    result_package = build_result_package(
        project,
        {"status": "completed", "run_id": project.run_id},
        result,
        assets=[],
        polish_bundle=polish_bundle,
        app_version="0.1.0",
    )
    return result, polish_bundle, result_package


def _card_by_key(response, card_key: str):
    return next(card for card in response.summary_cards if card.card_key == card_key)


def _section_by_key(response, section_key: str):
    return next(section for section in response.section_views if section.section_key == section_key)


def test_explanation_presenter_keeps_facts_and_citations_across_audiences():
    result, _, result_package = _build_ready_result_package()
    presenter = ExplanationPresenter()

    developer = presenter.present(project_id="proj_phase3_ready", result_package=result_package, audience="developer")
    manager = presenter.present(project_id="proj_phase3_ready", result_package=result_package, audience="manager")
    client = presenter.present(project_id="proj_phase3_ready", result_package=result_package, audience="client")

    top_decision = result.decision_summary["decisions"][0]
    top_stage = result.improvement_plan_bundle["execution_stages"][0]
    coverage = result.structure_snapshot["coverage_summary"]

    for response in (developer, manager, client):
        assert response.taxonomy_view.core_judgment.structural_judgment == result.structural_judgment
        assert response.taxonomy_view.core_judgment.recommended_strategy == result.decision_summary["recommended_strategy"]
        assert response.taxonomy_view.core_judgment.top_decision_type == top_decision["decision_type"]
        assert response.taxonomy_view.evidence_view.top_priority_score == top_decision["priority_score"]
        assert response.taxonomy_view.evidence_view.score_breakdown == top_decision["score_breakdown"]
        assert response.taxonomy_view.explanation_context.narrative_axis == result.narrative_axis
        assert response.review_diff_preview.available is True
        assert response.review_diff_preview.structural_signals
        assert response.review_diff_preview.evidence_signals
        assert result.decision_summary["recommended_strategy"] in _card_by_key(response, "strategy").body
        assert result.structural_judgment in _card_by_key(response, "judgment").body
        assert top_decision["decision_type"] in _card_by_key(response, "strategy").body
        assert str(top_decision["priority_score"]) in _card_by_key(response, "priority").body
        assert top_stage["title"] in _card_by_key(response, "execution").body
        assert str(coverage["slice_count"]) in _card_by_key(response, "scope").body

    assert _card_by_key(developer, "judgment").body != _card_by_key(manager, "judgment").body
    assert _card_by_key(developer, "strategy").body != _card_by_key(manager, "strategy").body
    assert _card_by_key(manager, "strategy").body != _card_by_key(client, "strategy").body

    for card_key in ("judgment", "strategy", "priority", "execution", "scope"):
        assert [item.model_dump() for item in _card_by_key(developer, card_key).citations] == [
            item.model_dump() for item in _card_by_key(manager, card_key).citations
        ]
        assert [item.model_dump() for item in _card_by_key(manager, card_key).citations] == [
            item.model_dump() for item in _card_by_key(client, card_key).citations
        ]

    assert [item.model_dump() for item in _section_by_key(developer, "execution_plan").citations] == [
        item.model_dump() for item in _section_by_key(client, "execution_plan").citations
    ]


def test_explanation_presenter_hides_review_diff_preview_for_external_surface():
    result, _, result_package = _build_ready_result_package()
    presenter = ExplanationPresenter()

    internal = presenter.present(
        project_id="proj_phase3_ready",
        result_package=result_package,
        audience="manager",
        surface_mode="internal",
    )
    external = presenter.present(
        project_id="proj_phase3_ready",
        result_package=result_package,
        audience="manager",
        surface_mode="external",
    )

    assert internal.surface_mode == "internal"
    assert internal.review_diff_preview.available is True
    assert external.surface_mode == "external"
    assert external.review_diff_preview.available is False
    assert external.review_diff_preview.structural_signals == []
    assert external.review_diff_preview.evidence_signals == []
    assert external.review_diff_preview.blocked_decisions == []
    assert internal.taxonomy_view.model_dump() == external.taxonomy_view.model_dump()
    assert [card.card_key for card in internal.summary_cards] == ["judgment", "strategy", "priority", "execution", "scope"]
    assert [card.card_key for card in external.summary_cards] == ["judgment", "strategy", "execution"]
    assert [card.title for card in external.summary_cards] == ["핵심 판단", "왜 이 방향인가", "다음 단계"]
    assert [section.section_key for section in external.section_views] == ["recommended_option", "execution_plan", "risks"]
    assert [section.title for section in external.section_views] == ["이 방향의 효과", "진행 흐름", "주의할 영향"]
    external_text = " ".join(card.body for card in external.summary_cards) + " " + " ".join(section.text for section in external.section_views)
    assert "decision type" not in external_text.lower()
    assert "severity" not in external_text.lower()
    assert "blast radius" not in external_text.lower()
    assert "해야" not in external_text
    assert "필요합니다" not in external_text
    assert "Decision Brief" not in external_text
    assert "ready" not in external_text.lower()
    for card in external.summary_cards:
        assert all(not citation.decision_id and not citation.issue_id and not citation.evidence_id and not citation.locator for citation in card.citations)
    for section in external.section_views:
        assert all(not citation.decision_id and not citation.issue_id and not citation.evidence_id and not citation.locator for citation in section.citations)
    assert internal.provenance["access_profile"] == "internal_full"
    assert internal.provenance["review_diff_surface"] == "preview_only"
    assert internal.provenance["review_diff_surface_policy"] == "visible"
    assert internal.provenance["field_visibility"]["review_diff"] == "visible"
    assert external.provenance["access_profile"] == "external_basic"
    assert external.provenance["review_diff_surface"] == "hidden_by_policy"
    assert external.provenance["review_diff_surface_policy"] == "hidden_by_policy"
    assert external.provenance["field_visibility"]["review_diff"] == "hidden_by_policy"


def test_explanation_presenter_uses_deterministic_fallback_without_polish_bundle():
    result, _, result_package = _build_ready_result_package()
    response = ExplanationPresenter().present(
        project_id="proj_phase3_ready",
        result_package={**result_package, "polish_bundle": None},
        audience="manager",
    )

    assert response.provenance["wording_source"] == "deterministic_fallback"
    assert response.provenance["delivery_mode_applied"] is False
    assert response.warnings
    assert _section_by_key(response, "report_purpose").text == result.report_purpose
    assert response.taxonomy_view.core_judgment.structural_judgment == result.structural_judgment
    assert response.review_diff_preview.available is True


def test_build_result_package_backfills_taxonomy_for_legacy_structured_result():
    result, _, result_package = _build_ready_result_package()
    legacy_result = result.model_copy(
        update={
            "template_judgment": "",
            "structural_judgment": "",
            "narrative_axis": "",
            "feature_signal_mode": "",
        }
    )

    project = ModernizationProject(
        id="proj_phase3_legacy_surface",
        user_id=1,
        session_id="sess_phase3_legacy_surface",
        run_id="run_phase3_legacy_surface",
        project_name="레거시 taxonomy surface",
        client_name="OO생명",
        template_key="default_modernization_v1",
        template_mode="recommended",
        constraints_json="[]",
        upload_session_id="upload_phase3_legacy_surface",
        asset_manifest_json="[]",
        status="completed",
    )
    rebuilt_package = build_result_package(
        project,
        {"status": "completed", "run_id": project.run_id},
        legacy_result,
        assets=[],
        polish_bundle=result_package["polish_bundle"],
        app_version="0.1.0",
    )

    assert rebuilt_package["primary_judgment"] == result.primary_judgment
    assert rebuilt_package["template_judgment"] == result.primary_judgment
    assert rebuilt_package["structural_judgment"] == result.structural_judgment
    assert rebuilt_package["narrative_axis"] == result.primary_judgment

    response = ExplanationPresenter().present(
        project_id=project.id,
        result_package=rebuilt_package,
        audience="manager",
    )

    assert response.taxonomy_view.core_judgment.structural_judgment == result.structural_judgment
    assert response.taxonomy_view.explanation_context.narrative_axis == result.primary_judgment


@pytest.mark.asyncio
async def test_result_question_answering_service_returns_grounded_priority_answer_deterministically():
    result, _, result_package = _build_ready_result_package()
    service = ResultQuestionAnsweringService()

    first = await service.answer(
        project_id="proj_phase3_ready",
        result_package=result_package,
        question="왜 이게 우선순위가 높아?",
        audience="manager",
        llm_service=None,
    )
    second = await service.answer(
        project_id="proj_phase3_ready",
        result_package=result_package,
        question="왜 이게 우선순위가 높아?",
        audience="manager",
        llm_service=None,
    )

    assert first.answer_mode == "deterministic"
    assert first.insufficient_grounding is False
    assert first.referenced_sections == ["decision_summary"]
    assert first.answer == second.answer
    assert str(result.decision_summary["decisions"][0]["priority_score"]) in first.answer
    assert first.citations


@pytest.mark.asyncio
async def test_result_question_answering_service_reports_insufficient_grounding():
    empty_project = ModernizationProject(
        id="proj_phase3_empty",
        user_id=1,
        session_id="sess_phase3_empty",
        run_id="run_phase3_empty",
        project_name="미완료 프로젝트",
        client_name="OO",
        template_key="default_modernization_v1",
        template_mode="recommended",
        constraints_json="[]",
        upload_session_id="upload_phase3_empty",
        asset_manifest_json="[]",
        status="running",
    )
    empty_package = build_result_package(
        empty_project,
        {"status": "running", "run_id": empty_project.run_id},
        None,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )

    response = await ResultQuestionAnsweringService().answer(
        project_id=empty_project.id,
        result_package=empty_package,
        question="주요 리스크가 뭐야?",
        audience="client",
        llm_service=None,
    )

    assert response.insufficient_grounding is True
    assert response.answer_mode == "deterministic"
    assert "grounding" in response.answer


@pytest.mark.asyncio
async def test_result_question_answering_service_invalid_ai_output_falls_back():
    result, _, result_package = _build_ready_result_package()

    class BadLLM:
        async def generate(self, *args, **kwargs):
            class Response:
                content = '{"answer":"최우선 점수는 9999이고 신규 CORP_X 정책이 추가되었습니다."}'
                model = "qwen3.5:9b"

            return Response()

    response = await ResultQuestionAnsweringService().answer(
        project_id="proj_phase3_ready",
        result_package=result_package,
        question="왜 이게 우선순위가 높아?",
        audience="manager",
        llm_service=BadLLM(),
    )

    assert response.answer_mode == "deterministic"
    assert response.provenance["validation_passed"] is False
    assert response.provenance["fallback_reason"] in {"new_numeric_fact", "new_named_token"}
    assert str(result.decision_summary["decisions"][0]["priority_score"]) in response.answer


@pytest.fixture(scope="module")
def client():
    app = _get_app()
    if app is None:
        pytest.skip("FastAPI app not available")
    return TestClient(app)


def test_result_explanation_and_qa_endpoints_are_additive_and_read_only(client, monkeypatch):
    from mellow_link.infra import ModernizationProject
    from mellow_link.infra.database import SessionLocal
    from mellow_link.infra.run_events import EVENT_TYPE_RUN_FINISHED, emit_event

    monkeypatch.setattr(app_state, "llm_service", None, raising=False)
    user = _register(client, "phase3_result")
    project_id, _ = _create_persisted_project(
        client,
        user,
        monkeypatch,
        upload_session_id=f"phase3-upload-{uuid.uuid4().hex[:8]}",
        filename="legacy.jsp",
        content=b"<% String sql = \"SELECT * FROM orders\"; %>",
        project_name="주문 결과 설명",
        client_name="OO카드",
    )
    result, polish_bundle, _ = _build_ready_result_package()

    with SessionLocal() as db:
        project = db.query(ModernizationProject).filter(ModernizationProject.id == project_id).first()
        emit_event(
            project.run_id,
            EVENT_TYPE_RUN_FINISHED,
            {
                "success": True,
                "summary": "completed",
                "structured_result": result.model_dump(),
                "polish_bundle": polish_bundle,
                "primary_feature_mode": "save_validation",
                "module_id": "rebuild_assistant",
                "run_kind": "rebuild_plan",
            },
            db=db,
        )

    developer = client.get(
        f"/projects/{project_id}/result/explanation",
        params={"audience": "developer", "surface_mode": "internal"},
        headers=user["headers"],
    )
    client_view = client.get(
        f"/projects/{project_id}/result/explanation",
        params={"audience": "client", "surface_mode": "internal"},
        headers=user["headers"],
    )
    external_view = client.get(
        f"/projects/{project_id}/result/explanation",
        params={"audience": "client", "surface_mode": "external"},
        headers=user["headers"],
    )
    assert developer.status_code == 200, developer.text
    assert client_view.status_code == 200, client_view.text
    assert external_view.status_code == 200, external_view.text
    developer_body = developer.json()
    client_body = client_view.json()
    external_body = external_view.json()

    developer_priority = next(card for card in developer_body["summary_cards"] if card["card_key"] == "priority")
    client_priority = next(card for card in client_body["summary_cards"] if card["card_key"] == "priority")
    assert developer_priority["citations"] == client_priority["citations"]
    assert developer_body["provenance"]["delivery_mode_applied"] is False
    assert client_body["provenance"]["delivery_mode_applied"] is False
    assert developer_body["taxonomy_view"]["core_judgment"]["structural_judgment"]
    assert developer_body["taxonomy_view"]["core_judgment"]["recommended_strategy"]
    assert developer_body["taxonomy_view"]["explanation_context"]["narrative_axis"]
    assert developer_body["review_diff_preview"]["available"] is True
    assert developer_body["review_diff_preview"]["structural_signals"]
    assert developer_body["review_diff_preview"]["evidence_signals"]
    assert "markdown" not in developer_body["review_diff_preview"]
    assert developer_body["provenance"]["access_profile"] == "internal_full"
    assert developer_body["provenance"]["field_visibility"]["review_diff"] == "visible"
    assert external_body["surface_mode"] == "external"
    assert external_body["review_diff_preview"]["available"] is False
    assert external_body["review_diff_preview"]["structural_signals"] == []
    assert external_body["review_diff_preview"]["evidence_signals"] == []
    assert external_body["review_diff_preview"]["blocked_decisions"] == []
    assert external_body["provenance"]["access_profile"] == "external_basic"
    assert external_body["provenance"]["review_diff_surface"] == "hidden_by_policy"
    assert external_body["provenance"]["review_diff_surface_policy"] == "hidden_by_policy"
    assert external_body["provenance"]["field_visibility"]["review_diff"] == "hidden_by_policy"
    assert external_body["taxonomy_view"] == client_body["taxonomy_view"]
    assert [card["card_key"] for card in external_body["summary_cards"]] == ["judgment", "strategy", "execution"]
    assert [card["title"] for card in external_body["summary_cards"]] == ["핵심 판단", "왜 이 방향인가", "다음 단계"]
    assert [section["section_key"] for section in external_body["section_views"]] == ["recommended_option", "execution_plan", "risks"]
    assert [section["title"] for section in external_body["section_views"]] == ["이 방향의 효과", "진행 흐름", "주의할 영향"]
    external_text = " ".join(card["body"] for card in external_body["summary_cards"]) + " " + " ".join(section["text"] for section in external_body["section_views"])
    assert "decision type" not in external_text.lower()
    assert "severity" not in external_text.lower()
    assert "blast radius" not in external_text.lower()
    assert "해야" not in external_text
    assert "필요합니다" not in external_text
    assert "Decision Brief" not in external_text
    assert "ready" not in external_text.lower()
    for card in external_body["summary_cards"]:
        assert all(not citation["decision_id"] and not citation["issue_id"] and not citation["evidence_id"] and not citation["locator"] for citation in card["citations"])
    for section in external_body["section_views"]:
        assert all(not citation["decision_id"] and not citation["issue_id"] and not citation["evidence_id"] and not citation["locator"] for citation in section["citations"])
    assert "primary_judgment" not in developer_body["taxonomy_view"]
    assert "template_judgment" not in developer_body["taxonomy_view"]
    assert "feature_signal_mode" not in developer_body["taxonomy_view"]

    qa_res = client.post(
        f"/projects/{project_id}/result/qa",
        headers={**user["headers"], "Content-Type": "application/json"},
        json={"question": "왜 이게 우선순위가 높아?", "audience": "manager"},
    )
    assert qa_res.status_code == 200, qa_res.text
    qa_body = qa_res.json()
    assert qa_body["insufficient_grounding"] is False
    assert qa_body["citations"]
    assert qa_body["referenced_sections"] == ["decision_summary"]

    base_result = client.get(f"/projects/{project_id}/result?format=json", headers=user["headers"])
    assert base_result.status_code == 200, base_result.text
    base_body = base_result.json()
    assert "authoritative_payload" in base_body
    assert "extensions" in base_body
    assert "review_diff" in base_body["extensions"]
    assert "summary_cards" not in base_body
