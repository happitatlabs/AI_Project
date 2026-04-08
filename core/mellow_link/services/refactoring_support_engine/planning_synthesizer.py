from __future__ import annotations

from typing import Any

from mellow_link.modules.rebuild_assistant.schemas import (
    AppliedJudgmentTemplate,
    DesignOption,
    ExecutionPlanWeek,
    GroundedBusinessRule,
    PrioritySplitItem,
    RecommendedOption,
    RetainedContract,
    VerificationItem,
)

from .decision_catalog import get_judgment_template_spec
from .schemas import DecisionArtifacts
from .template_support import TemplateSupport


class PlanningSynthesizer:
    def __init__(self, helper: Any | None = None) -> None:
        self.helper = helper or TemplateSupport()

    def _require_decisions(self, decisions: DecisionArtifacts | None) -> DecisionArtifacts:
        if decisions is None:
            raise ValueError("DecisionArtifacts are required for planning.")
        return decisions

    def _template_source(self, decisions: DecisionArtifacts) -> list[AppliedJudgmentTemplate]:
        applied_templates = list(decisions.applied_templates or [])
        if applied_templates:
            return applied_templates
        template_id = (decisions.primary_judgment or decisions.selected_narrative_judgment or "").strip()
        if not template_id:
            return []
        spec = get_judgment_template_spec(template_id)
        return [
            AppliedJudgmentTemplate(
                template_id=template_id,
                score=1.0,
                matched_signal_types=[],
                matched_rule_titles=[],
                matched_contract_items=[],
                core_questions=list(spec.core_questions),
            )
        ]

    def _apply_decision_anchor(
        self,
        prepared: Any,
        grounded_rules: list[GroundedBusinessRule],
        decisions: DecisionArtifacts,
    ) -> list[AppliedJudgmentTemplate]:
        prepared.selected_primary_judgment = decisions.primary_judgment or (prepared.selected_primary_judgment or "")
        prepared.selected_primary_judgment_reason = decisions.primary_judgment_reason or (prepared.selected_primary_judgment_reason or "")
        prepared.selected_narrative_judgment = decisions.selected_narrative_judgment or decisions.primary_judgment or (prepared.selected_narrative_judgment or "")
        prepared.pattern_candidates = list(decisions.pattern_candidates or [])
        applied_templates = self._template_source(decisions)
        if not applied_templates:
            raise ValueError("DecisionArtifacts.applied_templates is required for planning.")
        return self.helper._ordered_templates_for_generation(prepared, applied_templates, grounded_rules)

    def build_priority_split_items(
        self,
        prepared: Any,
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
        decisions: DecisionArtifacts | None,
    ) -> list[PrioritySplitItem]:
        anchored = self._apply_decision_anchor(prepared, grounded_rules, self._require_decisions(decisions))
        return self.helper._build_template_priority_split_items(prepared, grounded_rules, retained_contracts, anchored)

    def build_design_options(
        self,
        prepared: Any,
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
        decisions: DecisionArtifacts | None,
    ) -> list[DesignOption]:
        anchored = self._apply_decision_anchor(prepared, grounded_rules, self._require_decisions(decisions))
        return self.helper._build_template_design_options(prepared, grounded_rules, retained_contracts, anchored)

    def apply_recommended_selection_reason(
        self,
        prepared: Any,
        options: list[DesignOption],
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
        decisions: DecisionArtifacts | None,
    ) -> list[DesignOption]:
        anchored = self._apply_decision_anchor(prepared, grounded_rules, self._require_decisions(decisions))
        recommended = next((item for item in options if item.recommended), None)
        if not recommended:
            return options
        raw_templates = self._template_source(self._require_decisions(decisions))
        reason = self.helper._build_recommended_selection_reason(
            prepared,
            grounded_rules,
            retained_contracts,
            recommended,
            raw_templates,
        )
        updated: list[DesignOption] = []
        for item in options:
            if item.recommended:
                updated.append(item.model_copy(update={"selection_reason": reason}))
            else:
                updated.append(
                    item.model_copy(
                        update={
                            "selection_reason": item.selection_reason
                            or self.helper._build_non_recommended_selection_reason(item.name, raw_templates)
                        }
                    )
                )
        return updated

    def pick_recommended_option(
        self,
        options: list[DesignOption],
        prepared: Any,
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
        decisions: DecisionArtifacts | None,
    ) -> RecommendedOption | None:
        self._apply_decision_anchor(prepared, grounded_rules, self._require_decisions(decisions))
        recommended = next((item for item in options if item.recommended), None)
        if not recommended:
            return None
        raw_templates = self._template_source(self._require_decisions(decisions))
        selection_reason = self.helper._build_recommended_selection_reason(
            prepared,
            grounded_rules,
            retained_contracts,
            recommended,
            raw_templates,
        )
        return RecommendedOption(
            name=recommended.name,
            structure_summary=recommended.structure_summary,
            selection_reason=selection_reason,
            expected_outcomes=["핵심 규칙과 정책 분리를 우선 완료해야 합니다.", "기존 데이터 계약을 유지한 상태에서 단계적 전환 순서를 고정해야 합니다."],
        )

    def build_verification_checkpoints(
        self,
        prepared: Any,
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
        decisions: DecisionArtifacts | None,
    ) -> list[VerificationItem]:
        anchored = self._apply_decision_anchor(prepared, grounded_rules, self._require_decisions(decisions))
        retained_keys = {self.helper._normalize_key(item.item) for item in retained_contracts}
        items: list[VerificationItem] = []
        primary_template = anchored[0] if anchored else None
        workflow_primary = bool(primary_template and primary_template.template_id == "workflow")
        access_control_primary = self.helper._should_enrich_access_control(
            prepared,
            grounded_rules,
            applied_templates=anchored,
        )
        for rule in grounded_rules:
            if not rule.needs_verification:
                continue
            items.append(
                VerificationItem(
                    item=f"{rule.title} 운영 기준을 확인하는 것이 필요합니다.",
                    reason=rule.confidence_reason or "직접 확인 가능한 운영 자산이 부족합니다.",
                    evidence=rule.evidence,
                )
            )
        output: list[VerificationItem] = []
        for item in items:
            if workflow_primary and any(
                token in item.item for token in ("권한 위임 가능 여부", "승인 요청 및 처리 흐름", "상태 전이와 액션 노출 조건")
            ):
                continue
            if access_control_primary and any(
                token in item.item for token in ("권한 위임 가능 여부", "승인 요청 및 처리 흐름")
            ):
                continue
            if self.helper._normalize_key(item.item) in retained_keys:
                continue
            output.append(item)
        for spec in self.helper._template_retained_contract_specs(prepared, grounded_rules):
            contract_key = self.helper._normalize_key(spec["item"])
            if contract_key in retained_keys:
                continue
            evidence = self.helper._collect_evidence_refs(prepared, tuple(spec["keywords"]), ("source", "ui", "sql", "schema", "constraint"))
            if evidence:
                continue
            output.append(
                VerificationItem(
                    item=f"{spec['item']} 운영 기준을 추가 자산으로 확인하는 것이 필요합니다.",
                    reason="직접 확인 가능한 상태값, 컬럼명 또는 규칙 조건 근거가 부족해 유지 계약으로 확정할 수 없습니다.",
                    evidence=[],
                )
            )
        if workflow_primary:
            workflow_defaults = [
                (
                    "대리 승인 범위와 병렬 승인 가능 조건을 확인하는 것이 필요합니다.",
                    "승인 트리거와 승인 주체는 직접 확인되었지만 대리 승인 범위와 병렬 승인 조건은 추가 확인이 필요합니다.",
                ),
                (
                    "승인 단계별 통지와 후속 처리 절차를 확인하는 것이 필요합니다.",
                    "승인 단계 구조는 보이지만 단계별 통지와 후속 처리 절차는 현재 자산만으로 모두 확정할 수 없습니다.",
                ),
            ]
            for item_text, reason in workflow_defaults:
                if any(self.helper._normalize_key(existing.item) == self.helper._normalize_key(item_text) for existing in output):
                    continue
                output.append(VerificationItem(item=item_text, reason=reason, evidence=[]))
        elif access_control_primary:
            access_defaults = [
                (
                    "권한 위임 세부 범위를 확인하는 것이 필요합니다.",
                    "권한 위임 가능 여부는 보이지만 위임 범위와 승인 한계는 현재 자산만으로 확정할 수 없습니다.",
                ),
                (
                    "예외 승인 조건 상세를 확인하는 것이 필요합니다.",
                    "예외 승인 경로 후보는 보이지만 어떤 조건에서 우회 승인되는지는 현재 자산만으로 확정할 수 없습니다.",
                ),
                (
                    "처리 후 통지와 후속 처리 절차를 확인하는 것이 필요합니다.",
                    "승인 요청 이후 통지 대상과 후속 처리 책임은 현재 자산만으로 모두 확인되지 않았습니다.",
                ),
            ]
            for item_text, reason in access_defaults:
                if any(self.helper._normalize_key(existing.item) == self.helper._normalize_key(item_text) for existing in output):
                    continue
                output.append(VerificationItem(item=item_text, reason=reason, evidence=[]))
        if not output:
            fallback_template = self.helper._fallback_verification_template(prepared, grounded_rules)
            for template_id in ([fallback_template] if fallback_template else []):
                if template_id == "workflow":
                    output.append(
                        VerificationItem(
                            item="대리 승인 범위와 병렬 승인 가능 조건을 확인하는 것이 필요합니다.",
                            reason="승인 트리거와 승인 주체는 직접 확인되었지만 대리 승인 범위와 병렬 승인 조건은 추가 확인이 필요합니다.",
                            evidence=[],
                        )
                    )
                elif template_id == "state_transition":
                    output.append(
                        VerificationItem(
                            item="상태 전이 이후 후속 승인 또는 운영 처리 절차를 확인하는 것이 필요합니다.",
                            reason="상태 전이 규칙은 직접 확인되었지만 후속 운영 절차는 현재 자산에서 모두 확인되지 않았습니다.",
                            evidence=[],
                        )
                    )
                elif template_id == "access_control":
                    output.append(
                        VerificationItem(
                            item="권한 규칙 적용 이후 외부 승인 또는 통지 절차를 확인하는 것이 필요합니다.",
                            reason="승인 주체는 직접 확인되었지만 후속 운영 절차는 추가 확인이 필요합니다.",
                            evidence=[],
                        )
                    )
                elif template_id == "validation":
                    output.append(
                        VerificationItem(
                            item="검증 실패 이후 예외 처리와 운영 메시지 기준을 확인하는 것이 필요합니다.",
                            reason="차단 조건은 직접 확인되었지만 운영 메시지와 예외 처리 기준은 추가 확인이 필요합니다.",
                            evidence=[],
                        )
                    )
                elif template_id == "amount_threshold":
                    output.append(
                        VerificationItem(
                            item="한도 초과 이후 후속 처리 기준과 사용자 안내 기준을 확인하는 것이 필요합니다.",
                            reason="금액 구간과 한도 경계는 직접 확인되었지만 한도 초과 이후 후속 처리 기준은 추가 확인이 필요합니다.",
                            evidence=[],
                        )
                    )
        return self.helper._dedupe_by_normalized_text(output, attr="item")

    def build_execution_plan(
        self,
        prepared: Any,
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
        recommended_option: RecommendedOption | None,
        decisions: DecisionArtifacts | None,
    ) -> list[ExecutionPlanWeek]:
        anchored = self._apply_decision_anchor(prepared, grounded_rules, self._require_decisions(decisions))
        return self.helper._build_template_execution_plan(prepared, grounded_rules, retained_contracts, recommended_option, anchored)

    def infer_target_architecture(self, prepared: Any) -> list[str]:
        return self.helper.infer_target_architecture(prepared)

    def build_layer_reconstruction(self, prepared: Any):
        return self.helper.build_layer_reconstruction(prepared)

    def build_recomposition_draft(self, prepared: Any, decisions: DecisionArtifacts | None):
        anchored = self._template_source(self._require_decisions(decisions))
        return self.helper.build_recomposition_draft(prepared, anchored)

    def build_risks(
        self,
        prepared: Any,
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
        decisions: DecisionArtifacts | None,
    ) -> list[str]:
        anchored = self._apply_decision_anchor(prepared, grounded_rules, self._require_decisions(decisions))
        return self.helper._build_template_risks(prepared, grounded_rules, retained_contracts, anchored)

    def build_recommended_directions(self, prepared: Any) -> list[str]:
        return self.helper.build_recommended_directions(prepared)
