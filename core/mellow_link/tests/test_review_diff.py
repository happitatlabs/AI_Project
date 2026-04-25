from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from mellow_link.infra import ModernizationProject
from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.routers.projects import _result_package_markdown, _surface_filtered_result_package, build_result_package
from mellow_link.services.refactoring_support_engine.decision_engine import DecisionEngine
from mellow_link.services.refactoring_support_engine.diagnosis_engine import DiagnosisEngine
from mellow_link.services.refactoring_support_engine.improvement_planner import ImprovementPlanner
from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
from mellow_link.services.refactoring_support_engine.result_packager import ResultPackager
from mellow_link.services.refactoring_support_engine.schemas import EvidenceLink
from mellow_link.services.refactoring_support_engine.structure_analyzer import StructureAnalyzer

from .refactoring_support_test_utils import build_safe_bundle, load_expansion_sample_case, load_sample_case

MELLOW_LINK_ROOT = Path(__file__).resolve().parents[1]


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


def _package_result(asset_specs, goal: str, constraints: list[str] | None = None):
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal=goal,
        safe_bundle=build_safe_bundle(asset_specs),
        constraints=constraints or [],
    )
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    decisions = DecisionEngine().run(prepared, structure, diagnosis, service)
    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, decisions, service)
    result = ResultPackager().package(prepared, structure, diagnosis, decisions, improvement, service)
    return result


def test_review_diff_marks_blocked_migration_for_goal_only_contamination():
    case = load_expansion_sample_case("01_crud_simple")

    result = _package_result(
        case["asset_specs"],
        goal="reports CRUD 구조를 점검하고 전환 초안을 작성하라.",
    )

    review_diff = result.extensions["review_diff"]
    markdown = review_diff["markdown"]

    assert review_diff["decision_diff"]["synthetic_signal_detected"] is True
    assert review_diff["decision_diff"]["blocked_decisions"]
    assert review_diff["decision_diff"]["blocked_decisions"][0]["decision_type"] == "migration_consideration"
    assert "goal wording only (contamination)" in review_diff["decision_diff"]["block_reasons"]
    assert markdown.startswith("## Decision Result")
    assert "✖ blocked: migration_consideration" in markdown
    assert "Reason:" in markdown
    assert "- goal wording only (contamination)" in markdown
    assert "- synthetic_signal_detected: True" in markdown
    assert "- decision_engine_guard_applied: True" in markdown
    assert "- result_packager_guard_applied: False" in markdown


def test_review_diff_keeps_block_reason_when_only_document_migration_evidence_exists():
    result = _package_result(
        [
            {
                "name": "legacy_order_page.jsp",
                "content": """
<% String sql = "SELECT * FROM orders WHERE status = 'READY'"; %>
<button onclick="submitOrder()">submit</button>
                """,
            },
            {
                "name": "order_service.py",
                "content": """
class OrderService:
    def submit(self, order):
        if order.status == "READY" and order.amount > 1000:
            return repo.save(order)
                """,
            },
            {
                "name": "approval_service.py",
                "content": """
class ApprovalService:
    def approve(self, order):
        if order.status == "READY" and order.amount > 1000:
            return repo.save(order)
                """,
            },
            {
                "name": "migration_plan.md",
                "content": """
레거시 승인 화면을 Spring Boot REST API와 React Admin으로 분리한다.
서비스 분리와 단계적 마이그레이션을 고려한다.
                """,
            },
        ],
        goal="legacy order approval flow migration plan",
    )

    review_diff = result.extensions["review_diff"]
    decision_types = [item["decision_type"] for item in review_diff["decision_diff"]["allowed_decisions"]]
    markdown = review_diff["markdown"]

    assert review_diff["decision_diff"]["synthetic_signal_detected"] is True
    assert review_diff["decision_diff"]["blocked_decisions"]
    assert "migration_consideration" not in decision_types
    assert "goal wording only (contamination)" in markdown
    assert "✖ blocked: migration_consideration" in markdown
    assert "✔ allowed: migration_consideration" not in markdown


def test_review_diff_builds_structural_and_evidence_sections_for_query_filter_refactor():
    case = load_expansion_sample_case("04_db_heavy_query_filter")

    result = _package_result(
        case["asset_specs"],
        goal="요청 검색 구조를 분석하고 조회 조건 정리를 제안하라.",
    )

    review_diff = result.extensions["review_diff"]
    markdown = review_diff["markdown"]

    assert review_diff["structural_diff"]["component_structure"]
    assert review_diff["decision_diff"]["allowed_decisions"]
    assert "## Decision Result" in markdown
    assert "## Why this decision?" in markdown
    assert "## Structural Difference" in markdown
    assert markdown.index("## Decision Result") < markdown.index("## Why this decision?") < markdown.index("## Structural Difference")
    assert "### Evidence" in markdown
    assert "### Observed" in markdown
    assert "### Expected Pattern" in markdown
    assert review_diff["evidence_diff"]["leak_traces"] or review_diff["evidence_diff"]["repeated_fingerprints"]
    assert any(
        item["detector_id"] == "query_filter_leak"
        for item in review_diff["evidence_diff"]["detector_evidence_map"]
    )
    assert review_diff["code_diff"]["available"] is True
    assert review_diff["code_diff"]["snippets"]
    assert review_diff["code_diff"]["snippets"][0]["type"] == "before_after"
    assert "observed" in review_diff["code_diff"]["snippets"][0]
    assert "expected_pattern" in review_diff["code_diff"]["snippets"][0]
    assert review_diff["code_diff"]["snippets"][0]["difference_summary"]
    assert "before" not in review_diff["code_diff"]["snippets"][0]
    assert "after" not in review_diff["code_diff"]["snippets"][0]
    assert review_diff["markdown"].index("## Why this decision?") < review_diff["markdown"].index("## 현재 구조 vs 권장 구조 비교") < review_diff["markdown"].index("## Structural Difference")
    assert "이 비교는 실제 패치가 아니라, 현재 구조와 권장 패턴의 차이를 검토하기 위한 근거 예시입니다." in review_diff["markdown"]
    assert "#### observed" in review_diff["markdown"]
    assert "#### expected_pattern" in review_diff["markdown"]
    assert "#### difference_summary" in review_diff["markdown"]


def test_review_diff_code_diff_stays_unavailable_for_noise_only_sample():
    result = _package_result(
        [
            {
                "name": "simple_report.sql",
                "content": "SELECT id, status FROM reports ORDER BY created_at DESC",
            },
            {
                "name": "simple_page.html",
                "content": "<button>load</button>",
            },
        ],
        goal="단순 조회 페이지를 확인하라.",
    )

    review_diff = result.extensions["review_diff"]

    assert review_diff["code_diff"]["available"] is False
    assert review_diff["code_diff"]["snippets"] == []


def test_review_diff_code_diff_uses_asset_name_fallback_when_evidence_asset_id_is_empty():
    packager = ResultPackager()
    prepared = SimpleNamespace(
        safe_bundle=SimpleNamespace(
            sources=[
                SimpleNamespace(
                    asset_id="asset_001",
                    name="claim_approval_service.py",
                    content="""
def approve(claim, user):
    if claim["amount"] >= 10000000 and user["dept"] != "CLAIM_AUDIT":
        raise PermissionError("blocked")
    return save_claim(claim)
                    """.strip(),
                )
            ]
        )
    )
    evidence = EvidenceLink(
        evidence_id="EVID_TEST",
        asset_id="",
        asset_name="claim_approval_service.py",
        asset_type="source",
        locator="line:2",
        excerpt='if claim["amount"] >= 10000000 and user["dept"] != "CLAIM_AUDIT":',
        fingerprint='if claim["STR"] >= NUM and user["STR"] != "STR":',
    )
    asset_text_map = packager._source_text_map(prepared)

    snippet = packager._build_code_diff_snippet(
        detector_id="rule_scatter",
        issue_summary="Rule scatter detected",
        evidence_ids=["EVID_TEST"],
        evidence_map={"EVID_TEST": evidence},
        asset_text_map=asset_text_map,
    )

    assert snippet is not None
    assert snippet["file"] == "claim_approval_service.py"
    assert snippet["observed"]
    assert snippet["expected_pattern"]
    assert snippet["difference_summary"]


def test_review_diff_code_diff_uses_locator_context_when_excerpt_anchor_does_not_match_exact_line():
    packager = ResultPackager()
    prepared = SimpleNamespace(
        safe_bundle=SimpleNamespace(
            sources=[
                SimpleNamespace(
                    asset_id="asset_001",
                    name="order_service.py",
                    content="""
class OrderService:
    def submit(self, order_data, retry_flag, note_text, repo):
        validator = OrderValidator()
        if not validator.is_valid(order_data):
            return {"error": "invalid"}
        return repo.save(order_data)
                    """.strip(),
                )
            ]
        )
    )
    evidence = EvidenceLink(
        evidence_id="EVID_LOCATOR",
        asset_id="asset_001",
        asset_name="order_service.py",
        asset_type="source",
        locator="line:2",
        excerpt="def submit(self, order_data, retry_flag, note_text, repo): validator = OrderValidator()",
        fingerprint="def submit(self, order_data, retry_flag, note_text, repo):",
    )

    snippet = packager._build_code_diff_snippet(
        detector_id="validation_guard_leak",
        issue_summary="Validation is mixed into the submit path",
        evidence_ids=["EVID_LOCATOR"],
        evidence_map={"EVID_LOCATOR": evidence},
        asset_text_map=packager._source_text_map(prepared),
    )

    assert snippet is not None
    assert "class OrderService:" in snippet["observed"]
    assert "validator = OrderValidator()" in snippet["observed"]
    assert "\n" in snippet["observed"]
    assert "def submit(self, order_data, retry_flag, note_text, repo):" in snippet["expected_pattern"]
    assert "validate_submit_input(order_data, retry_flag, note_text)" in snippet["expected_pattern"]
    assert "return repo.save(validation.payload)" in snippet["expected_pattern"]


def test_review_diff_code_diff_grounds_sql_expected_pattern_to_observed_query_shape():
    packager = ResultPackager()
    snippet = packager._build_grounded_expected_pattern(
        detector_id="state_transition_leak",
        asset_type="sql",
        observed="""
FROM legacy_orders o
JOIN customer_profile p ON p.customer_id = o.customer_id
WHERE o.status_code = 'READY'
  AND p.contact_email = '[EMAIL]'
ORDER BY o.created_at DESC;
        """.strip(),
    )

    assert snippet.startswith("SELECT *")
    assert "FROM legacy_orders o" in snippet
    assert "WHERE o.status_code = :status_code" in snippet
    assert "AND p.contact_email = :contact_email" in snippet
    assert "TransitionPolicy01" not in snippet


def test_duplicate_logic_grounded_pattern_reuses_existing_input_name_instead_of_normalized_temp():
    packager = ResultPackager()
    snippet = packager._build_grounded_expected_pattern(
        detector_id="duplicate_logic_candidate",
        asset_type="source",
        observed="""
class OrderClosureService:
    def submit_order(self, order_data, retry_flag, note_text, repo):
        validator = OrderValidator()
        if not validator.is_valid(order_data):
            return {"error": "invalid"}
        return repo.save(order_data)
        """.strip(),
    )

    assert "normalized =" not in snippet
    assert "order_data = normalize_submit_order_input(order_data, retry_flag, note_text)" in snippet
    assert "if not order_data.valid:" in snippet
    assert "return repo.save(order_data.payload)" in snippet


def test_review_diff_preserves_multiline_snippets_and_masks_sensitive_literals():
    case = load_sample_case("ui_01_normal_balanced_upload")

    result = _package_result(
        case["asset_specs"],
        goal=case["goal"],
        constraints=case["constraints"],
    )

    snippets = result.extensions["review_diff"]["code_diff"]["snippets"]
    order_service = next(item for item in snippets if item["file"] == "order_service.py")
    order_lookup = next(item for item in snippets if item["file"] == "order_lookup.sql")

    assert "\n" in order_service["observed"]
    assert "\n" in order_service["expected_pattern"]
    assert "ops.order@example.com" not in order_service["observed"]
    assert "/internal/orders/submit" not in order_service["observed"]
    assert "[EMAIL]" in order_service["observed"]
    assert "[PATH]" in order_service["observed"]
    assert "def submit_order(self, order_data, retry_flag, note_text, repo):" in order_service["expected_pattern"]
    assert "build_submit_order_command(order_data, retry_flag, note_text)" in order_service["expected_pattern"]
    assert "\n" in order_lookup["observed"]
    assert "ops.order@example.com" not in order_lookup["observed"]
    assert "[EMAIL]" in order_lookup["observed"]
    assert "WHERE o.status_code = :status_code" in order_lookup["expected_pattern"]
    assert "AND p.contact_email = :contact_email" in order_lookup["expected_pattern"]


def test_internal_markdown_export_includes_review_diff_when_available():
    case = load_expansion_sample_case("04_db_heavy_query_filter")
    result = _package_result(
        case["asset_specs"],
        goal="요청 검색 구조를 분석하고 조회 조건 정리를 제안하라.",
    )
    project = ModernizationProject(
        id="proj_review_export",
        user_id=1,
        session_id="sess_review_export",
        run_id="run_review_export",
        project_name="Review Export",
        client_name="OO카드",
        template_key="default_modernization_v1",
        template_mode="recommended",
        constraints_json="[]",
        upload_session_id="upload_review_export",
        asset_manifest_json="[]",
        status="completed",
    )
    pkg = build_result_package(
        project,
        {"status": "completed", "run_id": project.run_id},
        result,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )

    markdown = _result_package_markdown(pkg, surface_mode="internal", internal_export_mode="full")

    assert markdown.startswith("# 결과 패키지 - Review Export")
    assert "## 참고 구조 비교" in markdown
    assert "### Decision Result" in markdown
    assert "### Why this decision?" in markdown
    assert "### 현재 구조 vs 권장 구조 비교" in markdown
    assert "### Structural Difference" in markdown
    assert "synthetic_signal_detected" in markdown


def test_build_result_package_preserves_multiline_structure_comparison_snippets():
    case = load_sample_case("ui_01_normal_balanced_upload")
    result = _package_result(
        case["asset_specs"],
        goal=case["goal"],
        constraints=case["constraints"],
    )
    project = ModernizationProject(
        id="proj_structure_multiline",
        user_id=1,
        session_id="sess_structure_multiline",
        run_id="run_structure_multiline",
        project_name="구조 비교 멀티라인",
        client_name="OO카드",
        template_key="default_modernization_v1",
        template_mode="recommended",
        constraints_json="[]",
        upload_session_id="upload_structure_multiline",
        asset_manifest_json="[]",
        status="completed",
    )

    pkg = build_result_package(
        project,
        {"status": "completed", "run_id": project.run_id},
        result,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )

    comparison = pkg["structure_comparison"]

    assert comparison["available"] is True
    assert comparison["items"]
    order_service = next(item for item in comparison["items"] if item["file"] == "order_service.py")
    assert "\n" in order_service["current_structure"]
    assert "\n" in order_service["recommended_structure"]
    assert "ops.order@example.com" not in order_service["current_structure"]
    assert "/internal/orders/submit" not in order_service["current_structure"]
    assert "[EMAIL]" in order_service["current_structure"]
    assert "[PATH]" in order_service["current_structure"]
    assert "def submit_order(self, order_data, retry_flag, note_text, repo):" in order_service["recommended_structure"]
    assert "execute_submit_order(command, repo)" in order_service["recommended_structure"]


def test_build_result_package_refreshes_legacy_review_diff_expected_patterns_for_display():
    case = load_sample_case("ui_01_normal_balanced_upload")
    result = _package_result(
        case["asset_specs"],
        goal=case["goal"],
        constraints=case["constraints"],
    )
    legacy_review_diff = dict(result.extensions["review_diff"])
    legacy_code_diff = dict(legacy_review_diff["code_diff"])
    legacy_snippets = []
    for snippet in legacy_code_diff["snippets"]:
        snippet_copy = dict(snippet)
        snippet_copy["expected_pattern"] = "\n".join(
            [
                "normalized = RuleFragment01.normalize(input_data)",
                "if not normalized.valid:",
                "    return normalized.errors",
                "return Service01.apply(normalized.payload)",
            ]
        )
        legacy_snippets.append(snippet_copy)
    legacy_code_diff["snippets"] = legacy_snippets
    legacy_review_diff["code_diff"] = legacy_code_diff
    legacy_review_diff["markdown"] = "legacy"
    legacy_result = result.model_copy(
        update={
            "extensions": {
                **result.extensions,
                "review_diff": legacy_review_diff,
            }
        }
    )
    project = ModernizationProject(
        id="proj_structure_refresh",
        user_id=1,
        session_id="sess_structure_refresh",
        run_id="run_structure_refresh",
        project_name="구조 비교 갱신",
        client_name="OO카드",
        template_key="default_modernization_v1",
        template_mode="recommended",
        constraints_json="[]",
        upload_session_id="upload_structure_refresh",
        asset_manifest_json="[]",
        status="completed",
    )

    pkg = build_result_package(
        project,
        {"status": "completed", "run_id": project.run_id},
        legacy_result,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )

    snippets = pkg["extensions"]["review_diff"]["code_diff"]["snippets"]
    order_service = next(item for item in snippets if item["file"] == "order_service.py")
    order_lookup = next(item for item in snippets if item["file"] == "order_lookup.sql")
    assert "RuleFragment01" not in order_service["expected_pattern"]
    assert "normalized =" not in order_service["expected_pattern"]
    assert "def submit_order(self, order_data, retry_flag, note_text, repo):" in order_service["expected_pattern"]
    assert "SELECT *" in order_lookup["expected_pattern"]
    assert "WHERE o.status_code = :status_code" in order_lookup["expected_pattern"]
    assert "normalized = RuleFragment01.normalize(input_data)" not in pkg["extensions"]["review_diff"]["markdown"]
    assert "return Service01.apply(normalized.payload)" not in pkg["extensions"]["review_diff"]["markdown"]


def test_build_result_package_display_supports_option_comparison_and_deferred_impact():
    case = load_sample_case("ui_01_normal_balanced_upload")
    result = _package_result(
        case["asset_specs"],
        goal=case["goal"],
        constraints=case["constraints"],
    )
    project = ModernizationProject(
        id="proj_display_decision_aids",
        user_id=1,
        session_id="sess_display_decision_aids",
        run_id="run_display_decision_aids",
        project_name="판단 보조 UI",
        client_name="OO카드",
        template_key="default_modernization_v1",
        template_mode="recommended",
        constraints_json="[]",
        upload_session_id="upload_display_decision_aids",
        asset_manifest_json="[]",
        status="completed",
    )

    pkg = build_result_package(
        project,
        {"status": "completed", "run_id": project.run_id},
        result,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )

    grounded_rules = pkg["display"]["sections"]["grounded_rules"]["items"]
    priorities = {item["priority"] for item in grounded_rules}
    assert "P0" in priorities
    assert len(priorities) >= 2
    assert all(item["unchanged_consequence"] for item in grounded_rules)
    assert all(item["priority_reason"] for item in grounded_rules)

    options = pkg["display"]["sections"]["design_options"]["items"]
    assert [item["priority"] for item in options[:3]] == ["P0", "P1", "P2"]
    first_option = options[0]
    assert first_option["unchanged_consequence"]
    assert first_option["priority_reason"]
    assert [point["label"] for point in first_option["comparison_points"]] == [
        "구조 개선 폭",
        "적용 범위",
        "구현 난이도",
        "예상 효과",
        "선행 조건",
        "미조치 시 영향",
    ]

    first_plan = pkg["display"]["sections"]["execution_plan"]["items"][0]
    assert first_plan["priority"] == "P0"
    assert first_plan["priority_reason"]
    assert first_plan["unchanged_consequence"]


def test_build_result_package_option_comparison_surface_uses_comparison_first_intro():
    case = load_sample_case("13_document_option_boundary")
    service = RebuildAssistantService()
    result = service.build_result(
        service.prepare_safe_bundle_input(
            goal=case["goal"],
            safe_bundle=case["safe_bundle"],
            constraints=case["constraints"],
        )
    )
    polish_bundle = service.build_polish_bundle(result, audience="manager", delivery_mode="client_report").model_dump()
    project = ModernizationProject(
        id="proj_option_surface",
        user_id=1,
        session_id="sess_option_surface",
        run_id="run_option_surface",
        project_name="옵션 비교 surface",
        client_name="OO카드",
        template_key="default_modernization_v1",
        template_mode="recommended",
        constraints_json="[]",
        upload_session_id="upload_option_surface",
        asset_manifest_json="[]",
        status="completed",
    )

    pkg = build_result_package(
        project,
        {"status": "completed", "run_id": project.run_id},
        result,
        assets=[],
        polish_bundle=polish_bundle,
        app_version="0.1.0",
    )
    markdown = _result_package_markdown(pkg, surface_mode="internal")
    surface_wording = (((pkg.get("extensions") or {}).get("decision_governance") or {}).get("surface_wording") or {})

    assert surface_wording.get("mode") == "comparison_first_option"
    assert surface_wording.get("display_strategy") == "비교 기준 우선"
    assert "## 비교 목적" in markdown
    assert "## 선택지 요약" in markdown
    assert "## 비교 기준" in markdown
    assert "## 추천 근거" in markdown
    assert "## 도입 단계" in markdown
    assert "Role: Decision" in markdown
    assert "복수 선택지를 비교 기준 우선 원칙으로 검토해" in markdown
    assert "비교 관점: 비교 기준 우선 기준으로" in markdown
    assert "## 보고 목적" not in markdown
    assert "보조 판단: 입력 검증" not in markdown
    assert "운영 판단:" not in markdown
    assert _first_section_paragraph(markdown).startswith("복수 선택지를 비교 기준 우선 원칙으로 검토해")
    assert not _first_section_paragraph(markdown).startswith("보조 판단:")
    assert _markdown_headings(markdown, level=2) == [
        "## 비교 목적",
        "## 선택지 요약",
        "## 비교 기준",
        "## 추천 근거",
        "## 도입 단계",
    ]
    assert "## 선택지 비교 개요" not in markdown
    assert "## 실행 로드맵" not in markdown
    assert "## 선택 시 유의점" not in markdown


def test_surface_filtered_result_package_marks_hidden_by_policy_when_review_diff_exists():
    case = load_expansion_sample_case("04_db_heavy_query_filter")
    result = _package_result(
        case["asset_specs"],
        goal="요청 검색 구조를 분석하고 조회 조건 정리를 제안하라.",
    )
    project = ModernizationProject(
        id="proj_surface_filtered_review",
        user_id=1,
        session_id="sess_surface_filtered_review",
        run_id="run_surface_filtered_review",
        project_name="Surface Filtered Review",
        client_name="OO카드",
        template_key="default_modernization_v1",
        template_mode="recommended",
        constraints_json="[]",
        upload_session_id="upload_surface_filtered_review",
        asset_manifest_json="[]",
        status="completed",
    )
    pkg = build_result_package(
        project,
        {"status": "completed", "run_id": project.run_id},
        result,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )

    filtered = _surface_filtered_result_package(pkg, surface_mode="external")

    assert pkg["structure_comparison"]["available"] is True
    assert pkg["structure_comparison"]["items"]
    assert "review_diff" in (pkg.get("extensions") or {})
    assert "review_diff" not in (filtered.get("extensions") or {})
    assert "decision_governance" not in (filtered.get("extensions") or {})
    assert filtered["structure_comparison"]["available"] is True
    assert filtered["structure_comparison"]["items"][0]["current_structure"]
    assert filtered["structure_comparison"]["items"][0]["recommended_structure"]
    assert filtered["structure_comparison"]["items"][0]["difference_summary"]
    assert filtered["display"]["hero"]["headline"]
    assert "state" not in filtered["diagnosis"]
    assert "state" not in filtered["design"]
    assert "state" not in filtered["transition_draft"]
    assert "title" not in filtered["executive_summary"]
    assert "state" not in filtered["executive_summary"]
    assert filtered["provenance"]["surface_access"]["access_profile"] == "external_basic"
    assert filtered["provenance"]["surface_access"]["field_visibility"]["review_diff"] == "hidden_by_policy"
    assert filtered["provenance"]["surface_access"]["field_visibility"]["decision_governance"] == "hidden_by_policy"


def test_surface_filtered_result_package_hides_review_artifacts_for_operational_source_internal_surface():
    case = load_sample_case("09_fx_fifo_operational_source")
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal=case["goal"],
        safe_bundle=case["safe_bundle"],
        constraints=case["constraints"],
    )
    result = service.build_result(prepared)
    project = SimpleNamespace(
        id="proj_operational_surface",
        user_id=1,
        session_id="sess_operational_surface",
        run_id="run_operational_surface",
        project_name="FX FIFO",
        client_name="OO카드",
        template_key="default_modernization_v1",
        constraints_json=[],
        goal_text=case["goal"],
        status="completed",
    )
    pkg = build_result_package(
        project,
        {"status": "completed", "run_id": project.run_id},
        result,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )

    filtered = _surface_filtered_result_package(pkg, surface_mode="internal")

    assert pkg["family_classification"]["family"] == "operational_source"
    assert "review_diff" in (pkg.get("extensions") or {})
    assert "review_diff" not in (filtered.get("extensions") or {})
    assert filtered["structure_comparison"] == {"available": False, "items": []}
    assert filtered["provenance"]["surface_access"]["field_visibility"]["review_diff"] == "hidden_by_family"
    assert filtered["provenance"]["surface_access"]["review_diff_surface_policy"] == "hidden_by_family"


def test_project_result_ui_contains_review_diff_rendering_hooks():
    html = (MELLOW_LINK_ROOT / "static" / "project_result.html").read_text(encoding="utf-8")

    assert 'id="reviewDiffSection"' in html
    assert 'id="reviewDiffStickyBar"' in html
    assert 'id="reviewDiffDecisionSection"' in html
    assert 'id="reviewDiffWhySection"' in html
    assert 'id="reviewDiffEvidenceSection"' in html
    assert 'id="internalSurface"' in html
    assert 'id="externalSurface"' in html
    assert 'id="surfaceModeInternalBtn"' in html
    assert 'id="surfaceModeExternalBtn"' in html
    assert '<section id="reviewDiffDecisionSection"' in html
    assert '<details id="reviewDiffDecisionSection"' not in html
    assert "function renderReviewDiff(pkg)" in html
    assert "function renderExternalSurface(pkg, explanation)" in html
    assert 'id="structureComparisonSection"' in html
    assert 'id="structureComparisonBox"' in html
    assert 'id="customerIntentSection"' in html
    assert 'id="customerIntentBox"' in html
    assert 'id="externalComparisonSection"' in html
    assert 'id="externalComparisonBox"' in html
    assert 'id="externalCustomerIntentSection"' in html
    assert 'id="externalCustomerIntentBox"' in html
    assert "function resultDownloadUrl(format)" in html
    assert "function resultDownloadFallbackName(format)" in html
    assert "function surfaceModeConfig(mode)" in html
    assert "const accessPolicyMap =" in html
    assert "function resolveAccessProfile(mode)" in html
    assert "function resolveSurfaceAccessPolicy(mode)" in html
    assert "function applySurfaceAccessPolicy(mode)" in html
    assert "function resetReviewDiffSections()" in html
    assert "function renderReviewDiffStickyBar(pkg, reviewDiff)" in html
    assert "function renderStructureComparisonPanel(comparison)" in html
    assert "function renderExternalStructureComparisonPanel(comparison)" in html
    assert "function renderCustomerIntentBox(customerIntent)" in html
    assert "function highlightAnonymizedSegments(text)" in html
    assert "function renderExternalEvidenceHint(citations)" in html
    assert "function shortenComparisonSnippet(text, maxLines, maxChars)" in html
    assert "function inferStructureTheme(item)" in html
    assert "function buildEffectSummary(item)" in html
    assert "function renderStructureGuideCard(label, body, accentClass)" in html
    assert "return '<div class=\"overflow-hidden rounded-2xl border ' + panelTone + '\">' + rows + '</div>';" in html
    assert "왜 중요한가" in html
    assert "변경 전과 변경 후를 비교해 승인 근거를 바로 읽는 영역입니다." in html
    assert "escapeHtml(executive.title" not in html
    assert "escapeHtml(executive.state" not in html
    assert "displaySections(pkg)" in html
    assert "const hero = (((pkg || {}).display || {}).hero || {});" in html
    assert "function renderCodeDiffLines(text, tone)" in html
    assert "function renderComparisonSummaryList(items)" in html
    assert "function renderComparisonPoints(points)" in html
    assert 'class="rounded bg-white/10 px-1"' in html
    assert 'id="optionsDetails"' in html
    assert 'id="planDetails"' in html
    assert 'id="appendixDetails"' in html
    assert 'id="readingGuideDetails"' in html
    assert 'id="riskDetails"' in html
    assert 'id="reviewDiffDetails"' in html
    assert "data-collapsible-badge" in html
    assert "const shouldCollapse = function (section)" in html
    assert "function updateCollapsibleBadge(detailsElement)" in html
    assert "function bindCollapsibleDetails(root)" in html
    assert "surface_mode=" in html
    assert "설명용 마크다운" in html
    assert "검토용 마크다운" in html
    assert "설명용 내보내기" in html
    assert "검토용 내보내기" in html
    assert "참고 구조 비교와 판단 제어 추적을 제외한 설명 중심 산출물을 내보냅니다." in html
    assert "참고 구조 비교와 판단 제어 추적을 포함한 내부 검토용 산출물을 내보냅니다." in html
    assert "extensions || {}).review_diff" in html
    assert "/result/explanation?audience=manager&surface_mode=external" in html
    assert "currentCapabilities.can_view_review_diff" in html
    assert "currentAccessPolicy.surfaceVariant === 'external_presentation'" in html
    assert "comparisonBox.innerHTML = renderExternalStructureComparisonPanel(structureComparison);" in html
    assert "function usesComparisonFirstSurface(pkg)" in html
    assert "function usesSpecializedFamilySurface(pkg)" in html
    assert "function renderOperationalFollowupChecks(pkg, section)" in html
    assert "!currentCapabilities.can_view_review_diff || !reviewDiff || usesSpecializedFamilySurface(pkg)" in html
    assert "renderOperationalFollowupChecks(pkg, sections.design_options || {})" in html
    assert "!specializedFamily && structureComparison.available" in html
    assert "if (!analysisFirst && !comparisonFirst) {" in html
    assert "판단 결과" in html
    assert "왜 이렇게 판단했는가" in html
    assert "근거 상세" in html
    assert "최종 판단" in html
    assert "차단된 판단" in html
    assert "신뢰도" in html
    assert "구조 비교" in html
    assert "변경 전, 변경 후, 근거 순으로 비교해 승인 범위를 좁히는 본문 영역입니다." in html
    assert "변경 전에 어떤 결합을 풀어야 하는지 보여주는 익명화 패턴입니다." in html
    assert "(실제 구조를 안전하게 치환한 형태입니다)" in html
    assert "변경 후 어떤 경계를 고정할지 보여주는 권장 예시입니다." in html
    assert "(새 helper 이름만 예시용으로 생성될 수 있습니다)" in html
    assert "실제 코드 근거 " in html
    assert "변경 전" in html
    assert "변경 후" in html
    assert "근거" in html
    assert "미조치 시 영향" in html
    assert "비교 포인트" in html
    assert "우선순위 판단" in html
    assert "차이 설명" in html
    assert "코드 비교 보기" not in html
    assert "Code Diff" not in html
    assert "익명화된 구조 비교 보기" not in html
    assert "synthetic_signal_detected" in html
    assert "whySection.open = true" in html
    assert "evidenceSection.open = false" in html
