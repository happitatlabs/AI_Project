from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.diagnosis_engine import DiagnosisEngine
from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
from mellow_link.services.refactoring_support_engine.structure_analyzer import StructureAnalyzer

from .refactoring_support_test_utils import build_safe_bundle


def test_diagnosis_engine_detects_mixed_responsibility_and_ui_data_access_coupling():
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
    def submit(self, order, repo):
        if not order.amount:
            raise ValueError("required")
        if order.status == "READY":
            repo.save(order)
            return approve(order)
                """,
            },
        ]
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order creation flow", safe_bundle=bundle, constraints=[])
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    detector_ids = {item.detector_id for item in diagnosis.diagnosis_report.issues}

    assert "mixed_responsibility" in detector_ids
    assert "ui_data_access_coupling" in detector_ids
    assert diagnosis.evidence_index


def test_diagnosis_engine_ignores_ui_text_without_real_data_access_signal():
    bundle = build_safe_bundle(
        [
            {
                "name": "order_page.html",
                "content": """
<div class="help">repository overview for operators</div>
<button onclick="openGuide()">guide</button>
                """,
            }
        ]
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order guide screen", safe_bundle=bundle, constraints=[])
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    detector_ids = {item.detector_id for item in diagnosis.diagnosis_report.issues}

    assert "ui_data_access_coupling" not in detector_ids


def test_diagnosis_engine_ignores_generic_guard_for_rule_scatter():
    bundle = build_safe_bundle(
        [
            {
                "name": "order_service.py",
                "content": """
class OrderService:
    def submit(self, order):
        if not order:
            return None
                """,
            },
            {
                "name": "approval_service.py",
                "content": """
class ApprovalService:
    def approve(self, order):
        if not order:
            return None
                """,
            },
        ]
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order flow", safe_bundle=bundle, constraints=[])
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    detector_ids = {item.detector_id for item in diagnosis.diagnosis_report.issues}

    assert "rule_scatter" not in detector_ids
