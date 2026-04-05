from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
from mellow_link.services.refactoring_support_engine.structure_analyzer import StructureAnalyzer

from .refactoring_support_test_utils import build_safe_bundle


def test_structure_analyzer_splits_async_component_from_api_slice():
    bundle = build_safe_bundle(
        [
            {
                "name": "order_controller.py",
                "content": """
@router.post("/orders")
def create_order():
    return OrderService().submit()

async def send_order_notification():
    await queue.publish("created")
                """,
            },
            {"name": "order_service.py", "content": "class OrderService: pass"},
        ]
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order creation flow", safe_bundle=bundle, constraints=[])
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))

    api_slice = next(item for item in structure.structure_snapshot.feature_slices if item.entry_points[0] == "api:POST /orders")
    async_components = [item.component_id for item in structure.structure_snapshot.components if item.layer == "async"]

    assert async_components
    assert not any(component_id in api_slice.related_components for component_id in async_components)
    assert len(structure.structure_snapshot.feature_slices) >= 2


def test_input_assembler_and_structure_analyzer_preserve_seed_structures():
    bundle = build_safe_bundle(
        [
            {"name": "order_service.py", "content": "class OrderService: pass"},
        ]
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order flow", safe_bundle=bundle, constraints=[])
    analysis_input = InputAssembler().assemble(prepared)
    structure = StructureAnalyzer().analyze(analysis_input)

    assert analysis_input.seed_structures == bundle.structures
    assert structure.seed_structures == bundle.structures
