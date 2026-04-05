from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.diagnosis_engine import DiagnosisEngine
from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
from mellow_link.services.refactoring_support_engine.policies import (
    DetectorPolicyEntry,
    EnginePolicyBundle,
    ScoringPolicy,
)
from mellow_link.services.refactoring_support_engine.structure_analyzer import StructureAnalyzer

from .refactoring_support_test_utils import build_safe_bundle


def test_detector_policy_controls_severity_and_effort():
    bundle = build_safe_bundle(
        [
            {
                "name": "order_service.py",
                "content": """
class OrderService:
    def submit(self, order, repo):
        if not order.amount:
            raise ValueError("required")
        repo.save(order)
                """,
            },
        ]
    )
    policy_bundle = EnginePolicyBundle(
        detector_policies={
            "mixed_responsibility": DetectorPolicyEntry(
                detector_id="mixed_responsibility",
                category="custom_structure",
                enabled=True,
                base_severity=1,
                default_effort=5,
                allow_cross_layer_bonus=False,
                allow_write_path_bonus=False,
            )
        },
        scoring_policy=ScoringPolicy(),
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order submit flow", safe_bundle=bundle, constraints=[])
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine(policy_bundle=policy_bundle).run(prepared, structure, service)

    issue = next(item for item in diagnosis.diagnosis_report.issues if item.detector_id == "mixed_responsibility")
    assert issue.category == "custom_structure"
    assert issue.severity == 1
    assert issue.effort == 5


def test_detector_policy_disables_detector_execution():
    bundle = build_safe_bundle(
        [
            {
                "name": "order_page.html",
                "content": """
<% String sql = "SELECT * FROM orders WHERE status = 'READY'"; %>
<button onclick="submitOrder()">submit</button>
                """,
            }
        ]
    )
    policy_bundle = EnginePolicyBundle(
        detector_policies={
            "ui_data_access_coupling": DetectorPolicyEntry(
                detector_id="ui_data_access_coupling",
                category="boundary",
                enabled=False,
                base_severity=4,
                default_effort=3,
            )
        },
        scoring_policy=ScoringPolicy(),
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order screen", safe_bundle=bundle, constraints=[])
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine(policy_bundle=policy_bundle).run(prepared, structure, service)

    assert all(item.detector_id != "ui_data_access_coupling" for item in diagnosis.diagnosis_report.issues)


def test_detector_policy_falls_back_for_unknown_detector():
    engine = DiagnosisEngine(
        policy_bundle=EnginePolicyBundle(
            detector_policies={},
            scoring_policy=ScoringPolicy(),
        )
    )
    issue = engine._build_issue(
        detector_id="unknown_detector",
        summary="Unknown detector sample",
        component_ids=["cmp-a"],
        slice_ids=["slice-a"],
        evidence_ids=["evid-a"],
        layer_map={"cmp-a": "service"},
        text="return handler()",
    )

    assert issue.category == "unknown"
    assert issue.severity == 3
    assert issue.effort == 3
