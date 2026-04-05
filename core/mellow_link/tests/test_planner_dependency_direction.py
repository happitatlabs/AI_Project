from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.planning_synthesizer import PlanningSynthesizer

from .refactoring_support_test_utils import build_safe_bundle


def test_planning_synthesizer_requires_decision_artifacts():
    bundle = build_safe_bundle(
        [
            {
                "name": "order_service.py",
                "content": "def submit(order, repo):\n    if order.status == 'READY':\n        return repo.save(order)\n",
            }
        ]
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order flow", safe_bundle=bundle, constraints=[])
    core_rules = service.analyze_assets(prepared)
    grounded_rules = service.build_grounded_business_rules(prepared, core_rules)
    retained_contracts = service.build_retained_contracts(prepared, grounded_rules)

    import pytest

    with pytest.raises(ValueError):
        PlanningSynthesizer(service).build_design_options(prepared, grounded_rules, retained_contracts, None)


def test_planning_synthesizer_changes_plan_when_primary_judgment_changes():
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
            {"name": "query.sql", "content": "SELECT * FROM orders WHERE status = 'READY' ORDER BY created_at DESC"},
        ]
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order flow", safe_bundle=bundle, constraints=[])
    core_rules = service.analyze_assets(prepared)
    grounded_rules = service.build_grounded_business_rules(prepared, core_rules)
    retained_contracts = service.build_retained_contracts(prepared, grounded_rules)
    applied_templates = service.build_applied_templates(prepared, grounded_rules, retained_contracts)
    synth = PlanningSynthesizer(service)

    base_decisions = service._compat_decision_artifacts(prepared, applied_templates)
    query_decisions = base_decisions.model_copy(update={"primary_judgment": "query_filter", "selected_narrative_judgment": "query_filter"})
    validation_decisions = base_decisions.model_copy(update={"primary_judgment": "validation", "selected_narrative_judgment": "validation"})

    query_options = synth.build_design_options(prepared, grounded_rules, retained_contracts, query_decisions)
    validation_options = synth.build_design_options(prepared, grounded_rules, retained_contracts, validation_decisions)

    assert [item.name for item in query_options] != [item.name for item in validation_options]
