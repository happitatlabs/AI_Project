from __future__ import annotations

import pytest

from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.schemas import stable_hash

from .refactoring_support_test_utils import load_expected_assertions, load_expansion_sample_case


PROMOTED_EXPANSION_SAMPLES = (
    "01_crud_simple",
    "02_access_control_workflow",
    "04_db_heavy_query_filter",
    "05_legacy_tangled_mixed",
)


@pytest.mark.parametrize("sample_name", PROMOTED_EXPANSION_SAMPLES)
def test_refactoring_support_promoted_expansion_samples(sample_name: str):
    expected = load_expected_assertions(sample_name)["assertions"]
    deterministic_core = expected["deterministic_core"]
    planning_expectations = expected["planning_expectations"]
    stable_hashes = expected["stable_hashes"]
    issue_expectations = expected["issue_expectations"]

    service = RebuildAssistantService()
    case = load_expansion_sample_case(sample_name)
    result = service.build_result(
        service.prepare_safe_bundle_input(
            goal=case["goal"],
            safe_bundle=case["safe_bundle"],
            constraints=case["constraints"],
        )
    )

    decisions = result.decision_summary.get("decisions", [])
    top_decision = decisions[0] if decisions else None
    execution_stages = result.improvement_plan_bundle.get("execution_stages", [])
    feature_slices = result.structure_snapshot.get("feature_slices", [])
    first_entry_point = feature_slices[0]["entry_points"][0] if feature_slices and feature_slices[0]["entry_points"] else None
    detector_ids = [issue["detector_id"] for issue in result.diagnosis_report.get("issues", [])]
    narrative_axis = result.extensions.get("narrative", {}).get("axis")

    assert result.primary_judgment == deterministic_core["primary_judgment"]
    assert result.structural_judgment == deterministic_core["structural_judgment"]
    assert narrative_axis == deterministic_core["selected_narrative_judgment"]
    assert result.report_purpose == deterministic_core["report_purpose"]
    assert result.decision_summary.get("recommended_strategy") == deterministic_core["recommended_strategy"]
    assert first_entry_point == deterministic_core["first_entry_point"]
    assert len(feature_slices) == deterministic_core["feature_slice_count"]
    assert len(decisions) == deterministic_core["decision_count"]

    if deterministic_core["top_decision_type"] is None:
        assert top_decision is None
    else:
        assert top_decision is not None
        assert top_decision["decision_type"] == deterministic_core["top_decision_type"]
        assert top_decision["priority_score"] == deterministic_core["top_priority_score"]
        assert top_decision["score_breakdown"]["final_score"] == deterministic_core["top_priority_score"]

    assert stable_hash([item.model_dump() for item in result.execution_plan]) == stable_hashes["execution_plan"]
    assert stable_hash([item.model_dump() for item in result.design_options]) == stable_hashes["design_options"]
    assert stable_hash(result.recommended_option.model_dump() if result.recommended_option is not None else None) == stable_hashes["recommended_option"]

    for detector_id in issue_expectations["must_include_detectors"]:
        assert detector_id in detector_ids
    for detector_id in issue_expectations["must_not_include_detectors"]:
        assert detector_id not in detector_ids

    assert result.recommended_option is not None
    assert result.recommended_option.name == planning_expectations["recommended_option_title"]
    assert len(execution_stages) == planning_expectations["execution_stage_count"]
    assert result.execution_plan[0].week_label == planning_expectations["first_execution_stage_title"]
    assert result.execution_plan[-1].week_label == planning_expectations["last_execution_stage_title"]
    if planning_expectations["must_link_decision_ids"]:
        assert all(stage["decision_ids"] for stage in execution_stages)
