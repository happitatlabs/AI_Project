from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.planning_synthesizer import PlanningSynthesizer

from .refactoring_support_test_utils import build_safe_bundle


def test_planning_synthesizer_matches_service_public_contract():
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
    core_rules = service.analyze_assets(prepared)
    grounded_rules = service.build_grounded_business_rules(prepared, core_rules)
    retained_contracts = service.build_retained_contracts(prepared, grounded_rules)
    applied_templates = service.build_applied_templates(prepared, grounded_rules, retained_contracts)
    decisions = service._compat_decision_artifacts(prepared, applied_templates)
    synth = PlanningSynthesizer(service)

    priority_from_wrapper = service.build_priority_split_items(prepared, grounded_rules, retained_contracts, applied_templates)
    priority_from_synth = synth.build_priority_split_items(prepared, grounded_rules, retained_contracts, decisions)
    assert [item.model_dump() for item in priority_from_synth] == [item.model_dump() for item in priority_from_wrapper]

    options_from_wrapper = service.build_design_options(prepared, grounded_rules, retained_contracts, applied_templates)
    options_from_synth = synth.build_design_options(prepared, grounded_rules, retained_contracts, decisions)
    assert [item.model_dump() for item in options_from_synth] == [item.model_dump() for item in options_from_wrapper]

    verification_from_wrapper = service.build_verification_checkpoints(prepared, grounded_rules, retained_contracts, applied_templates)
    verification_from_synth = synth.build_verification_checkpoints(prepared, grounded_rules, retained_contracts, decisions)
    assert [item.model_dump() for item in verification_from_synth] == [item.model_dump() for item in verification_from_wrapper]


def test_improvement_planner_does_not_call_legacy_top_planning_helpers():
    class FailingPlanningService(RebuildAssistantService):
        def build_priority_split_items(self, *args, **kwargs):
            raise AssertionError("legacy build_priority_split_items should not be called")

        def build_design_options(self, *args, **kwargs):
            raise AssertionError("legacy build_design_options should not be called")

        def pick_recommended_option(self, *args, **kwargs):
            raise AssertionError("legacy pick_recommended_option should not be called")

        def build_verification_checkpoints(self, *args, **kwargs):
            raise AssertionError("legacy build_verification_checkpoints should not be called")

        def build_execution_plan(self, *args, **kwargs):
            raise AssertionError("legacy build_execution_plan should not be called")

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
    service = FailingPlanningService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order creation flow", safe_bundle=bundle, constraints=["keep db contract"])

    from mellow_link.services.refactoring_support_engine.decision_engine import DecisionEngine
    from mellow_link.services.refactoring_support_engine.diagnosis_engine import DiagnosisEngine
    from mellow_link.services.refactoring_support_engine.improvement_planner import ImprovementPlanner
    from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
    from mellow_link.services.refactoring_support_engine.structure_analyzer import StructureAnalyzer

    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    decisions = DecisionEngine().run(prepared, structure, diagnosis, service)
    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, decisions, service)

    assert improvement.execution_plan
    assert improvement.design_options


def test_improvement_planner_runs_without_legacy_service():
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

    from mellow_link.services.refactoring_support_engine.decision_engine import DecisionEngine
    from mellow_link.services.refactoring_support_engine.diagnosis_engine import DiagnosisEngine
    from mellow_link.services.refactoring_support_engine.improvement_planner import ImprovementPlanner
    from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
    from mellow_link.services.refactoring_support_engine.structure_analyzer import StructureAnalyzer

    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    decisions = DecisionEngine().run(prepared, structure, diagnosis, None)
    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, decisions, None)

    assert improvement.execution_plan
    assert improvement.design_options
