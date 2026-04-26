from __future__ import annotations

from typing import Any

from mellow_link.modules.rebuild_assistant.schemas import ExecutionPlanWeek, VerificationItem

from .planning_synthesizer import PlanningSynthesizer
from .runtime_contracts import assert_stage_action
from .schemas import (
    DecisionArtifacts,
    DecisionBasis,
    DecisionValidationResult,
    DiagnosisArtifacts,
    ExecutionScheduleHint,
    ExecutionStage,
    ImprovementArtifacts,
    ImprovementPlanBundle,
    OptionExecutionStrategy,
    RiskCheckpoint,
    StructureAnalysisResult,
    make_stable_id,
    max_recommendation_strength,
)


class ImprovementPlanner:
    def __init__(self) -> None:
        self.planning_synthesizer: PlanningSynthesizer | None = None

    def run(
        self,
        prepared: Any,
        structure: StructureAnalysisResult,
        diagnosis: DiagnosisArtifacts,
        decisions: DecisionArtifacts,
        legacy_service: Any | None = None,
        *,
        stage_control: dict[str, object] | None = None,
    ) -> ImprovementArtifacts:
        assert_stage_action(
            stage_control or getattr(prepared, "stage_control", None),
            expected_stage="planning",
            action="generate_improvement_plan",
            goal=str(getattr(prepared, "goal", "") or ""),
        )
        planning_synthesizer = self.planning_synthesizer or PlanningSynthesizer()
        if decisions is None:
            raise ValueError("DecisionArtifacts are required for planning.")
        priority_split_items = planning_synthesizer.build_priority_split_items(
            prepared,
            diagnosis.grounded_business_rules,
            diagnosis.retained_contracts,
            decisions,
        )
        design_options = planning_synthesizer.build_design_options(
            prepared,
            diagnosis.grounded_business_rules,
            diagnosis.retained_contracts,
            decisions,
        )
        design_options = planning_synthesizer.apply_recommended_selection_reason(
            prepared,
            design_options,
            diagnosis.grounded_business_rules,
            diagnosis.retained_contracts,
            decisions,
        )
        recommended_option = planning_synthesizer.pick_recommended_option(
            design_options,
            prepared,
            diagnosis.grounded_business_rules,
            diagnosis.retained_contracts,
            decisions,
        )
        verification_checkpoints = planning_synthesizer.build_verification_checkpoints(
            prepared,
            diagnosis.grounded_business_rules,
            diagnosis.retained_contracts,
            decisions=decisions,
        )
        execution_plan = planning_synthesizer.build_execution_plan(
            prepared,
            diagnosis.grounded_business_rules,
            diagnosis.retained_contracts,
            recommended_option,
            decisions,
        )
        planning_context = planning_synthesizer.describe_execution_context(
            prepared,
            diagnosis.grounded_business_rules,
            diagnosis.retained_contracts,
            decisions,
        )
        validation_result = self._decision_validation_result(prepared)
        recommendation_strength = self._resolve_recommendation_strength(decisions, validation_result)
        primary_basis = self._primary_decision_basis(decisions)
        verification_checkpoints = self._augment_verification_checkpoints(
            verification_checkpoints,
            validation_result=validation_result,
            conflicts=list(decisions.conflicts or []),
            recommendation_strength=recommendation_strength,
            decisions=decisions,
            primary_basis=primary_basis,
            planning_context=planning_context,
        )
        recommended_option = self._adjust_recommended_option(
            recommended_option,
            recommendation_strength=recommendation_strength,
        )
        execution_plan = self._adjust_execution_plan(
            execution_plan,
            verification_checkpoints=verification_checkpoints,
            validation_result=validation_result,
            recommendation_strength=recommendation_strength,
        )
        rebuild_strategy = planning_synthesizer.infer_target_architecture(prepared)
        layer_reconstruction = planning_synthesizer.build_layer_reconstruction(prepared)
        recomposition_draft = planning_synthesizer.build_recomposition_draft(prepared, decisions)
        risks = planning_synthesizer.build_risks(
            prepared,
            diagnosis.grounded_business_rules,
            diagnosis.retained_contracts,
            decisions,
        )
        recommended_directions = planning_synthesizer.build_recommended_directions(prepared)

        execution_stages = self._execution_stages(
            execution_plan,
            decisions,
            verification_checkpoints=verification_checkpoints,
            validation_result=validation_result,
            recommendation_strength=recommendation_strength,
            primary_basis=primary_basis,
            planning_context=planning_context,
        )
        option_execution_strategies = self._option_execution_strategies(
            design_options=design_options,
            recommended_option=recommended_option,
            execution_stages=execution_stages,
            verification_checkpoints=verification_checkpoints,
            validation_result=validation_result,
            recommendation_strength=recommendation_strength,
            primary_basis=primary_basis,
            planning_context=planning_context,
            decisions=decisions,
            risks=risks,
        )
        schedule_hints = self._schedule_hints(
            execution_stages=execution_stages,
            recommendation_strength=recommendation_strength,
            validation_result=validation_result,
            primary_basis=primary_basis,
        )
        risk_checkpoints = self._risk_checkpoints(risks, verification_checkpoints, decisions)
        improvement_bundle = ImprovementPlanBundle(
            design_options=[item.model_dump() for item in design_options],
            recommended_option=recommended_option.model_dump() if recommended_option else None,
            execution_stages=execution_stages,
            risk_checkpoints=risk_checkpoints,
        )
        return ImprovementArtifacts(
            improvement_plan_bundle=improvement_bundle,
            priority_split_items=priority_split_items,
            verification_checkpoints=verification_checkpoints,
            design_options=design_options,
            recommended_option=recommended_option,
            execution_plan=execution_plan,
            rebuild_strategy=rebuild_strategy,
            layer_reconstruction=layer_reconstruction,
            recomposition_draft=recomposition_draft,
            risks=risks,
            recommended_directions=recommended_directions,
            option_execution_strategies=option_execution_strategies,
            schedule_hints=schedule_hints,
        )

    def _execution_stages(
        self,
        execution_plan,
        decisions: DecisionArtifacts,
        *,
        verification_checkpoints: list[VerificationItem],
        validation_result: DecisionValidationResult | None,
        recommendation_strength: str,
        primary_basis: DecisionBasis | None,
        planning_context: dict[str, Any],
    ) -> list[ExecutionStage]:
        records = decisions.decision_summary.decisions
        default_decision_ids = [item.decision_id for item in records[:2]] or [make_stable_id("DEC", "fallback")]
        stages: list[ExecutionStage] = []
        total_stages = len(list(execution_plan or []))
        for index, week in enumerate(execution_plan):
            stage_decision_ids = [item.decision_id for item in records[index:index + 2]] or default_decision_ids[:1]
            risk_ids = [make_stable_id("RISK", week.week_label, task) for task in week.tasks[:2]]
            priority, phase = self._stage_priority(
                index=index,
                recommendation_strength=recommendation_strength,
                urgency_score=float(getattr(primary_basis, "urgency_score", 0.0) or 0.0),
            )
            stage_kind = self._stage_kind(
                index=index,
                total=total_stages,
                recommendation_strength=recommendation_strength,
                planning_context=planning_context,
                primary_basis=primary_basis,
            )
            related_checkpoints = self._stage_related_checkpoints(
                verification_checkpoints,
                index=index,
                recommendation_strength=recommendation_strength,
            )
            stages.append(
                ExecutionStage(
                    stage_id=make_stable_id("STAGE", week.week_label, week.goal, week.tasks),
                    title=week.goal,
                    tasks=list(week.tasks),
                    decision_ids=stage_decision_ids,
                    verification_checkpoint_ids=[
                        make_stable_id("VERIFY", item.item, item.reason)
                        for item in related_checkpoints[:2]
                    ],
                    risk_ids=risk_ids,
                    depends_on=self._stage_dependencies(
                        existing_stages=stages,
                        index=index,
                        recommendation_strength=recommendation_strength,
                        priority=priority,
                        phase=phase,
                        primary_basis=primary_basis,
                    ),
                    objective=week.goal,
                    priority=priority,
                    phase=phase,
                    stage_kind=stage_kind,
                    prerequisites=self._stage_prerequisites(
                        week=week,
                        index=index,
                        prior_stage=stages[-1] if stages else None,
                        validation_result=validation_result,
                        recommendation_strength=recommendation_strength,
                        primary_basis=primary_basis,
                    ),
                    verification_methods=self._stage_verification_methods(
                        week=week,
                        related_checkpoints=related_checkpoints,
                        recommendation_strength=recommendation_strength,
                        primary_basis=primary_basis,
                    ),
                    stop_conditions=self._stage_stop_conditions(
                        index=index,
                        validation_result=validation_result,
                        recommendation_strength=recommendation_strength,
                        primary_basis=primary_basis,
                    ),
                    deliverables=self._stage_deliverables(
                        week=week,
                        index=index,
                        recommendation_strength=recommendation_strength,
                        primary_basis=primary_basis,
                    ),
                    evidence_refs=self._stage_evidence_refs(week=week, primary_basis=primary_basis),
                    decision_basis_refs=self._decision_basis_refs(primary_basis, recommendation_strength),
                    fallback_action=self._stage_fallback_action(
                        recommendation_strength=recommendation_strength,
                        validation_result=validation_result,
                    ),
                )
            )
        if not stages and records:
            stages.append(
                ExecutionStage(
                    stage_id=make_stable_id("STAGE", records[0].decision_id),
                    title="핵심 책임 분리",
                    tasks=["우선순위가 가장 높은 구조 문제를 분리합니다."],
                    decision_ids=[records[0].decision_id],
                    verification_checkpoint_ids=[],
                    risk_ids=[],
                    depends_on=[],
                    objective="핵심 구조 문제를 우선 분리합니다.",
                    priority="P0",
                    phase="immediate",
                    stage_kind="fallback_execution",
                    prerequisites=["핵심 판단 근거와 유지 계약 범위가 먼저 정리되어야 합니다."],
                    verification_methods=["핵심 판단 근거가 diagnosis evidence_index와 연결되는지 확인합니다."],
                    stop_conditions=["추가 근거 없이 다음 단계로 확정하지 않습니다."],
                    deliverables=["핵심 책임 분리 초안"],
                    evidence_refs=[],
                    decision_basis_refs=[],
                    fallback_action="추가 evidence를 확보한 뒤 실행 단계를 다시 구성합니다.",
                )
            )
        return stages

    def _risk_checkpoints(self, risks: list[str], verification_checkpoints, decisions: DecisionArtifacts) -> list[RiskCheckpoint]:
        decision_ids = [item.decision_id for item in decisions.decision_summary.decisions[:2]]
        checkpoints: list[RiskCheckpoint] = []
        for risk in risks[:3]:
            checkpoints.append(
                RiskCheckpoint(
                    checkpoint_id=make_stable_id("RISK", risk),
                    title=risk[:60],
                    description=risk,
                    decision_ids=decision_ids[:1],
                )
            )
        for item in verification_checkpoints[:2]:
            checkpoints.append(
                RiskCheckpoint(
                    checkpoint_id=make_stable_id("RISK", item.item, item.reason),
                    title=item.item,
                    description=item.reason,
                    decision_ids=decision_ids[:1],
                )
            )
        deduped: dict[str, RiskCheckpoint] = {item.checkpoint_id: item for item in checkpoints}
        return list(deduped.values())

    def _decision_validation_result(self, prepared: Any) -> DecisionValidationResult | None:
        payload = getattr(prepared, "decision_validation_result", None)
        if payload is None:
            return None
        return DecisionValidationResult.coerce(payload)

    def _resolve_recommendation_strength(
        self,
        decisions: DecisionArtifacts,
        validation_result: DecisionValidationResult | None,
    ) -> str:
        records = list(decisions.decision_summary.decisions or [])
        top_decision_id = str(records[0].decision_id or "").strip() if records else ""
        basis = next(
            (item for item in list(decisions.decision_basis or []) if item.decision_id == top_decision_id),
            None,
        )
        if basis is None:
            basis = next(iter(list(decisions.decision_basis or [])), None)
        recommendation_strength = getattr(basis, "recommendation_strength", "review_required") if basis is not None else "review_required"
        if validation_result is not None:
            return validation_result.apply_recommendation_strength(recommendation_strength)
        if any(item.severity == "blocking" for item in list(decisions.conflicts or [])):
            return "blocked"
        if any(item.severity == "review_required" for item in list(decisions.conflicts or [])):
            return max_recommendation_strength(recommendation_strength, "review_required")
        if any(item.severity == "warning" for item in list(decisions.conflicts or [])):
            return max_recommendation_strength(recommendation_strength, "conditional")
        return recommendation_strength

    def _augment_verification_checkpoints(
        self,
        verification_checkpoints: list[VerificationItem],
        *,
        validation_result: DecisionValidationResult | None,
        conflicts,
        recommendation_strength: str,
        decisions: DecisionArtifacts,
        primary_basis: DecisionBasis | None,
        planning_context: dict[str, Any],
    ) -> list[VerificationItem]:
        items = list(verification_checkpoints or [])
        prepended: list[VerificationItem] = []
        decision_ids = [str(item.decision_id or "").strip() for item in list(decisions.decision_summary.decisions or [])[:2] if str(item.decision_id or "").strip()]
        conflict_ids = [str(getattr(item, "conflict_id", "") or "").strip() for item in list(conflicts or []) if str(getattr(item, "conflict_id", "") or "").strip()]
        if recommendation_strength == "blocked":
            prepended.append(
                VerificationItem(
                    item="차단 사유와 누락 근거를 우선 해소하는 것이 필요합니다.",
                    reason=(
                        str(getattr(validation_result, "blocking_reason", "") or "").strip()
                        or "현재 판단은 실행 로드맵보다 차단 사유와 누락 근거 해소가 우선입니다."
                    ),
                    evidence=[],
                    target="차단 사유와 누락 근거",
                    required_evidence=list(dict.fromkeys(list(getattr(validation_result, "missing_evidence", []) or []))),
                    pass_criteria="차단 사유가 해소되고 상위 판단의 evidence 연결 상태가 다시 확인됩니다.",
                    failure_action="차단 사유 해소 전에는 실행 로드맵을 확정하지 않고 재판단을 요청합니다.",
                    checkpoint_kind="blocker_resolution",
                    priority="P0",
                    related_decision_ids=decision_ids,
                    related_conflict_ids=conflict_ids,
                )
            )
        if validation_result is not None and list(validation_result.missing_evidence or []):
            prepended.append(
                VerificationItem(
                    item="핵심 판단 근거를 추가 확인하는 것이 필요합니다.",
                    reason="결정에 연결된 evidence reference가 부족하거나 diagnosis evidence_index와 충분히 연결되지 않았습니다.",
                    evidence=[],
                    target="상위 판단 evidence reference",
                    required_evidence=list(dict.fromkeys(list(validation_result.missing_evidence or []))),
                    pass_criteria="상위 판단의 evidence_ids가 diagnosis evidence_index에 모두 연결됩니다.",
                    failure_action="근거 확보 전에는 추천 강도를 올리지 않고 review_required 또는 blocked 상태를 유지합니다.",
                    checkpoint_kind="evidence_gathering",
                    priority="P0" if recommendation_strength in {"blocked", "review_required"} else "P1",
                    related_decision_ids=decision_ids,
                    related_conflict_ids=conflict_ids,
                )
            )
        if any(getattr(item, "severity", "") in {"review_required", "blocking"} for item in list(conflicts or [])):
            first_conflict = next(iter(list(conflicts or [])), None)
            prepended.append(
                VerificationItem(
                    item="상충 판단 근거를 비교 검증하는 것이 필요합니다.",
                    reason=str(getattr(first_conflict, "resolution_hint", "") or "충돌하는 판단 신호를 추가 evidence로 정리해야 합니다."),
                    evidence=[],
                    target="상충 판단 후보",
                    required_evidence=[str(getattr(first_conflict, "summary", "") or "상충 판단 근거")],
                    pass_criteria="충돌하는 판단 후보 중 하나로 수렴하거나 조건부 유지 사유가 명확히 기록됩니다.",
                    failure_action="충돌 해소 전에는 실행 후보 상태로만 유지하고 확정 결론을 피합니다.",
                    checkpoint_kind="conflict_resolution",
                    priority="P0",
                    related_decision_ids=decision_ids,
                    related_conflict_ids=conflict_ids,
                )
            )
        elif recommendation_strength == "conditional":
            prepended.append(
                VerificationItem(
                    item="조건부 판단의 전제와 제약을 확인하는 것이 필요합니다.",
                    reason="현재 실행안은 source evidence는 있으나 적용 전 전제 확인이 필요합니다.",
                    evidence=[],
                    target="조건부 실행 전제",
                    required_evidence=["선행 조건 충족 여부", "유지 계약 영향 범위", "적용 제외 조건"],
                    pass_criteria="조건부 실행 전제와 적용 제외 조건이 모두 확인됩니다.",
                    failure_action="전제가 충족되지 않으면 실행을 보류하고 대안을 비교합니다.",
                    checkpoint_kind="precondition_check",
                    priority="P0",
                    related_decision_ids=decision_ids,
                )
            )
        deduped: dict[str, VerificationItem] = {}
        for index, item in enumerate(prepended + items):
            item = self._enrich_verification_item(
                item,
                index=index,
                recommendation_strength=recommendation_strength,
                primary_basis=primary_basis,
                decision_ids=decision_ids,
                conflict_ids=conflict_ids,
                planning_context=planning_context,
            )
            key = str(item.item or "").strip().lower()
            if key and key not in deduped:
                deduped[key] = item
        return list(deduped.values())

    def _adjust_recommended_option(self, recommended_option, *, recommendation_strength: str):
        if recommended_option is None:
            return None
        if recommendation_strength == "assertive":
            return recommended_option
        if recommendation_strength == "blocked":
            return None
        prefix = "조건부 실행안입니다." if recommendation_strength == "conditional" else "추가 검토 전까지는 실행 후보로만 유지합니다."
        if prefix in str(recommended_option.selection_reason or ""):
            return recommended_option
        return recommended_option.model_copy(
            update={
                "selection_reason": f"{prefix} {str(recommended_option.selection_reason or '').strip()}".strip(),
            }
        )

    def _adjust_execution_plan(
        self,
        execution_plan: list[ExecutionPlanWeek],
        *,
        verification_checkpoints: list[VerificationItem],
        validation_result: DecisionValidationResult | None,
        recommendation_strength: str,
    ) -> list[ExecutionPlanWeek]:
        if recommendation_strength == "assertive":
            return execution_plan
        if recommendation_strength == "blocked":
            blocker_tasks = [item.item for item in verification_checkpoints[:3]] or [
                str(getattr(validation_result, "blocking_reason", "") or "차단 사유를 해소합니다.").strip()
            ]
            return [
                ExecutionPlanWeek(
                    week_label="선행 검증",
                    goal="실행 차단 요인 해소",
                    tasks=blocker_tasks,
                    roles=["분석", "검증"],
                    deliverables=["차단 사유 해소 여부 확인", "추가 근거 확보"],
                )
            ]
        gate_goal = "조건부 실행 전제 확인" if recommendation_strength == "conditional" else "근거 및 충돌 검증"
        gate_tasks = [item.item for item in verification_checkpoints[:3]] or ["핵심 판단 근거를 다시 확인합니다."]
        gate_stage = ExecutionPlanWeek(
            week_label="선행 검증",
            goal=gate_goal,
            tasks=gate_tasks,
            roles=["분석", "검증"],
            deliverables=["검증 결과 정리", "실행안 유지 여부 결정"],
        )
        if execution_plan and execution_plan[0].goal == gate_stage.goal:
            return execution_plan
        return [gate_stage] + list(execution_plan or [])

    def _primary_decision_basis(self, decisions: DecisionArtifacts) -> DecisionBasis | None:
        decision_ids = [str(item.decision_id or "").strip() for item in list(decisions.decision_summary.decisions or []) if str(item.decision_id or "").strip()]
        basis_items = list(decisions.decision_basis or [])
        for decision_id in decision_ids:
            for basis in basis_items:
                if basis.decision_id == decision_id:
                    return basis
        return basis_items[0] if basis_items else None

    def _stage_priority(self, *, index: int, recommendation_strength: str, urgency_score: float) -> tuple[str, str]:
        if recommendation_strength == "blocked":
            return ("P0", "immediate") if index == 0 else ("P1", "next")
        if recommendation_strength == "review_required":
            if index == 0:
                return "P0", "immediate"
            return ("P1", "next") if index == 1 else ("P2", "later")
        if recommendation_strength == "conditional":
            if index == 0:
                return "P0", "immediate"
            if urgency_score >= 0.75 and index == 1:
                return "P0", "immediate"
            return ("P1", "next") if index == 1 else ("P2", "later")
        if index == 0:
            return "P0", "immediate"
        if urgency_score >= 0.8 and index == 1:
            return "P0", "immediate"
        return ("P1", "next") if index == 1 else ("P2", "later")

    def _stage_dependencies(
        self,
        *,
        existing_stages: list[ExecutionStage],
        index: int,
        recommendation_strength: str,
        priority: str,
        phase: str,
        primary_basis: DecisionBasis | None,
    ) -> list[str]:
        if index == 0 or not existing_stages:
            return []
        if recommendation_strength in {"blocked", "review_required", "conditional"}:
            return [existing_stages[-1].stage_id]
        if priority in {"P1", "P2"} and phase in {"next", "later"} and len(existing_stages) >= 2:
            if primary_basis is not None and primary_basis.risk_score < 0.75:
                anchor_stage = existing_stages[0]
                return [anchor_stage.stage_id]
        return [existing_stages[-1].stage_id]

    def _stage_kind(
        self,
        *,
        index: int,
        total: int,
        recommendation_strength: str,
        planning_context: dict[str, Any],
        primary_basis: DecisionBasis | None,
    ) -> str:
        profile = dict(planning_context.get("stage_profile") or {})
        template_stage_kind = str(profile.get("stage_kind") or "implementation_plan").strip() or "implementation_plan"
        if recommendation_strength == "blocked":
            return "blocker_resolution" if index == 0 else "reassessment"
        if recommendation_strength == "review_required":
            return "verification_first" if index == 0 else template_stage_kind
        if recommendation_strength == "conditional":
            return "precondition_check" if index == 0 else template_stage_kind
        if primary_basis is not None and primary_basis.risk_score >= 0.75 and index == total - 1:
            return "monitoring"
        return "execution_start" if index == 0 else template_stage_kind

    def _stage_related_checkpoints(
        self,
        verification_checkpoints: list[VerificationItem],
        *,
        index: int,
        recommendation_strength: str,
    ) -> list[VerificationItem]:
        items = list(verification_checkpoints or [])
        if not items:
            return []
        if index == 0:
            return items[: min(3, len(items))]
        if recommendation_strength in {"blocked", "review_required", "conditional"}:
            return items[min(index, len(items) - 1): min(index + 1, len(items))]
        return items[max(0, min(index - 1, len(items) - 1)): min(index, len(items) - 1) + 1]

    def _stage_prerequisites(
        self,
        *,
        week: ExecutionPlanWeek,
        index: int,
        prior_stage: ExecutionStage | None,
        validation_result: DecisionValidationResult | None,
        recommendation_strength: str,
        primary_basis: DecisionBasis | None,
    ) -> list[str]:
        prerequisites: list[str] = []
        if prior_stage is not None:
            prerequisites.append(f"{prior_stage.title} 단계 완료")
        if index == 0:
            if recommendation_strength == "blocked":
                prerequisites.append(
                    str(getattr(validation_result, "blocking_reason", "") or "차단 사유 해소").strip()
                )
            elif recommendation_strength == "review_required":
                prerequisites.append("충돌 근거와 누락 evidence가 먼저 정리되어야 합니다.")
            elif recommendation_strength == "conditional":
                prerequisites.append("조건부 실행 전제와 제외 조건이 먼저 확인되어야 합니다.")
            elif primary_basis is not None and primary_basis.evidence_strength_score >= 0.65:
                prerequisites.append("상위 판단 근거가 diagnosis evidence_index와 연결되어야 합니다.")
        if primary_basis is not None and primary_basis.maintainability_score >= 0.7 and week.related_contracts:
            prerequisites.append("기존 유지 계약 범위를 먼저 고정해야 합니다.")
        if not prerequisites:
            prerequisites.append("직접 확인된 판단 근거와 유지 계약 범위를 실행 범위에 연결해야 합니다.")
        return self._dedupe_strings(prerequisites)

    def _stage_verification_methods(
        self,
        *,
        week: ExecutionPlanWeek,
        related_checkpoints: list[VerificationItem],
        recommendation_strength: str,
        primary_basis: DecisionBasis | None,
    ) -> list[str]:
        methods: list[str] = []
        for item in related_checkpoints[:2]:
            if str(item.pass_criteria or "").strip():
                methods.append(str(item.pass_criteria).strip())
            elif str(item.reason or "").strip():
                methods.append(str(item.reason).strip())
        if week.related_rules:
            methods.append(f"관련 규칙 확인: {week.related_rules[0]}")
        if week.related_contracts:
            methods.append(f"유지 계약 확인: {week.related_contracts[0]}")
        if primary_basis is not None and primary_basis.risk_score >= 0.75:
            methods.append("핵심 계약 회귀와 rollback 기준을 함께 점검합니다.")
        if primary_basis is not None and primary_basis.maintainability_score >= 0.7:
            methods.append("계약/인터페이스 분리 결과가 기존 계약을 침해하지 않는지 검토합니다.")
        if primary_basis is not None and primary_basis.confidence_score < 0.55:
            methods.append("근거 ID와 source evidence 연결 여부를 다시 확인합니다.")
        if recommendation_strength == "assertive":
            methods.append("적용 후 회귀 시나리오로 품질을 확인합니다.")
        return self._dedupe_strings(methods)

    def _stage_stop_conditions(
        self,
        *,
        index: int,
        validation_result: DecisionValidationResult | None,
        recommendation_strength: str,
        primary_basis: DecisionBasis | None,
    ) -> list[str]:
        stop_conditions: list[str] = []
        if recommendation_strength == "blocked":
            stop_conditions.append(
                str(getattr(validation_result, "blocking_reason", "") or "차단 사유 해소 전에는 다음 단계로 진행하지 않습니다.").strip()
            )
        elif recommendation_strength == "review_required" and index == 0:
            stop_conditions.append("충돌 근거가 정리되기 전에는 적용 결론을 확정하지 않습니다.")
        elif recommendation_strength == "conditional" and index == 0:
            stop_conditions.append("전제 조건이 충족되지 않으면 실행 단계로 넘어가지 않습니다.")
        if primary_basis is not None and primary_basis.risk_score >= 0.75:
            stop_conditions.append("핵심 계약 회귀 실패 시 단계를 중단하고 기존 계약을 유지합니다.")
        if primary_basis is not None and primary_basis.confidence_score < 0.55:
            stop_conditions.append("추가 근거가 확보되지 않으면 실행 후보 상태로만 유지합니다.")
        if not stop_conditions:
            stop_conditions.append("핵심 규칙 또는 유지 계약이 다시 확인되지 않으면 다음 단계로 진행하지 않습니다.")
        return self._dedupe_strings(stop_conditions)

    def _stage_deliverables(
        self,
        *,
        week: ExecutionPlanWeek,
        index: int,
        recommendation_strength: str,
        primary_basis: DecisionBasis | None,
    ) -> list[str]:
        deliverables = list(week.deliverables or [])
        if index == 0 and recommendation_strength in {"conditional", "review_required"}:
            deliverables.append("선행 검증 결과")
        if index == 0 and recommendation_strength == "blocked":
            deliverables.extend(["차단 사유 정리", "추가 근거 확보 목록"])
        if primary_basis is not None and primary_basis.maintainability_score >= 0.7:
            deliverables.append("계약/인터페이스 경계표")
        if primary_basis is not None and primary_basis.risk_score >= 0.75:
            deliverables.append("rollback 체크리스트")
        if primary_basis is not None and primary_basis.confidence_score < 0.55:
            deliverables.append("추가 evidence 확보 목록")
        if primary_basis is not None and primary_basis.urgency_score >= 0.75 and index == 0:
            deliverables.append("즉시 착수 범위와 담당자 합의")
        return self._dedupe_strings(deliverables)

    def _stage_evidence_refs(self, *, week: ExecutionPlanWeek, primary_basis: DecisionBasis | None) -> list[str]:
        refs = list(week.related_rules[:2]) + list(week.related_contracts[:2])
        if primary_basis is not None:
            refs.extend(list(primary_basis.evidence_ids or [])[:2])
        return self._dedupe_strings([str(item or "").strip() for item in refs if str(item or "").strip()])

    def _decision_basis_refs(self, primary_basis: DecisionBasis | None, recommendation_strength: str) -> list[str]:
        if primary_basis is None:
            return [f"recommendation_strength={recommendation_strength}"]
        refs = [
            primary_basis.decision_id,
            f"recommendation_strength={recommendation_strength}",
            f"confidence_score={primary_basis.confidence_score:.2f}",
            f"risk_score={primary_basis.risk_score:.2f}",
            f"urgency_score={primary_basis.urgency_score:.2f}",
            f"maintainability_score={primary_basis.maintainability_score:.2f}",
        ]
        refs.extend(list(primary_basis.scoring_reasons or [])[:3])
        return self._dedupe_strings(refs)

    def _stage_fallback_action(
        self,
        *,
        recommendation_strength: str,
        validation_result: DecisionValidationResult | None,
    ) -> str:
        if recommendation_strength == "blocked":
            return str(getattr(validation_result, "blocking_reason", "") or "차단 사유 해소 후 재판단을 요청합니다.").strip()
        if recommendation_strength == "review_required":
            return "충돌 근거와 추가 evidence를 정리한 뒤 실행 후보를 다시 평가합니다."
        if recommendation_strength == "conditional":
            return "전제 조건이 충족되지 않으면 실행을 보류하고 대안을 비교합니다."
        return "회귀 실패 시 유지 계약 기준안으로 되돌리고 범위를 축소합니다."

    def _enrich_verification_item(
        self,
        item: VerificationItem,
        *,
        index: int,
        recommendation_strength: str,
        primary_basis: DecisionBasis | None,
        decision_ids: list[str],
        conflict_ids: list[str],
        planning_context: dict[str, Any],
    ) -> VerificationItem:
        checkpoint_kind = str(item.checkpoint_kind or "").strip() or self._checkpoint_kind(item)
        target = str(item.target or "").strip() or str(dict(planning_context.get("stage_profile") or {}).get("domain_focus") or item.item).strip()
        required_evidence = list(item.required_evidence or [])
        if not required_evidence and list(item.evidence or []):
            required_evidence = [
                f"{str(getattr(evidence, 'asset_name', '') or '').strip()}:{str(getattr(evidence, 'locator', '') or '').strip()}".strip(":")
                for evidence in list(item.evidence or [])[:3]
                if str(getattr(evidence, "asset_name", "") or "").strip() or str(getattr(evidence, "locator", "") or "").strip()
            ]
        if not required_evidence and primary_basis is not None and primary_basis.evidence_ids:
            required_evidence = list(primary_basis.evidence_ids[:2])
        pass_criteria = str(item.pass_criteria or "").strip() or self._default_checkpoint_pass_criteria(target, checkpoint_kind)
        failure_action = str(item.failure_action or "").strip() or self._default_checkpoint_failure_action(
            checkpoint_kind=checkpoint_kind,
            recommendation_strength=recommendation_strength,
        )
        priority = str(item.priority or "").strip() or self._checkpoint_priority(index, recommendation_strength)
        related_conflict_ids = list(item.related_conflict_ids or [])
        if not related_conflict_ids and checkpoint_kind in {"conflict_resolution", "blocker_resolution"}:
            related_conflict_ids = list(conflict_ids)
        related_decision_ids = list(item.related_decision_ids or []) or list(decision_ids)
        return item.model_copy(
            update={
                "target": target,
                "required_evidence": self._dedupe_strings(required_evidence),
                "pass_criteria": pass_criteria,
                "failure_action": failure_action,
                "priority": priority,
                "checkpoint_kind": checkpoint_kind,
                "related_decision_ids": self._dedupe_strings(related_decision_ids),
                "related_conflict_ids": self._dedupe_strings(related_conflict_ids),
            }
        )

    def _checkpoint_kind(self, item: VerificationItem) -> str:
        text = f"{str(item.item or '')} {str(item.reason or '')}".lower()
        if "충돌" in text or "상충" in text:
            return "conflict_resolution"
        if "근거" in text or "evidence" in text:
            return "evidence_gathering"
        if "차단" in text:
            return "blocker_resolution"
        if "조건" in text or "전제" in text:
            return "precondition_check"
        if "권한" in text or "승인" in text:
            return "access_control_confirmation"
        if "상태" in text:
            return "state_transition_confirmation"
        if "조회" in text or "필터" in text:
            return "query_filter_confirmation"
        if "금액" in text or "한도" in text:
            return "threshold_confirmation"
        return "rule_validation"

    def _default_checkpoint_pass_criteria(self, target: str, checkpoint_kind: str) -> str:
        if checkpoint_kind == "conflict_resolution":
            return "상충 판단 후보가 하나의 조건부 판단 또는 우선안으로 정리됩니다."
        if checkpoint_kind == "evidence_gathering":
            return "상위 판단을 지지하는 source evidence가 diagnosis evidence_index와 다시 연결됩니다."
        if checkpoint_kind == "blocker_resolution":
            return "차단 사유와 누락 근거가 해소되어 재판단 가능한 상태가 됩니다."
        if checkpoint_kind == "precondition_check":
            return "조건부 실행 전제와 적용 제외 조건이 모두 확인됩니다."
        return f"{target} 기준이 직접 evidence와 다시 연결됩니다."

    def _default_checkpoint_failure_action(self, *, checkpoint_kind: str, recommendation_strength: str) -> str:
        if checkpoint_kind == "blocker_resolution":
            return "차단 사유 해소 전에는 실행 계획을 확정하지 않고 재판단을 요청합니다."
        if checkpoint_kind == "conflict_resolution":
            return "충돌 해소 전에는 실행 후보 상태로만 유지합니다."
        if checkpoint_kind == "evidence_gathering":
            return "근거 확보 전에는 추천 강도를 올리지 않고 추가 확인 상태를 유지합니다."
        if checkpoint_kind == "precondition_check":
            return "전제 미충족 시 실행을 보류하고 대안을 비교합니다."
        if recommendation_strength in {"review_required", "blocked"}:
            return "추가 확인 전에는 검토 후보 또는 차단 상태를 유지합니다."
        return "검증 실패 시 유지 계약 기준안으로 되돌리고 범위를 축소합니다."

    def _checkpoint_priority(self, index: int, recommendation_strength: str) -> str:
        if index == 0:
            return "P0"
        if recommendation_strength in {"blocked", "review_required"} and index == 1:
            return "P0"
        return "P1" if index <= 2 else "P2"

    def _option_execution_strategies(
        self,
        *,
        design_options,
        recommended_option,
        execution_stages: list[ExecutionStage],
        verification_checkpoints: list[VerificationItem],
        validation_result: DecisionValidationResult | None,
        recommendation_strength: str,
        primary_basis: DecisionBasis | None,
        planning_context: dict[str, Any],
        decisions: DecisionArtifacts,
        risks: list[str],
    ) -> list[OptionExecutionStrategy]:
        options = list(design_options or [])
        primary_name = str(getattr(recommended_option, "name", "") or "").strip()
        if not options and recommended_option is not None:
            options = [
                type("FallbackOption", (), {
                    "name": str(getattr(recommended_option, "name", "") or "권장안"),
                    "structure_summary": str(getattr(recommended_option, "structure_summary", "") or ""),
                    "selection_reason": str(getattr(recommended_option, "selection_reason", "") or ""),
                    "advantages": list(getattr(recommended_option, "expected_outcomes", []) or []),
                    "risks": list(risks[:2]),
                    "recommended": True,
                })()
            ]
        if not options:
            options = [
                type("FallbackOption", (), {
                    "name": "검토 전략",
                    "structure_summary": str(dict(planning_context.get("stage_profile") or {}).get("domain_focus") or "직접 확인된 구조 근거 기반 실행 전략"),
                    "selection_reason": "직접 확인된 구조 근거를 기준으로 가장 보수적인 실행 전략을 유지합니다.",
                    "advantages": ["직접 확인된 근거와 유지 계약을 기준으로 판단합니다."],
                    "risks": list(risks[:2]),
                    "recommended": recommendation_strength == "assertive",
                })()
            ]

        first_stage = execution_stages[0] if execution_stages else None
        first_checkpoint = verification_checkpoints[0] if verification_checkpoints else None
        decision_basis_refs = self._decision_basis_refs(primary_basis, recommendation_strength)
        missing_evidence = list(getattr(validation_result, "missing_evidence", []) or [])
        conflict_texts = [
            str(getattr(item, "summary", "") or "").strip()
            for item in list(getattr(validation_result, "conflicts", []) or [])
            if str(getattr(item, "summary", "") or "").strip()
        ]
        shared_required_evidence = self._dedupe_strings(
            missing_evidence
            + list(getattr(first_checkpoint, "required_evidence", []) or [])[:2]
            + list(getattr(primary_basis, "evidence_ids", []) or [])[:2]
        )

        strategies: list[OptionExecutionStrategy] = []
        for index, option in enumerate(options[:3]):
            option_name = str(getattr(option, "name", "") or "").strip() or f"옵션 {index + 1}"
            is_primary = bool(getattr(option, "recommended", False)) or (primary_name and option_name == primary_name) or (index == 0 and not primary_name)
            option_strength = recommendation_strength
            if recommendation_strength == "assertive" and not is_primary:
                option_strength = "conditional"
            first_action = self._option_first_action(
                option_name=option_name,
                is_primary=is_primary,
                recommendation_strength=option_strength,
                first_stage=first_stage,
                first_checkpoint=first_checkpoint,
            )
            expected_deliverables = self._option_expected_deliverables(
                option=option,
                first_stage=first_stage,
                recommendation_strength=option_strength,
            )
            key_risks = self._dedupe_strings(
                list(getattr(option, "risks", []) or [])[:2]
                + list(risks[:2])
                + conflict_texts[:1]
            )
            strategies.append(
                OptionExecutionStrategy(
                    option_label=f"option_{index + 1}",
                    option_title=option_name,
                    primary=is_primary,
                    recommendation_strength=option_strength,
                    when_to_choose=self._option_when_to_choose(
                        option=option,
                        is_primary=is_primary,
                        recommendation_strength=option_strength,
                    ),
                    first_action=first_action,
                    required_evidence=self._dedupe_strings(
                        shared_required_evidence
                        or list(getattr(first_stage, "evidence_refs", []) or [])[:2]
                    ),
                    key_risks=key_risks,
                    fallback_or_exit_condition=self._option_exit_condition(
                        recommendation_strength=option_strength,
                        validation_result=validation_result,
                        key_risks=key_risks,
                    ),
                    expected_deliverables=expected_deliverables,
                    related_decision_basis_refs=decision_basis_refs,
                )
            )
        return strategies

    def _option_first_action(
        self,
        *,
        option_name: str,
        is_primary: bool,
        recommendation_strength: str,
        first_stage: ExecutionStage | None,
        first_checkpoint: VerificationItem | None,
    ) -> str:
        if recommendation_strength == "blocked":
            return str(getattr(first_checkpoint, "item", "") or "차단 사유와 누락 근거를 먼저 정리합니다.").strip()
        if recommendation_strength == "review_required":
            return str(getattr(first_checkpoint, "item", "") or "충돌 근거와 누락 evidence를 먼저 비교 검증합니다.").strip()
        if recommendation_strength == "conditional":
            return str(getattr(first_checkpoint, "item", "") or "선행 조건과 적용 제외 조건을 먼저 확인합니다.").strip()
        if is_primary and first_stage is not None and list(first_stage.tasks or []):
            return str(first_stage.tasks[0] or "").strip() or str(first_stage.title or "").strip()
        return f"{option_name} 기준의 적용 범위와 유지 계약 영향을 먼저 비교합니다."

    def _option_when_to_choose(self, *, option, is_primary: bool, recommendation_strength: str) -> str:
        if recommendation_strength == "blocked":
            return "차단 사유와 누락 근거를 해소한 뒤 다시 판단할 때 선택합니다."
        if recommendation_strength == "review_required":
            return "충돌하는 판단 근거를 비교하면서 실행 후보를 유지할 때 선택합니다."
        if recommendation_strength == "conditional":
            return "선행 조건이 충족되는지 확인한 뒤 적용 여부를 결정할 때 선택합니다."
        selection_reason = str(getattr(option, "selection_reason", "") or "").strip()
        if selection_reason:
            return selection_reason
        if is_primary:
            return "직접 확인된 규칙과 유지 계약을 기준으로 바로 착수 가능한 경우 선택합니다."
        return "대안 비교가 필요하거나 적용 범위를 축소해야 할 때 유지합니다."

    def _option_exit_condition(
        self,
        *,
        recommendation_strength: str,
        validation_result: DecisionValidationResult | None,
        key_risks: list[str],
    ) -> str:
        if recommendation_strength == "blocked":
            return str(getattr(validation_result, "blocking_reason", "") or "차단 사유 해소 전에는 실행으로 전환하지 않습니다.").strip()
        if recommendation_strength == "review_required":
            return "충돌 근거가 해소되지 않으면 실행 후보 상태로만 유지합니다."
        if recommendation_strength == "conditional":
            return "선행 조건이 충족되지 않으면 보류하고 대안을 비교합니다."
        if key_risks:
            return f"{key_risks[0]}가 현실화되면 범위를 축소하고 유지 계약 기준안으로 되돌립니다."
        return "핵심 계약 회귀가 확인되면 적용 범위를 축소합니다."

    def _option_expected_deliverables(
        self,
        *,
        option,
        first_stage: ExecutionStage | None,
        recommendation_strength: str,
    ) -> list[str]:
        deliverables = list(getattr(first_stage, "deliverables", []) or [])[:2] if first_stage is not None else []
        if not deliverables:
            deliverables = list(getattr(option, "advantages", []) or [])[:2]
        if not deliverables:
            deliverables = [str(getattr(option, "structure_summary", "") or "구조 적용 기준 초안").strip() or "구조 적용 기준 초안"]
        if recommendation_strength in {"review_required", "blocked"} and "선행 검증 결과" not in deliverables:
            deliverables.insert(0, "선행 검증 결과")
        return self._dedupe_strings(deliverables)

    def _schedule_hints(
        self,
        *,
        execution_stages: list[ExecutionStage],
        recommendation_strength: str,
        validation_result: DecisionValidationResult | None,
        primary_basis: DecisionBasis | None,
    ) -> list[ExecutionScheduleHint]:
        stage_map = {stage.stage_id: stage for stage in execution_stages}
        hints: list[ExecutionScheduleHint] = []
        for index, stage in enumerate(execution_stages):
            depends_on = list(stage.depends_on or [])
            can_parallelize_with = self._parallelizable_stage_ids(
                execution_stages=execution_stages,
                stage=stage,
            )
            blocking_conditions = self._dedupe_strings(
                list(stage.stop_conditions or [])[:2]
                or list(stage.prerequisites or [])[:1]
                or ([str(getattr(validation_result, "blocking_reason", "") or "").strip()] if recommendation_strength == "blocked" else [])
            )
            hints.append(
                ExecutionScheduleHint(
                    stage_id=stage.stage_id,
                    stage_title=stage.title,
                    sequence_index=index,
                    priority=str(stage.priority or "").strip(),
                    phase=str(stage.phase or "").strip(),
                    depends_on=depends_on,
                    can_parallelize_with=can_parallelize_with,
                    blocking_conditions=blocking_conditions,
                    suggested_order_reason=self._schedule_order_reason(
                        stage=stage,
                        index=index,
                        recommendation_strength=recommendation_strength,
                        primary_basis=primary_basis,
                        stage_map=stage_map,
                    ),
                    stage_kind=str(stage.stage_kind or "").strip(),
                )
            )
        return hints

    def _parallelizable_stage_ids(
        self,
        *,
        execution_stages: list[ExecutionStage],
        stage: ExecutionStage,
    ) -> list[str]:
        if str(stage.priority or "").strip() == "P0":
            return []
        if str(stage.stage_kind or "").strip() in {"verification_first", "precondition_check", "blocker_resolution", "execution_start"}:
            return []
        peers: list[str] = []
        for candidate in execution_stages:
            if candidate.stage_id == stage.stage_id:
                continue
            if str(candidate.phase or "").strip() != str(stage.phase or "").strip():
                continue
            if list(candidate.depends_on or []) != list(stage.depends_on or []):
                continue
            if str(candidate.priority or "").strip() == "P0":
                continue
            if str(candidate.stage_kind or "").strip() in {"verification_first", "precondition_check", "blocker_resolution", "execution_start"}:
                continue
            peers.append(candidate.stage_id)
        return self._dedupe_strings(peers)

    def _schedule_order_reason(
        self,
        *,
        stage: ExecutionStage,
        index: int,
        recommendation_strength: str,
        primary_basis: DecisionBasis | None,
        stage_map: dict[str, ExecutionStage],
    ) -> str:
        stage_kind = str(stage.stage_kind or "").strip()
        if index == 0 and stage_kind == "blocker_resolution":
            return "차단 사유 해소가 실행보다 우선이므로 가장 먼저 배치합니다."
        if index == 0 and stage_kind == "verification_first":
            return "충돌과 근거 검증이 실행보다 우선이므로 가장 먼저 배치합니다."
        if index == 0 and stage_kind == "precondition_check":
            return "조건 확인이 실행보다 우선이므로 가장 먼저 배치합니다."
        if index == 0 and stage_kind == "execution_start":
            return "직접 확인된 근거가 충분해 실행 착수 단계를 먼저 배치합니다."
        if stage_kind == "monitoring":
            return "고위험 판단이므로 적용 이후 monitoring/rollback 확인 단계를 둡니다."
        if list(stage.depends_on or []):
            dependency_titles = [
                str(getattr(stage_map.get(dep_id), "title", dep_id) or dep_id).strip()
                for dep_id in list(stage.depends_on or [])[:2]
            ]
            return f"{', '.join(dependency_titles)} 완료 후 진행해야 하므로 후속 단계에 배치합니다."
        if recommendation_strength in {"blocked", "review_required"}:
            return "검증 우선 모드이므로 실행 후보를 후순위로 둡니다."
        if primary_basis is not None and primary_basis.urgency_score >= 0.8 and str(stage.phase or "").strip() == "immediate":
            return "긴급도가 높아 immediate 단계로 당겨 배치합니다."
        return "우선순위와 phase 기준으로 순서를 고정합니다."

    def _dedupe_strings(self, items: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for item in items:
            key = str(item or "").strip()
            if not key:
                continue
            normalized = key.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            output.append(key)
        return output
