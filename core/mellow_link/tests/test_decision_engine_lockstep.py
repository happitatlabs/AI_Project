from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.judgment_synthesizer import JudgmentSynthesizer

from .refactoring_support_test_utils import build_safe_bundle


def test_judgment_synthesizer_matches_service_public_contract():
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
    prepared = service.prepare_safe_bundle_input(goal="modernize order creation flow", safe_bundle=bundle, constraints=[])
    core_rules = service.analyze_assets(prepared)
    grounded_rules = service.build_grounded_business_rules(prepared, core_rules)
    retained_contracts = service.build_retained_contracts(prepared, grounded_rules)
    synth = JudgmentSynthesizer(service)

    applied_from_wrapper = service.build_applied_templates(prepared, grounded_rules, retained_contracts)
    applied_from_synth = synth.build_applied_templates(prepared, grounded_rules, retained_contracts)
    assert [item.model_dump() for item in applied_from_synth] == [item.model_dump() for item in applied_from_wrapper]

    candidates_from_wrapper = service.collect_pattern_candidates(prepared, applied_from_wrapper)
    candidates_from_synth = synth.collect_pattern_candidates(prepared, applied_from_synth)
    assert [item.model_dump() for item in candidates_from_synth] == [item.model_dump() for item in candidates_from_wrapper]

    judgment_from_wrapper = service.select_primary_judgment(prepared, candidates_from_wrapper)
    judgment_from_synth = synth.select_primary_judgment(prepared, candidates_from_synth)
    assert judgment_from_synth[0] == judgment_from_wrapper[0]
    assert judgment_from_synth[1] == judgment_from_wrapper[1]
    assert [item.model_dump() for item in judgment_from_synth[2]] == [item.model_dump() for item in judgment_from_wrapper[2]]


def test_decision_engine_does_not_call_legacy_top_judgment_helpers():
    class FailingJudgmentService(RebuildAssistantService):
        def build_applied_templates(self, *args, **kwargs):
            raise AssertionError("legacy build_applied_templates should not be called")

        def collect_pattern_candidates(self, *args, **kwargs):
            raise AssertionError("legacy collect_pattern_candidates should not be called")

        def select_primary_judgment(self, *args, **kwargs):
            raise AssertionError("legacy select_primary_judgment should not be called")

        def build_decision_items(self, *args, **kwargs):
            raise AssertionError("legacy build_decision_items should not be called")

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
    service = FailingJudgmentService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order approval flow", safe_bundle=bundle, constraints=[])

    from mellow_link.services.refactoring_support_engine.decision_engine import DecisionEngine
    from mellow_link.services.refactoring_support_engine.diagnosis_engine import DiagnosisEngine
    from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
    from mellow_link.services.refactoring_support_engine.structure_analyzer import StructureAnalyzer

    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    decisions = DecisionEngine().run(prepared, structure, diagnosis, service)

    assert decisions.primary_judgment
    assert decisions.decision_summary.decisions
