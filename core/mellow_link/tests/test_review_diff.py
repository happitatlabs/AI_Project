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


def test_review_diff_preserves_legitimate_migration_without_block_reason():
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

    assert review_diff["decision_diff"]["synthetic_signal_detected"] is False
    assert review_diff["decision_diff"]["blocked_decisions"] == []
    assert "migration_consideration" in decision_types
    assert "goal wording only (contamination)" not in markdown
    assert "✖ blocked: migration_consideration" not in markdown
    assert "✔ allowed: migration_consideration" in markdown


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
    assert "\n" in order_lookup["observed"]
    assert "ops.order@example.com" not in order_lookup["observed"]
    assert "[EMAIL]" in order_lookup["observed"]


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

    markdown = _result_package_markdown(pkg, surface_mode="internal")

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
    assert filtered["provenance"]["surface_access"]["access_profile"] == "external_basic"
    assert filtered["provenance"]["surface_access"]["field_visibility"]["review_diff"] == "hidden_by_policy"
    assert filtered["provenance"]["surface_access"]["field_visibility"]["decision_governance"] == "hidden_by_policy"


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
    assert "이 카드에서 먼저 볼 점" in html
    assert "이 구조로 바꾸면" in html
    assert "현재 구조를 그대로 둘 때의 부담과, 권장 구조로 나눴을 때의 효과를 먼저 읽는 영역입니다." in html
    assert "escapeHtml(executive.title" not in html
    assert "escapeHtml(executive.state" not in html
    assert "function renderCodeDiffLines(text, tone)" in html
    assert "function renderComparisonSummaryList(items)" in html
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
    assert "판단 결과" in html
    assert "왜 이렇게 판단했는가" in html
    assert "근거 상세" in html
    assert "최종 판단" in html
    assert "차단된 판단" in html
    assert "신뢰도" in html
    assert "구조 비교" in html
    assert "현재 구조는 익명화된 실제 패턴이고, 권장 구조는 설명용 일반화 패턴입니다." in html
    assert "이 섹션은 참고 부록이 아니라 판단 본문입니다." in html
    assert "현재 시스템에서 관찰된 익명화 패턴입니다." in html
    assert "(실제 구조를 안전하게 치환한 형태입니다)" in html
    assert "권장되는 구조 패턴 예시입니다." in html
    assert "(실제 코드가 아니라, 개선 방향을 설명하기 위한 일반화된 형태입니다)" in html
    assert "실제 코드 근거 " in html
    assert "이렇게 달라집니다" in html
    assert "차이 설명" in html
    assert "코드 비교 보기" not in html
    assert "Code Diff" not in html
    assert "익명화된 구조 비교 보기" not in html
    assert "synthetic_signal_detected" in html
    assert "whySection.open = true" in html
    assert "evidenceSection.open = false" in html
