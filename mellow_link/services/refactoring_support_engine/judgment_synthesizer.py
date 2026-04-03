from __future__ import annotations

from typing import Any

from mellow_link.modules.rebuild_assistant.schemas import (
    AppliedJudgmentTemplate,
    DecisionItem,
    GroundedBusinessRule,
    PatternCandidate,
    RetainedContract,
)

from .decision_catalog import get_judgment_template_specs


class JudgmentSynthesizer:
    def __init__(self, helper: Any) -> None:
        self.helper = helper

    def build_applied_templates(
        self,
        prepared: Any,
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
    ) -> list[AppliedJudgmentTemplate]:
        scores: dict[str, float] = {spec.template_id: 0.0 for spec in get_judgment_template_specs()}
        signal_hits: dict[str, set[str]] = {spec.template_id: set() for spec in get_judgment_template_specs()}
        rule_hits: dict[str, list[str]] = {spec.template_id: [] for spec in get_judgment_template_specs()}
        contract_hits: dict[str, list[str]] = {spec.template_id: [] for spec in get_judgment_template_specs()}

        self.helper._accumulate_signal_template_scores(prepared, scores, signal_hits)
        self.helper._accumulate_rule_template_scores(grounded_rules, scores, signal_hits, rule_hits)
        self.helper._accumulate_contract_template_scores(retained_contracts, scores, signal_hits, contract_hits)

        applied: list[AppliedJudgmentTemplate] = []
        for spec in get_judgment_template_specs():
            score = round(scores.get(spec.template_id, 0.0), 2)
            matched_rules = self.helper._dedupe_list(rule_hits[spec.template_id])
            matched_contracts = self.helper._dedupe_list(contract_hits[spec.template_id])
            matched_signal_types = sorted(signal_hits[spec.template_id])
            if score < 1.0 and not matched_rules and not matched_contracts:
                continue
            applied.append(
                AppliedJudgmentTemplate(
                    template_id=spec.template_id,
                    score=score,
                    matched_signal_types=matched_signal_types,
                    matched_rule_titles=matched_rules[:4],
                    matched_contract_items=matched_contracts[:3],
                    core_questions=list(spec.core_questions),
                )
            )
        ordered = sorted(applied, key=lambda item: item.score, reverse=True)
        if self.helper._has_workflow_pattern(prepared):
            workflow = next((item for item in ordered if item.template_id == "workflow"), None)
            if workflow:
                ordered = [workflow] + [item for item in ordered if item.template_id != "workflow"]
        elif self.helper._has_explicit_state_transition_signal(prepared):
            state_transition = next((item for item in ordered if item.template_id == "state_transition"), None)
            if state_transition:
                ordered = [state_transition] + [item for item in ordered if item.template_id != "state_transition"]
        elif prepared.signals.primary_feature_mode == "search_filters":
            query_filter = next((item for item in ordered if item.template_id == "query_filter"), None)
            if query_filter:
                ordered = [query_filter] + [item for item in ordered if item.template_id != "query_filter"]
        elif self.helper._has_amount_threshold_focus(prepared):
            amount_threshold = next((item for item in ordered if item.template_id == "amount_threshold"), None)
            if amount_threshold:
                ordered = [amount_threshold] + [item for item in ordered if item.template_id != "amount_threshold"]
        elif len(prepared.signals.save_validation) >= 2:
            validation = next((item for item in ordered if item.template_id == "validation"), None)
            if validation:
                ordered = [validation] + [item for item in ordered if item.template_id != "validation"]
        return ordered

    def collect_pattern_candidates(
        self,
        prepared: Any,
        applied_templates: list[AppliedJudgmentTemplate],
    ) -> list[PatternCandidate]:
        template_map = {item.template_id: item for item in applied_templates}
        candidates: list[PatternCandidate] = []

        def add(name: str, matched: bool, reasons: list[str]) -> None:
            item = template_map.get(name)
            score = float(item.score) if item else 0.0
            enriched_reasons = [reason for reason in reasons if reason]
            if item and item.matched_signal_types:
                enriched_reasons.extend(f"matched_signal={signal}" for signal in item.matched_signal_types[:3])
            candidates.append(
                PatternCandidate(
                    name=name,
                    matched=matched,
                    score=score,
                    reasons=enriched_reasons,
                )
            )

        workflow_actor = self.helper._workflow_actor_signal_count(prepared)
        workflow_stage = self.helper._workflow_stage_signal_count(prepared)
        workflow_gate = self.helper._workflow_gate_signal_count(prepared)
        workflow_progression = self.helper._workflow_progression_signal_count(prepared)
        add(
            "workflow",
            self.helper._has_workflow_pattern(prepared),
            [
                f"actor_signals={workflow_actor}",
                f"stage_signals={workflow_stage}",
                f"gate_signals={workflow_gate}",
                f"progression_signals={workflow_progression}",
            ],
        )
        explicit_state_transition = self.helper._has_explicit_state_transition_signal(prepared)
        add(
            "state_transition",
            explicit_state_transition,
            [
                f"explicit_state_transition={explicit_state_transition}",
                f"primary_feature_mode={prepared.signals.primary_feature_mode}",
            ],
        )
        query_filter_matched = prepared.signals.primary_feature_mode == "search_filters" or (
            prepared.signals.secondary_feature_mode == "search_filters"
            and len(prepared.signals.search_filters) >= 2
            and not self.helper._is_validation_primary(prepared)
            and not explicit_state_transition
            and not self.helper._has_workflow_pattern(prepared)
        )
        add(
            "query_filter",
            query_filter_matched,
            [
                f"primary_feature_mode={prepared.signals.primary_feature_mode}",
                f"secondary_feature_mode={prepared.signals.secondary_feature_mode}",
                f"search_filter_signals={len(prepared.signals.search_filters)}",
            ],
        )
        amount_threshold_focus = self.helper._has_amount_threshold_focus(prepared)
        add(
            "amount_threshold",
            amount_threshold_focus,
            [
                f"amount_threshold_focus={amount_threshold_focus}",
                f"validation_signals={len(prepared.signals.save_validation)}",
            ],
        )
        access_control_template = template_map.get("access_control")
        add(
            "access_control",
            bool(access_control_template) and self.helper._should_enrich_access_control(prepared, []),
            [
                f"access_control_score={float(access_control_template.score) if access_control_template else 0.0}",
                f"status_permission_signals={len(prepared.signals.status_permissions)}",
            ],
        )
        validation_primary = self.helper._is_validation_primary(prepared)
        add(
            "validation",
            validation_primary or len(prepared.signals.save_validation) >= 2,
            [
                f"validation_primary={validation_primary}",
                f"save_validation_signals={len(prepared.signals.save_validation)}",
                f"primary_feature_mode={prepared.signals.primary_feature_mode}",
            ],
        )
        return candidates

    def select_primary_judgment(
        self,
        prepared: Any,
        pattern_candidates: list[PatternCandidate],
    ) -> tuple[str, str, list[PatternCandidate]]:
        candidate_map = {item.name: item for item in pattern_candidates}

        def choose(name: str, reason: str) -> tuple[str, str]:
            return name, reason

        workflow = candidate_map.get("workflow")
        state_transition = candidate_map.get("state_transition")
        query_filter = candidate_map.get("query_filter")
        amount_threshold = candidate_map.get("amount_threshold")
        access_control = candidate_map.get("access_control")
        validation = candidate_map.get("validation")

        if workflow and workflow.matched:
            selected_name, selected_reason = choose(
                "workflow",
                "승인 주체, 단계 구조, 의사결정 게이트가 성립해 workflow를 우선 선택했습니다.",
            )
        elif state_transition and state_transition.matched:
            selected_name, selected_reason = choose(
                "state_transition",
                "명시적 상태 변경 신호가 확인되어 state_transition을 우선 선택했습니다.",
            )
        elif validation and validation.matched and prepared.signals.primary_feature_mode == "save_validation":
            selected_name, selected_reason = choose(
                "validation",
                "저장 검증 신호가 주축이라 validation을 우선 선택했습니다.",
            )
        elif query_filter and query_filter.matched and not (amount_threshold and amount_threshold.matched):
            selected_name, selected_reason = choose(
                "query_filter",
                "조회 조건, 필터, 정렬, 페이징 축이 금액 정책보다 강해 query_filter를 선택했습니다.",
            )
        elif amount_threshold and amount_threshold.matched:
            selected_name, selected_reason = choose(
                "amount_threshold",
                "금액 구간과 한도 경계가 조회형/검증형보다 강해 amount_threshold를 선택했습니다.",
            )
        elif access_control and access_control.matched:
            selected_name, selected_reason = choose(
                "access_control",
                "처리 권한과 승인 주체 축이 핵심이라 access_control을 선택했습니다.",
            )
        elif validation and validation.matched:
            selected_name, selected_reason = choose(
                "validation",
                "다른 패턴 최소 조건이 부족해 validation을 fallback으로 선택했습니다.",
            )
        else:
            selected_name, selected_reason = choose(
                "validation",
                "강한 패턴 후보가 없어 validation을 기본 fallback으로 선택했습니다.",
            )

        annotated: list[PatternCandidate] = []
        for item in pattern_candidates:
            rejected_reason = item.rejected_reason
            if item.name == selected_name:
                rejected_reason = ""
            elif item.name == "query_filter" and item.matched and prepared.signals.primary_feature_mode == "save_validation":
                rejected_reason = "저장 검증이 주축이라 query_filter 후보를 후순위로 내렸습니다."
            elif item.name == "access_control" and item.matched and selected_name == "workflow":
                rejected_reason = "승인 흐름의 단계성과 게이트가 더 강해 workflow를 우선 선택했습니다."
            elif item.matched:
                rejected_reason = f"{selected_name} 우선 규칙이 적용되어 탈락했습니다."
            else:
                rejected_reason = "최소 성립 조건 부족으로 탈락했습니다."
            annotated.append(item.model_copy(update={"rejected_reason": rejected_reason}))
        return selected_name, selected_reason, annotated

    def active_narrative_judgment(self, prepared: Any) -> str:
        return (
            (prepared.selected_narrative_judgment or "").strip()
            or (prepared.selected_primary_judgment or "").strip()
        )

    def primary_template(
        self,
        prepared: Any,
        applied_templates: list[AppliedJudgmentTemplate],
    ) -> AppliedJudgmentTemplate | None:
        if not applied_templates:
            return None
        primary_name = self.active_narrative_judgment(prepared)
        if not primary_name:
            candidates = self.collect_pattern_candidates(prepared, applied_templates)
            primary_name, _, candidates = self.select_primary_judgment(prepared, candidates)
            prepared.selected_primary_judgment = primary_name
            prepared.pattern_candidates = list(candidates)
        selected = next((item for item in applied_templates if item.template_id == primary_name), None)
        return selected or applied_templates[0]

    def ordered_templates_for_generation(
        self,
        prepared: Any,
        applied_templates: list[AppliedJudgmentTemplate],
        grounded_rules: list[GroundedBusinessRule] | None = None,
    ) -> list[AppliedJudgmentTemplate]:
        if not applied_templates:
            return []
        if grounded_rules and self.helper._should_force_access_control_narrative(grounded_rules):
            forced = next((item for item in applied_templates if item.template_id == "access_control"), None)
            if forced:
                return [forced]
        if grounded_rules and self.helper._should_force_amount_threshold_narrative(prepared, grounded_rules):
            forced = next((item for item in applied_templates if item.template_id == "amount_threshold"), None)
            if forced:
                return [forced]
        primary = self.primary_template(prepared, applied_templates)
        if not primary:
            return applied_templates
        if primary.template_id in {"workflow", "validation", "access_control", "state_transition", "query_filter", "amount_threshold"}:
            return [primary]
        return [primary] + [item for item in applied_templates if item.template_id != primary.template_id]

    def build_decision_items(
        self,
        prepared: Any,
        grounded_rules: list[GroundedBusinessRule],
        applied_templates: list[AppliedJudgmentTemplate],
    ) -> list[DecisionItem]:
        ordered_templates = self.ordered_templates_for_generation(prepared, applied_templates, grounded_rules)
        return self.helper._build_template_decision_items(prepared, grounded_rules, ordered_templates)
