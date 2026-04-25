from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.decision_engine import DecisionEngine
from mellow_link.services.refactoring_support_engine.policies import get_detector_policy, load_engine_policy_bundle
from mellow_link.services.refactoring_support_engine.schemas import StructuralIssue

from .refactoring_support_test_utils import build_safe_bundle


def test_doc_contract_authoritative_payload_and_explainability_shape():
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
            {"name": "order_page.html", "content": '<button onclick="submitOrder()">submit</button>'},
        ]
    )
    service = RebuildAssistantService()
    result = service.build_result(service.prepare_safe_bundle_input(goal="modernize order creation flow", safe_bundle=bundle, constraints=[]))

    assert set(result.structure_snapshot.keys()) >= {"feature_slices", "components", "dependencies", "hotspots", "layer_map"}
    assert set(result.diagnosis_report.keys()) >= {"issues", "coverage_summary", "detector_stats"}
    assert set(result.decision_summary.keys()) >= {"decisions", "recommended_strategy", "priority_queue"}
    assert set(result.improvement_plan_bundle.keys()) >= {"design_options", "recommended_option", "execution_stages", "risk_checkpoints"}
    assert set(result.family_classification.model_dump().keys()) == {
        "family",
        "confidence",
        "decision_basis",
        "secondary_signals",
        "display_strategy",
        "internal_strategy",
    }
    assert result.template_judgment == result.primary_judgment
    assert result.structural_judgment in {"refactor", "redesign", "migration_consideration", "observation_only"}
    assert result.narrative_axis == result.extensions["narrative"]["axis"]
    assert result.feature_signal_mode
    if result.decision_summary["decisions"]:
        top_decision = result.decision_summary["decisions"][0]
        assert set(top_decision["score_breakdown"].keys()) == {
            "severity_component",
            "blast_radius_component",
            "effort_component",
            "confidence_bonus",
            "detector_weight",
            "hotspot_bonus",
            "multi_slice_bonus",
            "redesign_bonus",
            "final_score",
        }
        assert set(top_decision["explainability"].keys()) == {
            "decision_rule",
            "score_formula",
            "score_summary",
            "evidence_count",
            "affected_slice_count",
        }
    assert result.extensions["narrative"]["source"] == "deterministic_fallback"
    assert result.extensions["narrative"]["axis"]
    governance = result.extensions["decision_governance"]
    assert governance["intent_usage_policy"]["engine_definition"] == "레거시 시스템을 해석하여 구조와 의존성을 진단하고, 신규 환경으로 이전 가능한 구조 초안과 의사결정 근거를 생성하는 엔진"
    assert governance["confidence_policy"]["evidence_only"] is True
    assert set(governance["family_classifier"].keys()) == {
        "family",
        "confidence",
        "decision_basis",
        "secondary_signals",
        "display_strategy",
        "internal_strategy",
    }
    assert governance["ordered_sections"] == ["recommended_strategy", "rationale", "evidence", "risk", "next_step"]
    assert list(governance["document_outline"].keys()) == ["recommended_strategy", "rationale", "evidence", "risk", "next_step"]


def test_doc_contract_decision_branching_uses_detector_id_not_category():
    engine = DecisionEngine()
    prepared = SimpleNamespace(goal="", constraints=[])
    redesign_issue = StructuralIssue(
        issue_id="ISSUE-REDESIGN",
        detector_id="boundary_mismatch",
        category="duplication",
        severity=4,
        blast_radius=3,
        effort=5,
        summary="Boundary mismatch sample",
        affected_component_ids=["cmp-a"],
        affected_slice_ids=["slice-a"],
        evidence_ids=["ev-1"],
        confidence=0.8,
    )
    refactor_issue = StructuralIssue(
        issue_id="ISSUE-REFACTOR",
        detector_id="duplicate_logic_candidate",
        category="boundary",
        severity=4,
        blast_radius=3,
        effort=2,
        summary="Duplicate logic sample",
        affected_component_ids=["cmp-b"],
        affected_slice_ids=["slice-b"],
        evidence_ids=["ev-2"],
        confidence=0.8,
    )

    assert engine._decision_type_for_issue(prepared, redesign_issue) == "redesign"
    assert engine._decision_type_for_issue(prepared, refactor_issue) == "refactor"


def test_doc_contract_score_breakdown_matches_policy_formula_and_explainability():
    policy_bundle = load_engine_policy_bundle()
    scoring_policy = policy_bundle.scoring_policy
    engine = DecisionEngine(policy_bundle=policy_bundle)
    issue = StructuralIssue(
        issue_id="ISSUE-SCORE",
        detector_id="boundary_mismatch",
        category="boundary",
        severity=4,
        blast_radius=3,
        effort=5,
        summary="Boundary mismatch sample",
        affected_component_ids=["cmp-a"],
        affected_slice_ids=["slice-a", "slice-b"],
        evidence_ids=["ev-1", "ev-2"],
        confidence=0.9,
    )
    detector_policy = get_detector_policy(issue.detector_id, policy_bundle)
    breakdown = engine._score_breakdown(issue, "redesign", {"cmp-a": 2}, scoring_policy)
    explainability = engine._build_explainability(issue, "redesign", breakdown, scoring_policy)

    expected_final_score = max(
        1,
        issue.severity * scoring_policy.severity_multiplier
        + issue.blast_radius * scoring_policy.blast_radius_multiplier
        - issue.effort * scoring_policy.effort_multiplier
        + scoring_policy.confidence_bonus_value
        + detector_policy.detector_weight
        + scoring_policy.hotspot_bonus
        + scoring_policy.multi_slice_bonus
        + scoring_policy.redesign_bonus,
    )

    assert breakdown["final_score"] == expected_final_score
    assert explainability.score_formula == "severity*2 + blast_radius*1 - effort*1 + confidence_bonus + detector_weight + hotspot_bonus + multi_slice_bonus + redesign_bonus"
    assert "final_score=12" in explainability.score_summary
    assert explainability.evidence_count == 2
    assert explainability.affected_slice_count == 2


def test_doc_contract_slice_rules_prefer_entry_points_and_split_distinct_handlers():
    bundle = build_safe_bundle(
        [
            {
                "name": "order_controller.py",
                "content": """
@router.post("/orders")
def create_order():
    return save_order()

@router.post("/orders/{order_id}/approve")
def approve_order(order_id):
    return approve(order_id)
                """,
            },
            {"name": "order_service.py", "content": "def save_order(): pass\ndef approve(order_id): pass"},
        ]
    )
    service = RebuildAssistantService()
    result = service.build_result(service.prepare_safe_bundle_input(goal="modernize order flow", safe_bundle=bundle, constraints=[]))
    entry_points = sorted(item["entry_points"][0] for item in result.structure_snapshot["feature_slices"] if item["entry_points"])

    assert "api:POST /orders" in entry_points
    assert "api:POST /orders/{order_id}/approve" in entry_points
    assert len(entry_points) >= 2


def test_doc_contract_governance_doc_locks_engine_definition_and_grounding_policy():
    path = Path(r"C:\Users\Hyein\ClaudeAI\AI_Project\core\mellow_link\docs\REFACTORING_SUPPORT_ENGINE_DECISION_GOVERNANCE.md")
    text = path.read_text(encoding="utf-8")

    assert "레거시 시스템을 해석하여 구조와 의존성을 진단하고, 신규 환경으로 이전 가능한 구조 초안과 의사결정 근거를 생성하는 엔진" in text
    assert "Intent Usage Policy" in text
    assert "Insufficient Grounding Policy" in text
    assert "Confidence Policy" in text
    assert "recommended_strategy -> rationale -> evidence -> risk -> next_step" in text
    assert "executive_summary_v2" in text
    assert "문제" in text and "영향" in text and "조치" in text and "다음 단계" in text
    assert "grounded" in text and "limited" in text and "insufficient" in text
