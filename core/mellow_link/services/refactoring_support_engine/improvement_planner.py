from __future__ import annotations

from typing import Any

from .planning_synthesizer import PlanningSynthesizer
from .schemas import (
    DecisionArtifacts,
    DiagnosisArtifacts,
    ExecutionStage,
    ImprovementArtifacts,
    ImprovementPlanBundle,
    RiskCheckpoint,
    StructureAnalysisResult,
    make_stable_id,
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
    ) -> ImprovementArtifacts:
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

        execution_stages = self._execution_stages(execution_plan, decisions)
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
        )

    def _execution_stages(self, execution_plan, decisions: DecisionArtifacts) -> list[ExecutionStage]:
        records = decisions.decision_summary.decisions
        default_decision_ids = [item.decision_id for item in records[:2]] or [make_stable_id("DEC", "fallback")]
        verification_ids = [make_stable_id("VERIFY", item.week_label, item.goal) for item in execution_plan[:1]]
        stages: list[ExecutionStage] = []
        for index, week in enumerate(execution_plan):
            stage_decision_ids = [item.decision_id for item in records[index:index + 2]] or default_decision_ids[:1]
            risk_ids = [make_stable_id("RISK", week.week_label, task) for task in week.tasks[:2]]
            stages.append(
                ExecutionStage(
                    stage_id=make_stable_id("STAGE", week.week_label, week.goal, week.tasks),
                    title=week.goal,
                    tasks=list(week.tasks),
                    decision_ids=stage_decision_ids,
                    verification_checkpoint_ids=verification_ids[:1],
                    risk_ids=risk_ids,
                    depends_on=[stages[-1].stage_id] if stages else [],
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
