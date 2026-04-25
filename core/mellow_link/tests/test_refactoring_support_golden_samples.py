from __future__ import annotations

import pytest

from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.schemas import stable_hash

from .refactoring_support_golden_samples import GOLDEN_SAMPLE_EXPECTATIONS
from .refactoring_support_test_utils import load_sample_case


@pytest.mark.parametrize("expectation", GOLDEN_SAMPLE_EXPECTATIONS, ids=[item.sample_name for item in GOLDEN_SAMPLE_EXPECTATIONS])
def test_refactoring_support_golden_samples(expectation):
    service = RebuildAssistantService()
    case = load_sample_case(expectation.sample_name, fallback_goal=expectation.fallback_goal)
    result = service.build_result(
        service.prepare_safe_bundle_input(
            goal=case["goal"],
            safe_bundle=case["safe_bundle"],
            constraints=case["constraints"],
        )
    )

    decisions = result.decision_summary.get("decisions", [])
    top_decision = decisions[0] if decisions else None
    feature_slices = result.structure_snapshot.get("feature_slices", [])
    first_entry_point = feature_slices[0]["entry_points"][0] if feature_slices and feature_slices[0]["entry_points"] else ""

    assert result.primary_judgment == expectation.expected_primary_judgment
    assert result.report_purpose == expectation.expected_report_purpose
    assert result.decision_summary.get("recommended_strategy") == expectation.expected_recommended_strategy
    assert first_entry_point == expectation.expected_first_entry_point
    assert len(decisions) == expectation.expected_decision_count
    execution_plan_dump = [item.model_dump() for item in result.execution_plan]
    design_options_dump = [item.model_dump() for item in result.design_options]
    recommended_option_dump = result.recommended_option.model_dump() if result.recommended_option is not None else None
    assert stable_hash(execution_plan_dump) == expectation.expected_execution_plan_hash
    assert stable_hash(design_options_dump) == expectation.expected_design_options_hash
    assert stable_hash(recommended_option_dump) == expectation.expected_recommended_option_hash

    if expectation.expected_top_decision_type is None:
        assert top_decision is None
    else:
        assert top_decision is not None
        assert top_decision["decision_type"] == expectation.expected_top_decision_type
        assert top_decision["priority_score"] == expectation.expected_top_priority_score
        assert top_decision["score_breakdown"]["final_score"] == expectation.expected_top_priority_score
        assert top_decision["explainability"]["decision_rule"] == expectation.expected_top_decision_rule
        assert top_decision["explainability"]["score_formula"]
        assert "final_score=" in top_decision["explainability"]["score_summary"]

    if expectation.expected_accounting_can_calculate is not None:
        assert result.extensions["accounting"]["calculation_status"]["can_calculate"] is expectation.expected_accounting_can_calculate
    if expectation.expected_narrative_axis is not None:
        assert result.narrative_axis == expectation.expected_narrative_axis
    if expectation.expected_analysis_summary_prefix is not None:
        assert result.analysis_summary
        assert result.analysis_summary[0].startswith(expectation.expected_analysis_summary_prefix)
    if expectation.expected_executive_summary_prefix is not None:
        assert result.executive_summary_v2
        assert result.executive_summary_v2[0].startswith(expectation.expected_executive_summary_prefix)
    top_narrative = " ".join(
        [
            result.report_purpose,
            result.one_line_conclusion,
            result.primary_judgment_reason,
            *list(result.analysis_summary[:2]),
            *list(result.executive_summary_v2[:2]),
        ]
    )
    front_narrative = " ".join(
        [
            result.report_purpose,
            result.one_line_conclusion,
            *list(result.analysis_summary[:1]),
            *list(result.executive_summary_v2[:1]),
        ]
    )
    for term in expectation.expected_required_terms:
        assert term in top_narrative
    for term in expectation.expected_forbidden_narrative_terms:
        assert term not in front_narrative
