from __future__ import annotations

import pytest

from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.decision_engine import DecisionEngine
from mellow_link.services.refactoring_support_engine.diagnosis_engine import DiagnosisEngine
from mellow_link.services.refactoring_support_engine.improvement_planner import ImprovementPlanner
from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
from mellow_link.services.refactoring_support_engine.result_packager import ResultPackager
from mellow_link.services.refactoring_support_engine.structure_analyzer import StructureAnalyzer

from .refactoring_support_golden_samples import GOLDEN_SAMPLE_EXPECTATIONS
from .refactoring_support_test_utils import load_expansion_sample_case, load_sample_case


RUNNABLE_SAMPLE_CASES = (
    [("golden", expectation.sample_name, expectation.fallback_goal) for expectation in GOLDEN_SAMPLE_EXPECTATIONS]
    + [
        ("expansion", "01_crud_simple", ""),
        ("expansion", "02_access_control_workflow", ""),
        ("expansion", "03_state_transition_complex", ""),
        ("expansion", "04_db_heavy_query_filter", ""),
        ("expansion", "05_legacy_tangled_mixed", ""),
        ("expansion", "07_order_closure_false_positive_minimal", ""),
    ]
)


def _package_sample(sample_type: str, sample_name: str, fallback_goal: str):
    case = (
        load_sample_case(sample_name, fallback_goal=fallback_goal)
        if sample_type == "golden"
        else load_expansion_sample_case(sample_name)
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal=case["goal"],
        safe_bundle=case["safe_bundle"],
        constraints=case["constraints"],
    )
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    decisions = DecisionEngine().run(prepared, structure, diagnosis, service)
    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, decisions, service)
    return ResultPackager().package(prepared, structure, diagnosis, decisions, improvement, service)


@pytest.mark.parametrize(("sample_type", "sample_name", "fallback_goal"), RUNNABLE_SAMPLE_CASES)
def test_runnable_sample_cases_smoke(sample_type: str, sample_name: str, fallback_goal: str):
    result = _package_sample(sample_type, sample_name, fallback_goal)

    assert result.primary_judgment
    assert result.structural_judgment
    assert isinstance(result.decision_summary, dict)
    assert isinstance(result.improvement_plan_bundle, dict)
    assert isinstance(result.extensions, dict)
    assert "review_diff" in result.extensions
