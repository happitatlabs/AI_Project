from __future__ import annotations

import pytest

from mellow_link.infra import ModernizationProject
from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.routers.projects import build_result_package
from mellow_link.services.refactoring_support_engine.decision_engine import DecisionEngine
from mellow_link.services.refactoring_support_engine.facade import RefactoringSupportEngineFacade
from mellow_link.services.refactoring_support_engine.diagnosis_engine import DiagnosisEngine
from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
from mellow_link.services.refactoring_support_engine.runtime_contracts import (
    StageControlViolation,
    build_stage_control,
)
from mellow_link.services.refactoring_support_engine.structure_analyzer import StructureAnalyzer

from .refactoring_support_test_utils import build_safe_bundle


def _asset_specs():
    return [
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
        {
            "name": "order_page.jsp",
            "content": """
<% String sql = "SELECT * FROM orders WHERE status = 'READY'"; %>
<button onclick="submitOrder()">submit</button>
            """,
        },
        {
            "name": "order_query.sql",
            "content": "SELECT * FROM orders WHERE status = 'READY' AND amount > 1000",
        },
        {
            "name": "schema.sql",
            "content": """
CREATE TABLE orders (
    id NUMBER,
    status VARCHAR2(20),
    amount NUMBER
);
            """,
        },
    ]


def _build_prepared(goal: str = "modernize order approval flow"):
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal=goal,
        safe_bundle=build_safe_bundle(_asset_specs()),
        constraints=["기존 DB 계약 유지"],
    )
    return service, prepared


def test_decision_engine_blocks_result_generation_in_wrong_stage():
    service, prepared = _build_prepared()
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    stage_control = build_stage_control(prepared.goal, current_stage="analysis")

    with pytest.raises(StageControlViolation):
        DecisionEngine().run(
            prepared,
            structure,
            diagnosis,
            service,
            stage_control=stage_control,
        )


def test_facade_retries_decision_validation_only_once(monkeypatch):
    service, prepared = _build_prepared()
    facade = RefactoringSupportEngineFacade(service)
    decision_run_count = {"value": 0}
    real_run = facade.decision_engine.run
    validation_results = iter(
        [
            {
                "status": "fail",
                "failure_types": ["evidence_insufficient"],
                "retry_hint": "evidence is insufficient; keep only evidence-grounded decisions and rerun.",
            },
            {
                "status": "pass",
                "failure_types": [],
                "retry_hint": "",
            },
        ]
    )

    def tracked_run(*args, **kwargs):
        decision_run_count["value"] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr(facade.decision_engine, "run", tracked_run)
    monkeypatch.setattr(
        facade.validation_engine,
        "validate_decision",
        lambda **kwargs: next(validation_results),
    )

    result = facade.build_result(prepared)

    assert decision_run_count["value"] == 2
    assert result.validation_result["status"] == "pass"
    assert result.stage_control["current_stage"] == "planning"


def test_facade_stops_after_single_retry_when_validation_keeps_failing(monkeypatch):
    service, prepared = _build_prepared()
    facade = RefactoringSupportEngineFacade(service)
    decision_run_count = {"value": 0}
    real_run = facade.decision_engine.run

    def tracked_run(*args, **kwargs):
        decision_run_count["value"] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr(facade.decision_engine, "run", tracked_run)
    monkeypatch.setattr(
        facade.validation_engine,
        "validate_decision",
        lambda **kwargs: {
            "status": "fail",
            "failure_types": ["forbidden_condition_violation"],
            "retry_hint": "forbidden condition detected; filter blocked decision types and rerun.",
        },
    )

    with pytest.raises(ValueError, match="validation failed after single retry"):
        facade.build_result(prepared)

    assert decision_run_count["value"] == 2


def test_build_result_always_contains_judgment_canvas_with_evidence_refs():
    service, prepared = _build_prepared()
    prepared.stage_control = build_stage_control(prepared.goal)

    result = service.build_result(prepared)

    assert result.validation_result["status"] == "pass"
    assert result.stage_control["current_stage"] == "planning"
    assert set(result.judgment_canvas) == {
        "situation_purpose",
        "problem_definition",
        "judgment_question",
        "options",
        "criteria",
        "conclusion",
        "risk",
    }
    for key in ("situation_purpose", "problem_definition", "judgment_question", "conclusion", "risk"):
        assert result.judgment_canvas[key]["evidence_refs"]
    assert result.judgment_canvas["options"]
    assert result.judgment_canvas["criteria"]
    assert all(item["evidence_refs"] for item in result.judgment_canvas["options"])
    assert all(item["evidence_refs"] for item in result.judgment_canvas["criteria"])


def test_result_package_exposes_judgment_canvas_as_fixed_output_surface():
    service, prepared = _build_prepared()
    prepared.stage_control = build_stage_control(prepared.goal)
    result = service.build_result(prepared)
    polish_bundle = service.build_polish_bundle(
        result,
        audience="manager",
        delivery_mode="client_report",
    ).model_dump()
    project = ModernizationProject(
        id="proj_stage_canvas",
        user_id=1,
        session_id="sess_stage_canvas",
        run_id="run_stage_canvas",
        project_name="주문 승인 현대화",
        client_name="OO생명",
        template_key="default_modernization_v1",
        template_mode="recommended",
        constraints_json="[]",
        upload_session_id="upload_stage_canvas",
        asset_manifest_json="[]",
        status="completed",
    )

    package = build_result_package(
        project,
        {"status": "completed", "run_id": project.run_id},
        result,
        assets=[],
        polish_bundle=polish_bundle,
        app_version="0.1.0",
    )

    assert package["judgment_canvas"] == result.judgment_canvas
    assert package["authoritative_payload"]["judgment_canvas"] == result.judgment_canvas
    assert package["validation_result"]["status"] == "pass"
