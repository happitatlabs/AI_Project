from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.decision_engine import DecisionEngine
from mellow_link.services.refactoring_support_engine.diagnosis_engine import DiagnosisEngine
from mellow_link.services.refactoring_support_engine.improvement_planner import ImprovementPlanner
from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
from mellow_link.services.refactoring_support_engine.result_packager import ResultPackager
from mellow_link.services.refactoring_support_engine.schemas import (
    DecisionConflict,
    DecisionValidationIssue,
    DecisionValidationResult,
)
from mellow_link.services.refactoring_support_engine.structure_analyzer import StructureAnalyzer

from .refactoring_support_test_utils import build_safe_bundle


def _order_bundle():
    return build_safe_bundle(
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


def _build_order_context(goal: str = "modernize order creation flow", constraints: list[str] | None = None):
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal=goal, safe_bundle=_order_bundle(), constraints=constraints or ["keep db contract"])
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    decisions = DecisionEngine().run(prepared, structure, diagnosis, service)
    return service, prepared, structure, diagnosis, decisions


def test_improvement_planner_links_execution_stages_to_decisions():
    service, prepared, structure, diagnosis, decisions = _build_order_context()
    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, decisions, service)

    assert improvement.improvement_plan_bundle.execution_stages
    assert all(stage.decision_ids for stage in improvement.improvement_plan_bundle.execution_stages)
    assert improvement.improvement_plan_bundle.design_options
    assert improvement.option_execution_strategies
    assert improvement.schedule_hints


def test_improvement_planner_builds_option_strategies_and_schedule_hints():
    service, prepared, structure, diagnosis, base_decisions = _build_order_context()
    primary_decision_id = base_decisions.decision_summary.decisions[0].decision_id
    decisions = base_decisions.model_copy(
        update={
            "decision_basis": [
                item.model_copy(update={"recommendation_strength": "assertive", "risk_score": 0.81})
                if item.decision_id == primary_decision_id
                else item
                for item in base_decisions.decision_basis
            ]
        }
    )

    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, decisions, service)

    primary_strategy = next(item for item in improvement.option_execution_strategies if item.primary)
    assert primary_strategy.option_title
    assert primary_strategy.first_action
    assert primary_strategy.required_evidence
    assert primary_strategy.fallback_or_exit_condition
    assert primary_strategy.expected_deliverables
    assert primary_strategy.related_decision_basis_refs

    assert len(improvement.schedule_hints) == len(improvement.improvement_plan_bundle.execution_stages)
    assert [item.sequence_index for item in improvement.schedule_hints] == list(range(len(improvement.schedule_hints)))
    assert improvement.schedule_hints[0].stage_kind == improvement.improvement_plan_bundle.execution_stages[0].stage_kind
    assert any("monitoring" in item.stage_kind or "rollback" in " ".join(item.blocking_conditions + [item.suggested_order_reason]).lower() for item in improvement.schedule_hints)


def test_improvement_planner_assertive_stages_include_actionable_metadata():
    service, prepared, structure, diagnosis, base_decisions = _build_order_context()
    primary_decision_id = base_decisions.decision_summary.decisions[0].decision_id
    decisions = base_decisions.model_copy(
        update={
            "decision_basis": [
                item.model_copy(update={"recommendation_strength": "assertive"})
                if item.decision_id == primary_decision_id
                else item
                for item in base_decisions.decision_basis
            ]
        }
    )

    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, decisions, service)

    first_stage = improvement.improvement_plan_bundle.execution_stages[0]
    assert first_stage.priority == "P0"
    assert first_stage.phase == "immediate"
    assert first_stage.stage_kind not in {"verification_first", "precondition_check", "blocker_resolution"}
    assert first_stage.prerequisites
    assert first_stage.verification_methods
    assert first_stage.stop_conditions
    assert first_stage.deliverables
    assert first_stage.decision_basis_refs
    assert first_stage.fallback_action


def test_improvement_planner_review_required_prioritizes_verification_and_structures_checkpoints():
    service, prepared, structure, diagnosis, base_decisions = _build_order_context()
    primary = base_decisions.decision_summary.decisions[0]
    secondary = base_decisions.decision_summary.decisions[1]
    conflict = DecisionConflict(
        conflict_id="DCF-stage4-review",
        conflict_type="strategy_tradeoff",
        severity="review_required",
        summary="상위 전략 후보 점수가 근접합니다.",
        issue_ids=list(primary.issue_ids or []) + list(secondary.issue_ids or []),
        decision_ids=[primary.decision_id, secondary.decision_id],
        evidence_ids=list(primary.evidence_ids or []) + list(secondary.evidence_ids or []),
        resolution_hint="추가 근거 비교 후 상위 후보를 좁혀야 합니다.",
    )
    decisions = base_decisions.model_copy(
        update={
            "conflicts": [conflict],
            "decision_basis": [
                item.model_copy(update={"recommendation_strength": "review_required"})
                if item.decision_id == primary.decision_id
                else item
                for item in base_decisions.decision_basis
            ],
        }
    )
    prepared.decision_validation_result = DecisionValidationResult(
        passed=True,
        issues=[
            DecisionValidationIssue(
                issue_code="strategy_tradeoff",
                severity="review_required",
                message=conflict.summary,
                issue_ids=list(conflict.issue_ids),
                decision_ids=list(conflict.decision_ids),
                evidence_ids=list(conflict.evidence_ids),
            )
        ],
        conflicts=[conflict],
        missing_evidence=["decision_missing_evidence_refs"],
        retry_recommended=False,
        blocking_reason=None,
        status="pass",
        failure_types=[],
        retry_hint="",
    )

    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, decisions, service)

    assert improvement.execution_plan[0].goal == "근거 및 충돌 검증"
    first_stage = improvement.improvement_plan_bundle.execution_stages[0]
    first_schedule = improvement.schedule_hints[0]
    assert first_stage.priority == "P0"
    assert first_stage.phase == "immediate"
    assert first_stage.stage_kind == "verification_first"
    assert first_schedule.stage_kind == "verification_first"
    assert first_schedule.sequence_index == 0
    assert first_stage.verification_methods
    assert first_stage.stop_conditions
    first_checkpoint = improvement.verification_checkpoints[0]
    assert first_checkpoint.priority == "P0"
    assert first_checkpoint.pass_criteria
    assert first_checkpoint.failure_action
    assert first_checkpoint.related_decision_ids
    assert first_checkpoint.checkpoint_kind in {"conflict_resolution", "evidence_gathering", "blocker_resolution"}


def test_improvement_planner_blocked_state_generates_blocker_resolution_stage():
    service, prepared, structure, diagnosis, decisions = _build_order_context()
    prepared.decision_validation_result = DecisionValidationResult(
        passed=False,
        issues=[
            DecisionValidationIssue(
                issue_code="evidence_insufficient",
                severity="blocking",
                message="decision evidence is insufficient",
            )
        ],
        conflicts=[],
        missing_evidence=["decision_missing_evidence_refs"],
        retry_recommended=True,
        blocking_reason="decision evidence is insufficient",
        status="fail",
        failure_types=["evidence_insufficient"],
        retry_hint="evidence is insufficient; keep only evidence-grounded decisions and rerun.",
    )

    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, decisions, service)

    first_stage = improvement.improvement_plan_bundle.execution_stages[0]
    first_schedule = improvement.schedule_hints[0]
    assert improvement.recommended_option is None
    assert first_stage.stage_kind == "blocker_resolution"
    assert first_schedule.stage_kind == "blocker_resolution"
    assert first_stage.priority == "P0"
    assert first_stage.phase == "immediate"
    assert first_schedule.blocking_conditions
    assert any("차단" in item or "근거" in item for item in first_stage.stop_conditions + first_stage.tasks)


def test_improvement_planner_score_profile_strengthens_rollback_and_contract_outputs():
    service, prepared, structure, diagnosis, base_decisions = _build_order_context()
    primary_decision_id = base_decisions.decision_summary.decisions[0].decision_id
    decisions = base_decisions.model_copy(
        update={
            "decision_basis": [
                item.model_copy(
                    update={
                        "decision_id": primary_decision_id,
                        "recommendation_strength": "conditional",
                        "risk_score": 0.91,
                        "urgency_score": 0.88,
                        "maintainability_score": 0.86,
                        "confidence_score": 0.42,
                        "scoring_reasons": list(item.scoring_reasons or []) + ["forced_stage4_test_profile"],
                    }
                )
                if item.decision_id == primary_decision_id
                else item
                for item in base_decisions.decision_basis
            ]
        }
    )
    prepared.decision_validation_result = DecisionValidationResult(
        passed=True,
        issues=[],
        conflicts=[],
        missing_evidence=["decision_missing_evidence_refs"],
        retry_recommended=False,
        blocking_reason=None,
        status="pass",
        failure_types=[],
        retry_hint="",
    )

    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, decisions, service)

    first_stage = improvement.improvement_plan_bundle.execution_stages[0]
    assert first_stage.priority == "P0"
    assert first_stage.phase == "immediate"
    assert any("rollback" in text.lower() for text in first_stage.verification_methods + first_stage.deliverables)
    assert any("계약/인터페이스 경계표" in text for text in first_stage.deliverables)
    assert any(item.checkpoint_kind == "evidence_gathering" for item in improvement.verification_checkpoints[:2])


def test_improvement_planner_uses_domain_aware_stage_profile_when_templates_exist():
    service, prepared, structure, diagnosis, base_decisions = _build_order_context()
    primary_decision_id = base_decisions.decision_summary.decisions[0].decision_id
    decisions = base_decisions.model_copy(
        update={
            "decision_basis": [
                item.model_copy(update={"recommendation_strength": "assertive"})
                if item.decision_id == primary_decision_id
                else item
                for item in base_decisions.decision_basis
            ]
        }
    )

    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, decisions, service)

    first_stage = improvement.improvement_plan_bundle.execution_stages[0]
    assert first_stage.stage_kind in {
        "execution_start",
        "query_model_design",
        "validation_split",
        "workflow_design",
        "access_control_design",
        "state_transition_design",
        "threshold_policy_design",
    }
    if len(improvement.improvement_plan_bundle.execution_stages) > 1:
        assert any(
            stage.stage_kind in {
                "query_model_design",
                "validation_split",
                "workflow_design",
                "access_control_design",
                "state_transition_design",
                "threshold_policy_design",
            }
            for stage in improvement.improvement_plan_bundle.execution_stages[1:]
        )


def test_result_packager_exposes_planner_summary_consistently_for_blocked_plan():
    service, prepared, structure, diagnosis, decisions = _build_order_context()
    prepared.decision_validation_result = DecisionValidationResult(
        passed=False,
        issues=[
            DecisionValidationIssue(
                issue_code="evidence_insufficient",
                severity="blocking",
                message="decision evidence is insufficient",
            )
        ],
        conflicts=[],
        missing_evidence=["decision_missing_evidence_refs"],
        retry_recommended=True,
        blocking_reason="decision evidence is insufficient",
        status="fail",
        failure_types=["evidence_insufficient"],
        retry_hint="evidence is insufficient; keep only evidence-grounded decisions and rerun.",
    )
    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, decisions, service)
    result = ResultPackager().package(
        prepared,
        structure,
        diagnosis,
        decisions,
        improvement,
        service,
        validation_result=prepared.decision_validation_result,
    )

    planner_summary = result.extensions["decision_governance"]["planner_summary"]
    schedule_summary = result.extensions["decision_governance"]["schedule_summary"]
    primary_strategy = result.extensions["decision_governance"]["primary_option_strategy"]
    assert planner_summary["blocked_execution"] is True
    assert planner_summary["verification_first"] is True
    assert planner_summary["first_stage_priority"] == "P0"
    assert schedule_summary["schedule_mode"] == "blocked_first"
    assert schedule_summary["first_blocking_condition"]
    assert primary_strategy is not None
