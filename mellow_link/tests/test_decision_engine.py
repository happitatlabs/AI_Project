from mellow_link.modules.rebuild_assistant import judgment_templates as legacy_judgment_templates
from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine import decision_catalog
from mellow_link.services.refactoring_support_engine.decision_engine import DecisionEngine
from mellow_link.services.refactoring_support_engine.diagnosis_engine import DiagnosisEngine
from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
from mellow_link.services.refactoring_support_engine.structure_analyzer import StructureAnalyzer

from .refactoring_support_test_utils import build_safe_bundle


def test_judgment_templates_is_compatibility_reexport_of_engine_catalog():
    assert legacy_judgment_templates.JUDGMENT_TEMPLATE_REGISTRY == decision_catalog.JUDGMENT_TEMPLATE_REGISTRY
    assert legacy_judgment_templates.get_judgment_template_specs() == decision_catalog.get_judgment_template_specs()


def test_decision_engine_marks_boundary_mismatch_as_redesign():
    bundle = build_safe_bundle(
        [
            {
                "name": "order_repository.py",
                "content": """
class OrderRepository:
    def approve_order(self, order):
        if order.status == "READY":
            return "approved"
                """,
            },
            {"name": "order_page.html", "content": "<button onclick=\"approveOrder()\">approve</button>"},
        ]
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order approval flow", safe_bundle=bundle, constraints=[])
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    decisions = DecisionEngine().run(prepared, structure, diagnosis, service)

    assert any(item.decision_type == "redesign" for item in decisions.decision_summary.decisions)
    assert all(item.score_breakdown["final_score"] == item.priority_score for item in decisions.decision_summary.decisions)
    assert decisions.primary_judgment


def test_decision_engine_prioritizes_boundary_and_ui_coupling_over_duplicate_logic():
    bundle = build_safe_bundle(
        [
            {
                "name": "order_page.html",
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
        ]
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order approval flow", safe_bundle=bundle, constraints=[])
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    decisions = DecisionEngine().run(prepared, structure, diagnosis, service)

    by_issue_id = {issue.issue_id: issue.detector_id for issue in diagnosis.diagnosis_report.issues}
    ui_scores = [
        item.priority_score
        for item in decisions.decision_summary.decisions
        if any(by_issue_id.get(issue_id) == "ui_data_access_coupling" for issue_id in item.issue_ids)
    ]
    duplicate_scores = [
        item.priority_score
        for item in decisions.decision_summary.decisions
        if any(by_issue_id.get(issue_id) == "duplicate_logic_candidate" for issue_id in item.issue_ids)
    ]

    assert ui_scores
    assert duplicate_scores
    assert max(ui_scores) > max(duplicate_scores)
    assert any("검토" in item.rationale or "적절" in item.rationale for item in decisions.decision_summary.decisions)
    assert all(
        set(item.score_breakdown.keys()) == {
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
        for item in decisions.decision_summary.decisions
    )
