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

from .refactoring_support_test_utils import build_safe_bundle, load_expansion_sample_case

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
    assert "before" not in review_diff["code_diff"]["snippets"][0]
    assert "after" not in review_diff["code_diff"]["snippets"][0]
    assert review_diff["markdown"].index("## Why this decision?") < review_diff["markdown"].index("## 현재 구조 vs 권장 구조 비교") < review_diff["markdown"].index("## Structural Difference")
    assert "이 비교는 실제 패치가 아니라, 현재 구조와 권장 패턴의 차이를 검토하기 위한 근거 예시입니다." in review_diff["markdown"]
    assert "#### observed" in review_diff["markdown"]
    assert "#### expected_pattern" in review_diff["markdown"]


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
        evidence_ids=["EVID_TEST"],
        evidence_map={"EVID_TEST": evidence},
        asset_text_map=asset_text_map,
    )

    assert snippet is not None
    assert snippet["file"] == "claim_approval_service.py"
    assert snippet["observed"]
    assert snippet["expected_pattern"]


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

    assert "## Decision Result" in markdown
    assert "## Why this decision?" in markdown
    assert "## 현재 구조 vs 권장 구조 비교" in markdown
    assert "## Structural Difference" in markdown
    assert "synthetic_signal_detected" in markdown


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

    assert "review_diff" in (pkg.get("extensions") or {})
    assert "review_diff" not in (filtered.get("extensions") or {})
    assert "decision_governance" not in (filtered.get("extensions") or {})
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
    assert 'id="reviewDiffPatternSection"' in html
    assert 'id="internalSurface"' in html
    assert 'id="externalSurface"' in html
    assert 'id="surfaceModeInternalBtn"' in html
    assert 'id="surfaceModeExternalBtn"' in html
    assert '<section id="reviewDiffDecisionSection"' in html
    assert '<details id="reviewDiffDecisionSection"' not in html
    assert "function renderReviewDiff(pkg)" in html
    assert "function renderExternalSurface(pkg, explanation)" in html
    assert 'id="codeDiffSection"' in html
    assert 'id="showCodeDiffBtn"' in html
    assert 'id="codeDiffPanel"' in html
    assert "function resultDownloadUrl(format)" in html
    assert "function resultDownloadFallbackName(format)" in html
    assert "function surfaceModeConfig(mode)" in html
    assert "const accessPolicyMap =" in html
    assert "function resolveAccessProfile(mode)" in html
    assert "function resolveSurfaceAccessPolicy(mode)" in html
    assert "function applySurfaceAccessPolicy(mode)" in html
    assert "function resetReviewDiffSections()" in html
    assert "function renderReviewDiffStickyBar(pkg, reviewDiff)" in html
    assert "function renderCodeDiffPanel(reviewDiff)" in html
    assert "function renderCodeDiffLines(text, tone)" in html
    assert "surface_mode=" in html
    assert "설명용 Markdown" in html
    assert "검토용 Markdown" in html
    assert "설명용 내보내기" in html
    assert "검토용 내보내기" in html
    assert "Review Diff와 governance trace를 제외한 설명 중심 산출물을 내보냅니다." in html
    assert "Review Diff와 governance trace를 포함한 내부 검토용 산출물을 내보냅니다." in html
    assert "extensions || {}).review_diff" in html
    assert "/result/explanation?audience=manager&surface_mode=external" in html
    assert "currentCapabilities.can_view_review_diff" in html
    assert "currentCapabilities.can_view_code_diff" in html
    assert "currentAccessPolicy.surfaceVariant === 'external_presentation'" in html
    assert "Decision Result" in html
    assert "Why this decision?" in html
    assert "Evidence Detail" in html
    assert "Structural Difference" in html
    assert "Primary" in html
    assert "Blocked" in html
    assert "Confidence" in html
    assert "현재 구조 vs 권장 구조 비교" in html
    assert "현재 구조 vs 권장 구조 보기" in html
    assert "이 비교는 실제 패치가 아니라, 현재 구조와 권장 패턴의 차이를 검토하기 위한 근거 예시입니다." in html
    assert "현재 시스템에서 실제로 사용되고 있는 코드 일부입니다." in html
    assert "(판단의 근거가 되는 실제 구조입니다)" in html
    assert "권장되는 구조 패턴 예시입니다." in html
    assert "(실제 코드가 아니라, 개선 방향을 설명하기 위한 일반화된 형태입니다)" in html
    assert "코드 비교 보기" not in html
    assert "Code Diff" not in html
    assert "synthetic_signal_detected" in html
    assert "whySection.open = true" in html
    assert "evidenceSection.open = false" in html
    assert "patternSection.open = false" in html
