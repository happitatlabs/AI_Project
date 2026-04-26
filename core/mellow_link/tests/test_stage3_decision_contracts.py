from __future__ import annotations

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
from mellow_link.services.refactoring_support_engine.validation_engine import ValidationEngine

from .refactoring_support_test_utils import build_safe_bundle


def _cost_sml_bundle():
    return build_safe_bundle(
        [
            {
                "name": "cost_consulting_deck.pptx",
                "content": "\n".join(
                    [
                        "[SML v1]",
                        "presentation_file: cost_consulting_deck.pptx",
                        "slide_count: 2",
                        "",
                        "[SLIDE 1]",
                        "title: [CLIENT] 원가 컨설팅 개요",
                        "texts:",
                        "- 현행 원가체계 분석",
                        "- 원가분석 및 원가계산 개선 방향",
                        "- 재료비, 노무비, 제조경비 배부기준 검토",
                        "- 손익분석 확장 검토",
                        "",
                        "[SLIDE 2]",
                        "title: 배부기준 재정의",
                        "texts:",
                        "- 배부기준 조정",
                        "- 재료비 배부 기준",
                        "- 노무비 배부 기준",
                        "- 제조경비 배부 기준",
                    ]
                ),
            }
        ]
    )


def _order_asset_specs():
    return [
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


def test_question_guard_ownership_keeps_raw_and_effective_goal_separate():
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal="전면 재구축해야 하는가?",
        safe_bundle=_cost_sml_bundle(),
        constraints=["무조건 TO-BE 시스템으로 전환해야 하는가?"],
    )

    assert prepared.raw_goal == "전면 재구축해야 하는가?"
    assert prepared.goal == "현행 원가체계의 한계는 무엇인가?"
    assert prepared.guarded_decision_input.raw_goal == "전면 재구축해야 하는가?"
    assert prepared.guarded_decision_input.effective_goal == "현행 원가체계의 한계는 무엇인가?"
    assert prepared.guarded_decision_input.raw_constraints == ["무조건 TO-BE 시스템으로 전환해야 하는가?"]
    assert prepared.guarded_decision_input.applied_question_source == "source_candidates"
    assert prepared.question_guard_summary.selected_questions


def test_goal_only_contamination_is_recorded_as_conflict_without_migration_upgrade():
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal="전면 재구축해야 하는가?",
        safe_bundle=_cost_sml_bundle(),
        constraints=["무조건 TO-BE 시스템으로 전환해야 하는가?"],
    )
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    decisions = DecisionEngine().run(prepared, structure, diagnosis, service)

    assert decisions.structural_judgment != "migration_consideration"
    assert not any(item.decision_type == "migration_consideration" for item in decisions.decision_summary.decisions)
    assert any(item.conflict_type == "goal_source_mismatch" for item in decisions.conflicts)
    assert not decisions.decision_basis or any(basis.criteria.notes for basis in decisions.decision_basis)


def test_validation_engine_returns_typed_result_and_legacy_compatibility():
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal="modernize order approval flow",
        safe_bundle=build_safe_bundle(_order_asset_specs()),
        constraints=["기존 DB 계약 유지"],
    )
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    decisions = DecisionEngine().run(prepared, structure, diagnosis, service)

    validation = ValidationEngine().validate_decision(
        prepared=prepared,
        diagnosis=diagnosis,
        decisions=decisions,
        stage_control=prepared.stage_control,
    )

    assert isinstance(validation, DecisionValidationResult)
    assert validation.passed is True
    assert validation.status == "pass"
    assert validation.to_legacy_dict()["status"] == "pass"

    coerced = ValidationEngine().coerce_result(
        {
            "status": "fail",
            "failure_types": ["evidence_insufficient"],
            "retry_hint": "evidence is insufficient; keep only evidence-grounded decisions and rerun.",
        }
    )
    assert coerced.passed is False
    assert coerced.failure_types == ["evidence_insufficient"]
    assert coerced.retry_recommended is True


def test_result_packager_softens_conflicted_decision_as_conditional():
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal="modernize order approval flow",
        safe_bundle=build_safe_bundle(_order_asset_specs()),
        constraints=[],
    )
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    base_decisions = DecisionEngine().run(prepared, structure, diagnosis, service)
    primary = base_decisions.decision_summary.decisions[0]
    secondary = base_decisions.decision_summary.decisions[1]
    conflict = DecisionConflict(
        conflict_id="DCF-stage3-tradeoff",
        conflict_type="strategy_tradeoff",
        severity="review_required",
        summary="상위 전략 후보의 점수가 근접해 refactor/redesign 판단을 단정하기 어렵습니다.",
        issue_ids=list(primary.issue_ids or []) + list(secondary.issue_ids or []),
        decision_ids=[primary.decision_id, secondary.decision_id],
        evidence_ids=list(primary.evidence_ids or []) + list(secondary.evidence_ids or []),
        resolution_hint="추가 evidence 확인 전까지 조건부 판단으로 유지해야 합니다.",
    )
    conflicted_decisions = base_decisions.model_copy(
        update={
            "decision_summary": base_decisions.decision_summary.model_copy(
                update={
                    "decisions": [primary, secondary],
                    "priority_queue": [primary.decision_id, secondary.decision_id],
                    "conditional": True,
                    "review_required": True,
                    "conflict_ids": [conflict.conflict_id],
                }
            ),
            "conflicts": [conflict],
        }
    )
    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, conflicted_decisions, service)
    validation_result = DecisionValidationResult(
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
        missing_evidence=[],
        retry_recommended=False,
        blocking_reason=None,
        status="pass",
        failure_types=[],
        retry_hint="",
    )

    result = ResultPackager().package(
        prepared,
        structure,
        diagnosis,
        conflicted_decisions,
        improvement,
        service,
        validation_result=validation_result,
    )

    assert result.validation_result["status"] == "pass"
    assert result.extensions["decision_governance"]["validation_summary"]["review_required"] is True
    assert "review_required_conflict" in result.extensions["decision_governance"]["recommendation_grounding"]["reason_codes"]
    assert result.extensions["decision_governance"]["planner_summary"]["first_stage_kind"] == "verification_first"
    assert result.extensions["decision_governance"]["schedule_summary"]["schedule_mode"] == "verification_first"
    assert "검증" in result.one_line_conclusion or "검토" in result.one_line_conclusion
    assert any("검증" in line or "검토" in line for line in result.executive_summary_v2)
    assert any(
        token in result.judgment_canvas["conclusion"]["text"]
        for token in ("현재 근거 기준의 조건부 판단:", "추가 검토가 필요한 판단:", "우선 검토안", "조건부", "추가 검토", "실행 후보")
    )


def test_decision_basis_scoring_stays_source_grounded_and_goal_words_do_not_raise_confidence():
    service = RebuildAssistantService()
    neutral_prepared = service.prepare_safe_bundle_input(
        goal="modernize order approval flow",
        safe_bundle=build_safe_bundle(_order_asset_specs()),
        constraints=[],
    )
    forced_prepared = service.prepare_safe_bundle_input(
        goal="이 구조를 전환하고 마이그레이션하며 전면 재설계해야 하는가?",
        safe_bundle=build_safe_bundle(_order_asset_specs()),
        constraints=[],
    )

    neutral_structure = StructureAnalyzer().analyze(InputAssembler().assemble(neutral_prepared))
    forced_structure = StructureAnalyzer().analyze(InputAssembler().assemble(forced_prepared))
    neutral_diagnosis = DiagnosisEngine().run(neutral_prepared, neutral_structure, service)
    forced_diagnosis = DiagnosisEngine().run(forced_prepared, forced_structure, service)
    neutral_decisions = DecisionEngine().run(neutral_prepared, neutral_structure, neutral_diagnosis, service)
    forced_decisions = DecisionEngine().run(forced_prepared, forced_structure, forced_diagnosis, service)

    neutral_basis = neutral_decisions.decision_basis[0]
    forced_basis = forced_decisions.decision_basis[0]

    assert neutral_basis.score_scale == "0.0_to_1.0"
    for value in (
        neutral_basis.evidence_strength_score,
        neutral_basis.risk_score,
        neutral_basis.urgency_score,
        neutral_basis.maintainability_score,
        neutral_basis.confidence_score,
    ):
        assert 0.0 <= value <= 1.0
    assert neutral_basis.recommendation_strength in {"assertive", "conditional", "review_required", "blocked"}
    assert neutral_basis.recommendation_strength in {"assertive", "conditional"}
    assert forced_basis.confidence_score <= neutral_basis.confidence_score
    assert "raw_goal_direction_softened_by_source_guard" in forced_basis.criteria.notes or forced_basis.goal_signal_detected

    downgrade = DecisionValidationResult(
        passed=True,
        issues=[
            DecisionValidationIssue(
                issue_code="strategy_tradeoff",
                severity="review_required",
                message="conflict remains",
            )
        ],
        conflicts=[
            DecisionConflict(
                conflict_id="DCF-stage3-downgrade",
                conflict_type="strategy_tradeoff",
                severity="review_required",
                summary="conflict remains",
            )
        ],
        missing_evidence=["decision_missing_evidence_refs"],
        retry_recommended=False,
        blocking_reason=None,
        status="pass",
        failure_types=[],
        retry_hint="",
    )
    assert downgrade.apply_recommendation_strength(neutral_basis.recommendation_strength) in {"review_required", "blocked"}


def test_improvement_planner_uses_recommendation_strength_to_prioritize_verification():
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal="modernize order approval flow",
        safe_bundle=build_safe_bundle(_order_asset_specs()),
        constraints=[],
    )
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    base_decisions = DecisionEngine().run(prepared, structure, diagnosis, service)
    primary = base_decisions.decision_summary.decisions[0]
    secondary = base_decisions.decision_summary.decisions[1]
    conflict = DecisionConflict(
        conflict_id="DCF-stage3-planner-review",
        conflict_type="strategy_tradeoff",
        severity="review_required",
        summary="상위 전략 후보의 점수가 근접합니다.",
        issue_ids=list(primary.issue_ids or []) + list(secondary.issue_ids or []),
        decision_ids=[primary.decision_id, secondary.decision_id],
        evidence_ids=list(primary.evidence_ids or []) + list(secondary.evidence_ids or []),
        resolution_hint="상위 후보 간 추가 evidence를 비교해야 합니다.",
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

    assert improvement.execution_plan
    assert improvement.execution_plan[0].goal == "근거 및 충돌 검증"
    assert improvement.verification_checkpoints
    assert any("추가 확인" in item.item or "비교 검증" in item.item for item in improvement.verification_checkpoints[:2])
    assert improvement.recommended_option is not None
    assert "실행 후보" in improvement.recommended_option.selection_reason


def test_result_packager_blocks_hard_conclusion_when_validation_blocks():
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal="modernize order approval flow",
        safe_bundle=build_safe_bundle(_order_asset_specs()),
        constraints=[],
    )
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    decisions = DecisionEngine().run(prepared, structure, diagnosis, service)
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

    assert result.recommended_option is None
    assert result.improvement_plan_bundle["recommended_option"] is None
    assert result.extensions["decision_governance"]["planner_summary"]["blocked_execution"] is True
    assert result.extensions["decision_governance"]["schedule_summary"]["schedule_mode"] == "blocked_first"
    assert "실행에 착수할 수 없습니다" in result.one_line_conclusion
    assert any("차단" in line or "근거 보강" in line for line in result.executive_summary_v2)
    assert "결론을 확정할 수 없습니다" in result.judgment_canvas["conclusion"]["text"]
    assert result.extensions["decision_governance"]["recommendation_strength"] == "blocked"


def test_result_packager_conditional_summary_tracks_precondition_first_plan():
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal="modernize order approval flow",
        safe_bundle=build_safe_bundle(_order_asset_specs()),
        constraints=[],
    )
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    decisions = DecisionEngine().run(prepared, structure, diagnosis, service)
    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, decisions, service)

    result = ResultPackager().package(
        prepared,
        structure,
        diagnosis,
        decisions,
        improvement,
        service,
    )

    assert result.extensions["decision_governance"]["planner_summary"]["first_stage_kind"] == "precondition_check"
    assert result.extensions["decision_governance"]["schedule_summary"]["schedule_mode"] == "conditional_first"
    assert "조건" in result.one_line_conclusion
    assert any("조건" in line for line in result.executive_summary_v2)
    assert "조건부" in result.judgment_canvas["conclusion"]["text"] or "조건 확인" in result.judgment_canvas["conclusion"]["text"]


def test_result_packager_assertive_summary_keeps_execution_first_tone():
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal="modernize order approval flow",
        safe_bundle=build_safe_bundle(_order_asset_specs()),
        constraints=[],
    )
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    base_decisions = DecisionEngine().run(prepared, structure, diagnosis, service)
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

    result = ResultPackager().package(
        prepared,
        structure,
        diagnosis,
        decisions,
        improvement,
        service,
    )

    assert result.extensions["decision_governance"]["schedule_summary"]["schedule_mode"] == "execution_first"
    assert result.extensions["decision_governance"]["planner_summary"]["first_stage_kind"] == "execution_start"
    assert "우선 검토" not in result.one_line_conclusion
    assert not any("추가 검토" in line for line in result.executive_summary_v2[:3])
