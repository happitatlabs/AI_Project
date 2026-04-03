from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.decision_engine import DecisionEngine
from mellow_link.services.refactoring_support_engine.diagnosis_engine import DiagnosisEngine
from mellow_link.services.refactoring_support_engine.improvement_planner import ImprovementPlanner
from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
from mellow_link.services.refactoring_support_engine.structure_analyzer import StructureAnalyzer

from .refactoring_support_test_utils import build_safe_bundle


def test_improvement_planner_links_execution_stages_to_decisions():
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
            {"name": "query.sql", "content": "SELECT * FROM orders WHERE status = 'READY'"},
        ]
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order creation flow", safe_bundle=bundle, constraints=["keep db contract"])
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    decisions = DecisionEngine().run(prepared, structure, diagnosis, service)
    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, decisions, service)

    assert improvement.improvement_plan_bundle.execution_stages
    assert all(stage.decision_ids for stage in improvement.improvement_plan_bundle.execution_stages)
    assert improvement.improvement_plan_bundle.design_options
