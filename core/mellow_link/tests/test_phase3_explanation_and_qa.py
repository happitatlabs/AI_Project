import uuid
import re
from copy import deepcopy

import pytest

try:
    from fastapi.testclient import TestClient

    _has_fastapi = True
except ImportError:
    _has_fastapi = False

from mellow_link import app_state
from mellow_link.infra import ModernizationProject
from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.routers.projects import (
    _generate_result_package_docx,
    _resolve_slide_schema,
    _result_package_markdown,
    _result_package_pptx_response,
    build_result_package,
)
from mellow_link.services.refactoring_support_engine import ExplanationPresenter, ResultQuestionAnsweringService
from mellow_link.tests.refactoring_support_test_utils import build_safe_bundle, load_sample_case
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


def _build_fx_fifo_operational_result_package():
    service = RebuildAssistantService()
    case = load_sample_case("09_fx_fifo_operational_source")
    prepared = service.prepare_safe_bundle_input(
        goal=str(case["goal"]),
        safe_bundle=case["safe_bundle"],
        constraints=list(case["constraints"]),
    )
    result = service.build_result(prepared)
    polish_bundle = service.build_polish_bundle(result, audience="manager", delivery_mode="client_report").model_dump()
    project = ModernizationProject(
        id="proj_phase3_fx_fifo",
        user_id=1,
        session_id="sess_phase3_fx_fifo",
        run_id="run_phase3_fx_fifo",
        project_name="외화 FIFO 운영 분석",
        client_name="OO생명",
        template_key="default_modernization_v1",
        template_mode="recommended",
        constraints_json="[]",
        upload_session_id="upload_phase3_fx_fifo",
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


def _contains_sql_like_token(text: str) -> bool:
    patterns = (
        r"\b(?:TN|TB|TR|IB|GL|P|PKG|PK|PROC|PRC|FN|FNC|SP|VW|IDX|SEQ)_[A-Z0-9_$#]+\b",
        r"\b[A-Z][A-Z0-9$#]*_[A-Z0-9$#]*(?:AMT|SEQ|ID|CD|CODE|YN|FLAG|STATUS|RATE|DATE|DT|NO|NUM|QTY|CNT|KEY|REF)[A-Z0-9$#]*\b",
        r"\b(?:SELECT|INSERT|UPDATE|DELETE|MERGE|JOIN|FROM|WHERE|GROUP\s+BY|ORDER\s+BY)\b",
    )
    upper_text = str(text or "").upper()
    return any(re.search(pattern, upper_text) for pattern in patterns)


def _markdown_headings(markdown: str, level: int = 2) -> list[str]:
    prefix = "#" * level + " "
    return [line.strip() for line in str(markdown or "").splitlines() if line.startswith(prefix)]


def _first_section_paragraph(markdown: str) -> str:
    lines = str(markdown or "").splitlines()
    for idx, line in enumerate(lines):
        if not line.startswith("## "):
            continue
        for j in range(idx + 1, len(lines)):
            candidate = lines[j].strip()
            if not candidate:
                continue
            if candidate.startswith("#"):
                return ""
            return candidate[2:].strip() if candidate.startswith("- ") else candidate
    return ""


def _guard_precedence_package(result_package, polish_bundle):
    patched_polish = dict(polish_bundle)
    patched_sections = []
    for section in polish_bundle.get("polished_sections") or []:
        if not isinstance(section, dict):
            continue
        patched_section = dict(section)
        audience_variants = dict(section.get("audience_variants") or {})
        if str(section.get("section_key") or "") == "report_purpose":
            audience_variants["manager"] = "polish report purpose should lose"
        if str(section.get("section_key") or "") == "one_line_conclusion":
            audience_variants["manager"] = "polish conclusion should lose"
        if str(section.get("section_key") or "") == "primary_judgment_reason":
            audience_variants["manager"] = "polish judgment reason should lose"
        if str(section.get("section_key") or "") == "executive_summary_v2":
            audience_variants["manager"] = "polish summary should lose"
        if str(section.get("section_key") or "") == "recommended_option":
            audience_variants["manager"] = "polish recommended option should lose"
        if str(section.get("section_key") or "") == "execution_plan":
            audience_variants["manager"] = "polish execution plan should lose"
        if str(section.get("section_key") or "") == "risks":
            audience_variants["manager"] = "polish risks should lose"
        patched_section["audience_variants"] = audience_variants
        patched_sections.append(patched_section)
    patched_polish["polished_sections"] = patched_sections

    return {
        **result_package,
        "validated_narrative_layer": {
            "report_purpose": "validated narrative layer should lose",
            "one_line_conclusion": "validated conclusion layer should lose",
            "primary_judgment_reason": "validated reason layer should lose",
            "executive_summary_v2": ["validated summary layer should lose"],
            "recommended_option": "validated recommended option should lose",
            "execution_plan": [
                "validated execution stage 1 should lose",
                "validated execution stage 2 should lose",
            ],
            "risks": [
                "validated risk item 1 should lose",
                "validated risk item 2 should lose",
            ],
        },
        "validated_explanation_blocks": [
            {
                "block_id": "report_purpose",
                "resolved_lines": ["guard report purpose wins"],
                "deterministic_lines": ["guard report purpose wins"],
            },
            {
                "block_id": "one_line_conclusion",
                "resolved_lines": ["guard conclusion wins"],
                "deterministic_lines": ["guard conclusion wins"],
            },
            {
                "block_id": "primary_judgment_reason",
                "resolved_lines": ["guard judgment reason wins"],
                "deterministic_lines": ["guard judgment reason wins"],
            },
            {
                "block_id": "executive_summary_v2",
                "resolved_lines": ["guard summary wins"],
                "deterministic_lines": ["guard summary wins"],
            },
            {
                "block_id": "recommended_option",
                "resolved_lines": ["guard recommended option wins"],
                "deterministic_lines": ["guard recommended option wins"],
            },
            {
                "block_id": "execution_plan",
                "resolved_lines": [
                    "guard execution stage 1 wins",
                    "guard execution stage 2 wins",
                ],
                "deterministic_lines": [
                    "guard execution stage 1 wins",
                    "guard execution stage 2 wins",
                ],
            },
            {
                "block_id": "risks",
                "resolved_lines": [
                    "guard risk item 1 wins",
                    "guard risk item 2 wins",
                ],
                "deterministic_lines": [
                    "guard risk item 1 wins",
                    "guard risk item 2 wins",
                ],
            },
        ],
        "narrative_guard_metadata": {"source": "ai"},
        "polish_bundle": patched_polish,
    }


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
    assert [card.title for card in external.summary_cards] == ["핵심 문제", "영향", "권장 조치"]
    assert [section.section_key for section in external.section_views] == ["recommended_option", "execution_plan", "risks"]
    assert [section.title for section in external.section_views] == ["권장 조치", "검증 포인트", "영향"]
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


def test_operational_source_explanation_surface_uses_display_strategy_and_analysis_first_titles():
    result, _, result_package = _build_fx_fifo_operational_result_package()
    presenter = ExplanationPresenter()

    internal = presenter.present(
        project_id="proj_phase3_fx_fifo",
        result_package=result_package,
        audience="manager",
        surface_mode="internal",
    )
    external = presenter.present(
        project_id="proj_phase3_fx_fifo",
        result_package=result_package,
        audience="manager",
        surface_mode="external",
    )

    assert internal.taxonomy_view.core_judgment.recommended_strategy == result.decision_summary["recommended_strategy"]
    assert internal.taxonomy_view.core_judgment.display_strategy == "현행 분석 우선"
    assert [card.title for card in external.summary_cards] == ["핵심 문제", "영향", "권장 조치"]
    assert [section.title for section in external.section_views] == ["권장 조치", "검증 포인트", "영향"]
    assert _section_by_key(internal, "report_purpose").title == "분석 목적"
    assert _section_by_key(internal, "one_line_conclusion").title == "자산 정체"
    assert _section_by_key(internal, "analysis_summary").title == "핵심 객체"
    assert "recommended_option" not in {section.section_key for section in internal.section_views}
    assert "risks" not in {section.section_key for section in internal.section_views}
    assert "현행 분석 우선" in _card_by_key(internal, "strategy").body
    assert "리팩터링 우선" not in _card_by_key(external, "strategy").body
    front_text = " ".join(
        [
            _section_by_key(internal, "report_purpose").text,
            _section_by_key(internal, "one_line_conclusion").text,
            _section_by_key(internal, "execution_plan").text,
        ]
    )
    analysis_lines = [line.strip("- ").strip() for line in _section_by_key(internal, "analysis_summary").text.splitlines() if line.strip()]
    object_lines = analysis_lines[1:]
    assert not _contains_sql_like_token(front_text)
    assert analysis_lines[0].startswith("핵심 데이터 흐름은")
    assert 3 <= len(object_lines) <= 5
    assert all(re.match(r"^[^:]+: .+$", line) for line in object_lines)
    assert all(not re.search(r"\b(?:table|procedure|trigger)\b", line, flags=re.IGNORECASE) for line in object_lines)
    assert all("TN_" not in line and "GL_INTERFACE" not in line for line in object_lines)


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
    assert result.report_purpose in _section_by_key(response, "report_purpose").text
    assert "[상황 / 목적]" in _section_by_key(response, "report_purpose").text
    assert response.taxonomy_view.core_judgment.structural_judgment == result.structural_judgment
    assert response.review_diff_preview.available is True


def test_explanation_presenter_prefers_guard_blocks_over_validated_layer_and_polish():
    _, polish_bundle, result_package = _build_ready_result_package()
    response = ExplanationPresenter().present(
        project_id="proj_phase3_ready",
        result_package=_guard_precedence_package(result_package, polish_bundle),
        audience="manager",
    )

    assert _section_by_key(response, "report_purpose").text == "guard report purpose wins"
    assert _section_by_key(response, "one_line_conclusion").text == "guard conclusion wins"
    assert _section_by_key(response, "recommended_option").text == "guard recommended option wins"
    assert _section_by_key(response, "execution_plan").text == "guard execution stage 1 wins\nguard execution stage 2 wins"
    assert _section_by_key(response, "risks").text == "guard risk item 1 wins\nguard risk item 2 wins"
    assert response.provenance["wording_source"] == "validated_explanation_blocks"
    assert response.provenance["narrative_source"] == "ai"


def test_explanation_presenter_generic_contract_surfaces_judgment_structure_and_softened_conclusion():
    _, _, result_package = _build_ready_result_package()
    patched_package = deepcopy(result_package)
    patched_package["polish_bundle"] = None
    patched_package["validated_explanation_blocks"] = []
    patched_package["validated_narrative_layer"] = None
    patched_contract = dict(patched_package.get("consulting_min_contract") or {})
    patched_contract.update(
        {
            "context": ["주문 생성 구조 판단을 정리합니다."],
            "problem_definition": ["상태 전이 로직이 여러 위치에 분산됩니다."],
            "decision_question": ["주문 생성 경계를 분리할지 판단해야 합니다."],
            "options": ["옵션 A: 서비스 경계 분리", "옵션 B: 현행 유지"],
            "decision_criteria": ["정합성과 실행 가능성을 우선합니다."],
            "conclusion": ["옵션 A를 우선 적용합니다."],
            "key_reasons": ["상태 전이 로직이 여러 위치에 분산됩니다."],
            "evidence": ["주문 생성 조건이 여러 자산에 걸쳐 흩어져 있습니다."],
            "assumptions": [],
            "missing_information": ["실운영 예외 케이스: 추가 확인 필요"],
        }
    )
    patched_package["consulting_min_contract"] = patched_contract
    patched_package["report_scope"] = ["컨설팅 개요", "현행 구조", "개선 방향", "추진 계획"]
    patched_package["analysis_summary"] = ["현행 구조 요약", "개선 방향 요약"]
    auth = deepcopy(patched_package.get("authoritative_payload") or {})
    appendix = deepcopy(auth.get("appendix") or {})
    appendix["evidence_index"] = [{"locator": "slide:1", "excerpt": "컨설팅 개요와 개선 방향 설명"}]
    auth["appendix"] = appendix
    patched_package["authoritative_payload"] = auth

    presenter = ExplanationPresenter()
    internal = presenter.present(
        project_id="proj_phase3_ready",
        result_package=patched_package,
        audience="manager",
        surface_mode="internal",
    )
    external = presenter.present(
        project_id="proj_phase3_ready",
        result_package=patched_package,
        audience="manager",
        surface_mode="external",
    )

    assert "[상황 / 목적] 주문 생성 구조 판단을 정리합니다." in _section_by_key(internal, "report_purpose").text
    assert "[문제 정의] 상태 전이 로직이 여러 위치에 분산됩니다." in _section_by_key(internal, "report_purpose").text
    assert "[판단 질문] 주문 생성 경계를 분리할지 판단해야 합니다." in _section_by_key(internal, "one_line_conclusion").text
    assert "[결론] 검증 후 적용: 옵션 A를 우선 적용합니다." in _section_by_key(internal, "one_line_conclusion").text
    assert "[근거] 주문 생성 조건이 여러 자산에 걸쳐 흩어져 있습니다." in _section_by_key(internal, "analysis_summary").text
    assert "[선택지 비교] 옵션 A: 서비스 경계 분리" in _section_by_key(internal, "recommended_option").text
    assert "[판단 기준] 정합성과 실행 가능성을 우선합니다." in _section_by_key(internal, "recommended_option").text
    assert "[누락된 정보] 실운영 예외 케이스: 추가 확인 필요" in _section_by_key(internal, "risks").text
    external_recommended = _section_by_key(external, "recommended_option").text
    external_risks = _section_by_key(external, "risks").text
    assert "[결론]" not in external_recommended
    assert "[누락된 정보]" not in external_risks
    recommended_lines = [line.strip() for line in external_recommended.splitlines() if line.strip()]
    assert 1 <= len(recommended_lines) <= 3
    assert all(line.startswith("- ") for line in recommended_lines)
    assert any(token in external_recommended for token in ("실행 착수 가능", "조건 확인 후 실행", "검증 후 적용", "실행 불가"))
    assert any(line.startswith("- 이유: ") for line in recommended_lines)
    assert any(line.startswith("- 추가 확인 필요: ") for line in recommended_lines)
    assert all(len(line) <= 40 for line in recommended_lines)
    assert "우선 검토안" not in external_recommended
    assert "후보" not in external_recommended
    assert "추가 확인 필요: 실운영 예외 케이스: 추가 확인 필요" in external_risks


@pytest.mark.asyncio
async def test_export_surfaces_follow_guard_precedence_like_explanation_surface(tmp_path, monkeypatch):
    _, polish_bundle, result_package = _build_ready_result_package()
    patched_package = _guard_precedence_package(result_package, polish_bundle)
    explanation = ExplanationPresenter().present(
        project_id="proj_phase3_ready",
        result_package=patched_package,
        audience="manager",
    )
    markdown = _result_package_markdown(patched_package, surface_mode="internal")
    slide_schema = _resolve_slide_schema(patched_package, surface_mode="internal")

    assert _section_by_key(explanation, "report_purpose").text == "guard report purpose wins"
    assert _section_by_key(explanation, "one_line_conclusion").text == "guard conclusion wins"
    assert "## 컨설팅 개요" in markdown
    assert "## 컨설팅 전개" in markdown
    assert "### 상황 / 목적" in markdown
    assert "polish report purpose should lose" not in markdown
    assert "validated narrative layer should lose" not in markdown
    assert "guard report purpose wins" not in markdown
    assert slide_schema["slides"][0]["tagline"] == "guard report purpose wins"
    assert slide_schema["slides"][0]["headline"] == "guard conclusion wins"
    assert slide_schema["slides"][0]["absorbed_summary_text"] == "guard summary wins"
    assert any(
        str(slide.get("decision_message") or "").strip() == "guard judgment reason wins"
        for slide in slide_schema.get("slides") or []
        if isinstance(slide, dict)
    )
    assert any(
        "guard recommended option wins" in str(slide.get("absorbed_summary_text") or "")
        for slide in slide_schema.get("slides") or []
        if isinstance(slide, dict) and str(slide.get("slide_type") or "").strip() == "design"
    )
    assert any(
        "guard execution stage 1 wins" in str(slide.get("footer_note") or "")
        for slide in slide_schema.get("slides") or []
        if isinstance(slide, dict) and str(slide.get("slide_type") or "").strip() == "flow"
    )
    assert any(
        "guard risk item 1 wins" in str(slide.get("absorbed_summary_text") or "")
        for slide in slide_schema.get("slides") or []
        if isinstance(slide, dict) and str(slide.get("slide_type") or "").strip() == "as_is_gap"
    )

    class FakeDocService:
        def __init__(self):
            self.docx_content = ""
            self.pptx_payload = None

        def is_available(self):
            return True

        async def generate(self, request):
            suffix = ".docx" if str(request.output_type).endswith("DOCX") else ".pptx"
            if suffix == ".docx":
                self.docx_content = request.content
            else:
                self.pptx_payload = request.payload
            output_path = tmp_path / f"guard_export{suffix}"
            output_path.write_bytes(b"ok")
            return type("Response", (), {"output_path": str(output_path)})()

    fake_doc_service = FakeDocService()
    monkeypatch.setattr(app_state, "doc_service", fake_doc_service, raising=False)
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

    docx_path, _ = await _generate_result_package_docx(
        project,
        patched_package,
    )
    await _result_package_pptx_response(
        project,
        patched_package,
    )

    assert "## 컨설팅 개요" in fake_doc_service.docx_content
    assert "guard report purpose wins" not in fake_doc_service.docx_content
    assert "guard conclusion wins" not in fake_doc_service.docx_content
    assert "guard recommended option wins" not in fake_doc_service.docx_content
    assert "guard execution stage 1 wins" not in fake_doc_service.docx_content
    assert "guard risk item 1 wins" not in fake_doc_service.docx_content
    assert fake_doc_service.pptx_payload["slides"][0]["tagline"] == "guard report purpose wins"
    assert fake_doc_service.pptx_payload["slides"][0]["headline"] == "guard conclusion wins"
    assert any(
        "guard recommended option wins" in str(slide.get("absorbed_summary_text") or "")
        for slide in fake_doc_service.pptx_payload.get("slides") or []
        if isinstance(slide, dict) and str(slide.get("slide_type") or "").strip() == "design"
    )
    assert any(
        "guard execution stage 1 wins" in str(slide.get("footer_note") or "")
        for slide in fake_doc_service.pptx_payload.get("slides") or []
        if isinstance(slide, dict) and str(slide.get("slide_type") or "").strip() == "flow"
    )
    assert any(
        "guard risk item 1 wins" in str(slide.get("absorbed_summary_text") or "")
        for slide in fake_doc_service.pptx_payload.get("slides") or []
        if isinstance(slide, dict) and str(slide.get("slide_type") or "").strip() == "as_is_gap"
    )
    assert str(docx_path).endswith(".docx")


def test_operational_source_markdown_export_uses_analysis_first_headings():
    _, _, result_package = _build_fx_fifo_operational_result_package()
    markdown = _result_package_markdown(result_package, surface_mode="internal")

    assert "## 분석 목적" in markdown
    assert "## 현행 분석 요약" in markdown
    assert "## 자산 정체" in markdown
    assert "## 우선 검토 기준" not in markdown
    assert "## 후속 개선 검토" not in markdown
    assert "## 후속 확인 항목" not in markdown
    assert "## 컨설팅 개요" not in markdown
    assert "## 검토 순서" in markdown
    assert "## 운영 리스크" not in markdown
    assert "## 핵심 요약" not in markdown
    assert "## 추천안 설명" not in markdown
    assert "TN_FORINS" not in markdown
    assert "GL_INTERFACE" not in markdown
    assert "GAP_AMT" not in markdown
    assert "OUT_AMT0" not in markdown


def test_operational_source_markdown_export_top_paragraph_drops_support_prefix():
    _, _, result_package = _build_fx_fifo_operational_result_package()
    markdown = _result_package_markdown(result_package, surface_mode="internal")

    assert _first_section_paragraph(markdown).startswith("외화 입금, 출금, FIFO lot 소진")
    assert not _first_section_paragraph(markdown).startswith("보조 판단:")


@pytest.mark.parametrize(
    ("state", "planner_summary_patch", "schedule_summary_patch", "expected_label"),
    [
        ("blocked", {"blocked_execution": True, "first_stage_kind": "blocker_resolution"}, {"schedule_mode": "blocked_first"}, "실행 불가"),
        ("review_required", {"verification_first": True, "first_stage_kind": "verification_first"}, {"schedule_mode": "verification_first"}, "검증 후 적용"),
        ("conditional", {"first_stage_kind": "precondition_check"}, {"schedule_mode": "conditional_first"}, "조건 확인 후 실행"),
        ("assertive", {"first_stage_kind": "execution_start"}, {"schedule_mode": "execution_first"}, "실행 착수 가능"),
    ],
)
def test_external_surface_uses_only_standard_state_wording(state, planner_summary_patch, schedule_summary_patch, expected_label):
    _, _, result_package = _build_ready_result_package()
    patched = deepcopy(result_package)
    governance = deepcopy(((patched.get("extensions") or {}).get("decision_governance") or {}))
    governance["recommendation_strength"] = state
    planner_summary = deepcopy(governance.get("planner_summary") or {})
    planner_summary.update(planner_summary_patch)
    governance["planner_summary"] = planner_summary
    schedule_summary = deepcopy(governance.get("schedule_summary") or {})
    schedule_summary.update(schedule_summary_patch)
    governance["schedule_summary"] = schedule_summary
    patched.setdefault("extensions", {})["decision_governance"] = governance

    response = ExplanationPresenter().present(
        project_id="proj_phase3_ready",
        result_package=patched,
        audience="manager",
        surface_mode="external",
    )

    external_text = "\n".join(
        [card.body for card in response.summary_cards] + [section.text for section in response.section_views]
    )
    assert expected_label in external_text
    assert "우선 검토안" not in external_text
    assert "검토안" not in external_text
    assert "안전한 선택" not in external_text


def test_external_surface_document_input_keeps_consulting_style_titles():
    _, _, result_package = _build_ready_result_package()
    patched = deepcopy(result_package)
    patched["report_scope"] = ["컨설팅 개요", "현행 구조", "개선 방향", "추진 계획"]
    patched["consulting_min_contract"] = {
        "context": ["컨설팅 보고서 개요를 정리합니다."],
        "problem_definition": ["현행 구조의 한계를 설명합니다."],
        "decision_question": ["개선 방향을 어떻게 정리할지 검토합니다."],
        "options": ["옵션 A: 단계적 개선"],
        "decision_criteria": ["효과와 실행 가능성을 함께 봅니다."],
        "evidence": ["현행 운영 구조와 개선 방향이 문서에 정리돼 있습니다."],
        "missing_information": ["추가 보고서 확인 필요"],
        "as_is": ["현행 구조와 개선 포인트를 문서로 정리합니다."],
        "process_flow": ["1단계: 현행 구조 정리", "2단계: 개선 방향 검토"],
        "rules": ["문서 기준과 추진 계획을 함께 확인합니다."],
        "risks": ["세부 배경 자료가 부족하면 판단이 늦어질 수 있습니다."],
        "actions": ["개선 방향과 추진 계획을 정리합니다."],
    }
    patched["analysis_summary"] = ["현행 구조 요약", "개선 방향 요약"]
    auth = deepcopy(patched.get("authoritative_payload") or {})
    appendix = deepcopy(auth.get("appendix") or {})
    appendix["evidence_index"] = [{"locator": "slide:1", "excerpt": "컨설팅 개요와 개선 방향 설명"}]
    auth["appendix"] = appendix
    patched["authoritative_payload"] = auth

    response = ExplanationPresenter().present(
        project_id="proj_phase3_ready",
        result_package=patched,
        audience="manager",
        surface_mode="external",
    )

    assert [card.title for card in response.summary_cards] == ["핵심 판단", "왜 이 방향인가", "다음 단계"]
    assert _section_by_key(response, "execution_plan").title != "코드 분석 포인트"


def test_external_surface_code_input_switches_to_technical_style():
    _, _, result_package = _build_ready_result_package()
    response = ExplanationPresenter().present(
        project_id="proj_phase3_ready",
        result_package=result_package,
        audience="manager",
        surface_mode="external",
    )

    assert [card.title for card in response.summary_cards] == ["핵심 문제", "영향", "권장 조치"]
    assert _section_by_key(response, "recommended_option").title == "권장 조치"
    assert _section_by_key(response, "execution_plan").title == "검증 포인트"
    assert _section_by_key(response, "risks").title == "영향"
    assert "선택지:" not in _section_by_key(response, "recommended_option").text


def test_external_surface_mixed_input_adds_technical_block_but_keeps_document_base():
    _, _, result_package = _build_ready_result_package()
    patched = deepcopy(result_package)
    patched["report_scope"] = ["컨설팅 개요", "현행 구조", "저장 전 차단 조건", "SQL 조건 매핑"]
    patched["consulting_min_contract"] = {
        **(patched.get("consulting_min_contract") or {}),
        "context": ["컨설팅 보고서와 코드 구조를 함께 검토합니다."],
        "problem_definition": ["현행 구조 설명과 저장 검증 규칙이 함께 존재합니다."],
        "decision_question": ["개선 방향과 코드 적용 기준을 함께 검토합니다."],
        "evidence": [
            "현행 문서 설명과 SQL 조건 매핑이 함께 확인됩니다.",
            "저장 전 차단 조건과 예외 처리 기준이 코드에 존재합니다.",
        ],
    }
    auth = deepcopy(patched.get("authoritative_payload") or {})
    appendix = deepcopy(auth.get("appendix") or {})
    appendix["evidence_index"] = [
        {"locator": "slide:1", "excerpt": "컨설팅 개요와 개선 방향 설명"},
        {"locator": "line:10", "excerpt": "SELECT * FROM orders WHERE status = :status"},
    ]
    auth["appendix"] = appendix
    patched["authoritative_payload"] = auth

    response = ExplanationPresenter().present(
        project_id="proj_phase3_ready",
        result_package=patched,
        audience="manager",
        surface_mode="external",
    )

    assert [card.title for card in response.summary_cards] == ["핵심 판단", "왜 이 방향인가", "다음 단계"]
    assert _section_by_key(response, "execution_plan").title == "코드 분석 포인트"
    assert "검증 포인트:" in _section_by_key(response, "execution_plan").text


def test_operational_source_markdown_export_dedupes_sections_and_preserves_registry_order():
    _, _, result_package = _build_fx_fifo_operational_result_package()
    markdown = _result_package_markdown(result_package, surface_mode="internal")

    assert _markdown_headings(markdown, level=2) == [
        "## 분석 목적",
        "## 현행 분석 요약",
        "## 자산 정체",
        "## 핵심 객체",
        "## 검토 순서",
    ]
    assert markdown.count("## 핵심 객체") == 1
    assert markdown.count("## 검토 순서") == 1
    assert markdown.count("## 운영 리스크") == 0
    assert markdown.count("## 현행 분석 요약") == 1
    assert "## 현행 분석 개요" not in markdown
    assert "## 처리 흐름 검토" not in markdown
    assert "## 분석 단계" not in markdown


def test_operational_source_markdown_export_normalizes_sentence_stitch_regression():
    _, _, result_package = _build_fx_fifo_operational_result_package()
    markdown = _result_package_markdown(result_package, surface_mode="internal")

    assert ".." not in markdown
    assert "입니다.입니다" not in markdown
    assert "합니다.입니다" not in markdown
    bullet_lines = [line.strip() for line in markdown.splitlines() if line.startswith("- ")]
    assert len(bullet_lines) == len(set(bullet_lines))


def test_operational_source_markdown_export_normalizes_prefix_whitespace_and_duplicate_bullets():
    _, _, result_package = _build_fx_fifo_operational_result_package()
    patched_package = deepcopy(result_package)
    patched_package["validated_explanation_blocks"] = [
        {
            "block_id": "report_purpose",
            "resolved_lines": ["보조 판단:   외화  입금,   출금   흐름을   분석하기 위한   보고서입니다.   "],
            "deterministic_lines": ["보조 판단:   외화  입금,   출금   흐름을   분석하기 위한   보고서입니다.   "],
        },
        {
            "block_id": "execution_plan",
            "resolved_lines": [
                "- - 1단계:  흐름을  구조화합니다..",
                "• • 1단계: 흐름을 구조화합니다..",
                "• • 2단계: 계산 기준을 검증합니다.입니다.",
            ],
            "deterministic_lines": [
                "- - 1단계:  흐름을  구조화합니다..",
                "• • 1단계: 흐름을 구조화합니다..",
                "• • 2단계: 계산 기준을 검증합니다.입니다.",
            ],
        },
    ]
    markdown = _result_package_markdown(patched_package, surface_mode="internal")

    assert _first_section_paragraph(markdown) == "외화 입금, 출금 흐름을 분석하기 위한 보고서입니다."
    assert "\n\n\n" not in markdown
    assert "- - " not in markdown
    assert "• • " not in markdown
    assert ".." not in markdown
    assert "입니다.입니다" not in markdown
    assert markdown.count("- 1단계: 흐름을 구조화합니다.") == 1


def test_internal_full_markdown_keeps_review_appendix_outside_registry_body():
    _, _, result_package = _build_fx_fifo_operational_result_package()

    deck_only = _result_package_markdown(result_package, surface_mode="internal")
    full = _result_package_markdown(result_package, surface_mode="internal", internal_export_mode="full")
    body = full.split("## 참고 구조 비교", 1)[0]

    assert "## 참고 구조 비교" in full
    assert _markdown_headings(body, level=2) == _markdown_headings(deck_only, level=2)
    assert body.count("## 핵심 객체") == 1
    assert body.count("## 검토 순서") == 1
    assert body.count("## 운영 리스크") == 0


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
async def test_operational_source_result_question_answering_uses_display_strategy_for_manager_surface():
    _, _, result_package = _build_fx_fifo_operational_result_package()
    service = ResultQuestionAnsweringService()

    manager = await service.answer(
        project_id="proj_phase3_fx_fifo",
        result_package=result_package,
        question="왜 이 방향이야?",
        audience="manager",
        llm_service=None,
    )
    developer = await service.answer(
        project_id="proj_phase3_fx_fifo",
        result_package=result_package,
        question="왜 이 방향이야?",
        audience="developer",
        llm_service=None,
    )

    assert "현행 분석 우선" in manager.answer
    assert "리팩터링 우선" not in manager.answer
    assert "리팩터링 우선" in developer.answer
    assert "현행 분석 우선" in developer.answer


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
    assert [card["title"] for card in external_body["summary_cards"]] == ["핵심 문제", "영향", "권장 조치"]
    assert [section["section_key"] for section in external_body["section_views"]] == ["recommended_option", "execution_plan", "risks"]
    assert [section["title"] for section in external_body["section_views"]] == ["권장 조치", "검증 포인트", "영향"]
    external_text = " ".join(card["body"] for card in external_body["summary_cards"]) + " " + " ".join(section["text"] for section in external_body["section_views"])
    assert "decision type" not in external_text.lower()
    assert "severity" not in external_text.lower()
    assert "blast radius" not in external_text.lower()
    assert "해야" not in external_text
    assert "필요합니다" not in external_text
    assert "[상황 / 목적]" not in external_text
    assert "[문제 정의]" not in external_text
    assert "[핵심 이유]" not in external_text
    assert "Decision Brief" not in external_text
    assert "ready" not in external_text.lower()
    assert any(token in external_text for token in ("실행 착수 가능", "조건 확인 후 실행", "검증 후 적용", "실행 불가"))
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
