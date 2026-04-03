from __future__ import annotations

import re
from typing import Any

from mellow_link.modules.rebuild_assistant.schemas import StructuredRebuildResult

from .schemas import (
    DecisionArtifacts,
    DiagnosisArtifacts,
    ImprovementArtifacts,
    StructureAnalysisResult,
    StructuredRefactoringResult,
)


class ResultPackager:
    def package(
        self,
        prepared: Any,
        structure: StructureAnalysisResult,
        diagnosis: DiagnosisArtifacts,
        decisions: DecisionArtifacts,
        improvement: ImprovementArtifacts,
        legacy_service: Any,
    ) -> StructuredRebuildResult:
        confidence = legacy_service.estimate_confidence(prepared)
        core_business_rules = legacy_service._align_core_business_rules_for_narrative(
            prepared,
            diagnosis.grounded_business_rules,
            diagnosis.core_business_rules,
        )
        retained_contracts = legacy_service._align_retained_contracts_for_narrative(
            prepared,
            diagnosis.retained_contracts,
        )
        feature_slices = []
        for item in structure.structure_snapshot.feature_slices:
            if item.business_rules:
                feature_slices.append(item)
            else:
                feature_slices.append(item.model_copy(update={"business_rules": core_business_rules[:2]}))
        authoritative = StructuredRefactoringResult(
            structure_snapshot=structure.structure_snapshot.model_copy(update={"feature_slices": feature_slices}),
            diagnosis_report=diagnosis.diagnosis_report,
            decision_summary=decisions.decision_summary,
            improvement_plan_bundle=improvement.improvement_plan_bundle,
            appendix={"evidence_index": [item.model_dump() for item in diagnosis.evidence_index]},
        )
        result = StructuredRebuildResult(
            primary_judgment=decisions.primary_judgment,
            primary_judgment_reason=decisions.primary_judgment_reason,
            pattern_candidates=decisions.pattern_candidates,
            one_line_conclusion=legacy_service._build_conclusion_with_templates(
                prepared,
                confidence,
                diagnosis.grounded_business_rules,
                decisions.applied_templates,
            ),
            core_business_rules=core_business_rules,
            executive_summary_v2=legacy_service.build_executive_summary_v2(
                prepared,
                diagnosis.grounded_business_rules,
                improvement.recommended_option,
                decisions.applied_templates,
            ),
            grounded_business_rules=diagnosis.grounded_business_rules,
            decision_items=decisions.decision_items,
            retained_contracts=retained_contracts,
            priority_split_items=improvement.priority_split_items,
            verification_checkpoints=improvement.verification_checkpoints,
            design_options=improvement.design_options,
            recommended_option=improvement.recommended_option,
            execution_plan=improvement.execution_plan,
            analysis_summary=diagnosis.analysis_summary,
            rebuild_strategy=improvement.rebuild_strategy,
            layer_reconstruction=improvement.layer_reconstruction,
            recomposition_draft=improvement.recomposition_draft,
            risks=improvement.risks,
            extracted_rules=diagnosis.extracted_rules,
            recommended_directions=improvement.recommended_directions,
            confidence=confidence,
            missing_context=[item.required_material for item in diagnosis.missing_context_details],
            missing_context_details=diagnosis.missing_context_details,
            extensions=legacy_service._build_extensions(prepared),
            structure_snapshot=authoritative.structure_snapshot.model_dump(),
            diagnosis_report=authoritative.diagnosis_report.model_dump(),
            decision_summary=authoritative.decision_summary.model_dump(),
            improvement_plan_bundle=authoritative.improvement_plan_bundle.model_dump(),
            appendix=authoritative.appendix,
        )
        result = self._soften_supporting_sentences(result)
        result = legacy_service.attach_report_purpose(
            result,
            user_question=prepared.goal,
            narrative_judgment=decisions.selected_narrative_judgment,
        )
        result = legacy_service._apply_accounting_top_narrative(prepared, result)
        result = legacy_service._apply_accounting_bottom_sections(prepared, result)
        return legacy_service._sanitize_structured_result(result)

    def _soften_supporting_sentences(self, result: StructuredRebuildResult) -> StructuredRebuildResult:
        top_decision_rationale = ""
        decisions = result.decision_summary.get("decisions", []) if isinstance(result.decision_summary, dict) else []
        if decisions:
            top_decision_rationale = str(decisions[0].get("rationale", "") or "")
        decision_items = [
            item.model_copy(update={"rationale": self._soften_sentence(item.rationale)})
            for item in result.decision_items
        ]
        design_options = [
            item.model_copy(update={"selection_reason": self._soften_sentence(item.selection_reason)})
            for item in result.design_options
        ]
        recommended_option = result.recommended_option
        if recommended_option is not None:
            recommended_option = recommended_option.model_copy(
                update={
                    "selection_reason": self._soften_sentence(recommended_option.selection_reason),
                    "expected_outcomes": [self._soften_sentence(text) for text in recommended_option.expected_outcomes],
                }
            )
        executive_summary = [
            line if index == 0 else self._soften_sentence(line)
            for index, line in enumerate(result.executive_summary_v2)
        ]
        return result.model_copy(
            update={
                "primary_judgment_reason": self._soften_sentence(result.primary_judgment_reason or top_decision_rationale),
                "executive_summary_v2": executive_summary,
                "decision_items": decision_items,
                "design_options": design_options,
                "recommended_option": recommended_option,
            }
        )

    def _soften_sentence(self, text: str) -> str:
        softened = str(text or "").strip()
        if not softened:
            return softened
        replacements = (
            (r"확정하는 것이 필요합니다\.?", "우선 기준안으로 두는 편이 적절합니다."),
            (r"확정해야 합니다\.?", "우선 기준안으로 두는 편이 적절합니다."),
            (r"완료해야 합니다\.?", "먼저 정리하는 편이 적절합니다."),
            (r"고정해야 합니다\.?", "먼저 정리하는 편이 안전합니다."),
            (r"고정해야 하므로", "먼저 정리하는 편이 안전하므로"),
            (r"우선 적용해야 합니다\.?", "우선 적용하는 편이 적절합니다."),
            (r"적용해야 합니다\.?", "적용하는 편이 적절합니다."),
            (r"후속 검증하는 것이 필요합니다\.?", "후속 검증 대상으로 두는 편이 적절합니다."),
            (r"후속 마이그레이션 검토가 필요합니다\.?", "후속 마이그레이션 검토를 함께 두는 편이 적절합니다."),
        )
        for pattern, replacement in replacements:
            softened = re.sub(pattern, replacement, softened)
        return softened
