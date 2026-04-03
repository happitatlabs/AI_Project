from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
from mellow_link.services.refactoring_support_engine.structure_analyzer import StructureAnalyzer

from .refactoring_support_test_utils import build_safe_bundle


def test_feature_slice_extractor_prefers_api_endpoint_seed():
    bundle = build_safe_bundle(
        [
            {
                "name": "order_controller.py",
                "content": """
@router.post("/orders")
def create_order():
    return OrderService().submit()
                """,
            },
            {"name": "order_service.py", "content": "class OrderService: pass"},
            {"name": "order_page.html", "content": '<button onclick="submitOrder()">submit</button>'},
        ]
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order creation flow", safe_bundle=bundle, constraints=[])
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))

    assert structure.structure_snapshot.feature_slices
    assert structure.structure_snapshot.feature_slices[0].entry_points[0] == "api:POST /orders"


def test_feature_slice_extractor_uses_ui_action_when_api_is_absent():
    bundle = build_safe_bundle(
        [
            {
                "name": "order_page.html",
                "content": """
<button onclick="submitOrder()">Submit</button>
<script>
function submitOrder() { return true; }
</script>
                """,
            }
        ]
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order submit screen", safe_bundle=bundle, constraints=[])
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))

    assert structure.structure_snapshot.feature_slices[0].entry_points[0] == "ui:OrderPage#submitorder"


def test_feature_slice_extractor_falls_back_to_usecase_seed():
    bundle = build_safe_bundle(
        [
            {"name": "legacy_service.py", "content": "class OrderApprovalService: pass"},
        ]
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order approval flow", safe_bundle=bundle, constraints=[])
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))

    assert structure.structure_snapshot.feature_slices[0].entry_points[0].startswith("usecase:")


def test_feature_slice_extractor_separates_endpoint_handlers_in_same_asset():
    bundle = build_safe_bundle(
        [
            {
                "name": "order_controller.py",
                "content": """
@router.post("/orders")
def create_order():
    return create_service()

@router.post("/orders/{order_id}/approve")
def approve_order(order_id):
    return approve_service(order_id)

def create_service():
    return True

def approve_service(order_id):
    return order_id
                """,
            }
        ]
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order approval flow", safe_bundle=bundle, constraints=[])
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))

    components_by_id = {item.component_id: item.name for item in structure.structure_snapshot.components}
    slices_by_entry = {item.entry_points[0]: item for item in structure.structure_snapshot.feature_slices}

    create_slice = slices_by_entry["api:POST /orders"]
    approve_slice = slices_by_entry["api:POST /orders/{order_id}/approve"]
    create_names = {components_by_id[component_id] for component_id in create_slice.related_components}
    approve_names = {components_by_id[component_id] for component_id in approve_slice.related_components}

    assert "CreateOrder" in create_names
    assert "ApproveOrder" not in create_names
    assert "ApproveOrder" in approve_names
    assert "CreateOrder" not in approve_names
