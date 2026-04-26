from __future__ import annotations

import re
from typing import Any

from mellow_link.modules.rebuild_assistant.schemas import (
    ResultCitation,
    ResultExplanationContextView,
    ResultExplanationCoreJudgmentView,
    ResultExplanationEvidenceView,
    ResultExplanationReviewDiffPreview,
    ResultExplanationResponse,
    ResultExplanationSectionView,
    ResultExplanationSummaryCard,
    ResultExplanationTaxonomyView,
)
from mellow_link.services.refactoring_support_engine.surface_access import (
    can_view_review_diff_preview,
    filter_review_diff_for_access,
    normalize_surface_mode,
    policy_for_surface_mode,
    review_diff_preview_surface_state,
)
from mellow_link.services.refactoring_support_engine.template_support import TemplateSupport
from mellow_link.modules.rebuild_assistant.postprocess.information_separation import (
    package_information_role,
    purify_diagnosis_lines,
)


AUDIENCE_LABELS: dict[str, dict[str, str]] = {
    "developer": {
        "judgment": "구조 판단",
        "strategy": "구현 전략",
        "priority": "우선순위 계산",
        "execution": "실행 기준",
        "scope": "분석 범위",
    },
    "manager": {
        "judgment": "구조 판단",
        "strategy": "권장 전략",
        "priority": "우선순위",
        "execution": "실행 단계",
        "scope": "분석 범위",
    },
    "client": {
        "judgment": "핵심 판단",
        "strategy": "권장 방향",
        "priority": "우선 적용 근거",
        "execution": "진행 단계",
        "scope": "검토 범위",
    },
}

STRUCTURAL_JUDGMENT_LABELS: dict[str, str] = {
    "refactor": "책임 분리형 개선",
    "redesign": "구조 재설계",
    "migration_consideration": "단계적 전환 검토",
    "observation_only": "추가 관찰 필요",
}


SECTION_TITLES: dict[str, str] = {
    "report_purpose": "보고 목적",
    "executive_summary_v2": "핵심 요약",
    "one_line_conclusion": "핵심 결론",
    "analysis_summary": "핵심 객체",
    "primary_judgment_reason": "판단 이유",
    "recommended_option": "추천안",
    "execution_plan": "실행 계획",
    "risks": "리스크",
}

EXTERNAL_LABEL_PREFIXES: dict[str, str] = {
    "상황 / 목적": "",
    "문제 정의": "문제: ",
    "판단 질문": "검토 질문: ",
    "선택지 비교": "선택지: ",
    "판단 기준": "기준: ",
    "결론": "",
    "핵심 이유": "이유: ",
    "누락된 정보": "추가 확인 필요: ",
    "리스크": "리스크: ",
    "숨겨진 전제 / 가정": "가정: ",
    "단계별 추진 흐름": "",
    "중점 실행 과제": "",
    "근거": "근거: ",
    "핵심 규칙": "핵심 규칙: ",
    "설계 흐름": "",
    "적용 방향": "적용 방향: ",
    "후속 판단 포인트": "후속 판단 포인트: ",
}

STATE_LABELS: dict[str, str] = {
    "assertive": "실행 착수 가능",
    "conditional": "조건 확인 후 실행",
    "review_required": "검증 후 적용",
    "blocked": "실행 불가",
}

INPUT_KIND_TO_STYLE: dict[str, str] = {
    "document": "document_style",
    "code": "technical_style",
    "mixed": "mixed_style",
}

_CODE_INPUT_HINTS: tuple[str, ...] = (
    r"\bselect\b",
    r"\bjoin\b",
    r"\bwhere\b",
    r"\binsert\b",
    r"\bupdate\b",
    r"\bdelete\b",
    r"\bsql\b",
    r"\bapi\b",
    r"\bclass\b",
    r"\bfunction\b",
    r"\bdef\b",
    r"\btable\b",
    r"\bschema\b",
    r"\bgl\b",
    r"\bfifo\b",
    r"\blot\b",
    r"입력 검증",
    r"저장 전",
    r"차단 조건",
    r"예외 처리",
    r"파라미터",
    r"조회 조건",
    r"전표",
    r"검증 규칙",
    r"상태 전이",
)

_DOCUMENT_INPUT_HINTS: tuple[str, ...] = (
    r"보고서",
    r"컨설팅",
    r"개요",
    r"배경",
    r"목적",
    r"비전",
    r"계획",
    r"전략",
    r"방향",
    r"효과",
    r"현행",
    r"추진",
    r"개선",
    r"문제 정의",
    r"검토 질문",
    r"제안",
)


class ExplanationPresenter:
    def __init__(self) -> None:
        self.template_support = TemplateSupport()

    def present(
        self,
        *,
        project_id: str,
        result_package: dict[str, Any],
        audience: str = "manager",
        surface_mode: str = "internal",
    ) -> ResultExplanationResponse:
        normalized_audience = audience if audience in {"developer", "manager", "client"} else "manager"
        normalized_surface_mode = normalize_surface_mode(surface_mode)
        access_policy = policy_for_surface_mode(normalized_surface_mode)
        authoritative = result_package.get("authoritative_payload") if isinstance(result_package, dict) else {}
        authoritative = authoritative if isinstance(authoritative, dict) else {}
        polish_bundle = result_package.get("polish_bundle") if isinstance(result_package, dict) else None
        polish_bundle = polish_bundle if isinstance(polish_bundle, dict) else None
        polished_sections = self._polished_section_map(polish_bundle)
        wording_source = self._wording_source(result_package=result_package, polish_bundle=polish_bundle)

        decision_summary = authoritative.get("decision_summary") or {}
        diagnosis_report = authoritative.get("diagnosis_report") or {}
        structure_snapshot = authoritative.get("structure_snapshot") or {}
        improvement_plan_bundle = authoritative.get("improvement_plan_bundle") or {}
        appendix = authoritative.get("appendix") or {}
        family_classification = result_package.get("family_classification") if isinstance(result_package, dict) else {}
        family_classification = family_classification if isinstance(family_classification, dict) else {}

        top_decision = self._first_list_item(decision_summary.get("decisions"))
        top_issue = self._first_list_item(diagnosis_report.get("issues"))
        top_stage = self._first_list_item(improvement_plan_bundle.get("execution_stages"))
        coverage_summary = structure_snapshot.get("coverage_summary") or {}
        evidence_map = self._evidence_map(appendix.get("evidence_index"))
        issue_map = self._issue_map(diagnosis_report.get("issues"))
        structural_judgment = str(result_package.get("structural_judgment") or "").strip()
        narrative_axis = str(result_package.get("narrative_axis") or "").strip()
        recommended_strategy = str(decision_summary.get("recommended_strategy") or family_classification.get("internal_strategy") or "-")
        display_strategy = self._display_strategy(result_package=result_package, fallback=recommended_strategy)
        analysis_first_surface = self._uses_analysis_first_surface(result_package)
        comparison_first_surface = self._uses_comparison_first_surface(result_package)
        information_role = package_information_role(result_package)

        strategy_citations = self._decision_citations(top_decision, evidence_map=evidence_map, issue_map=issue_map)
        stage_citations = self._stage_citations(top_stage, top_decision=top_decision, evidence_map=evidence_map, issue_map=issue_map)
        scope_citations = self._scope_citations(structure_snapshot, evidence_map=evidence_map)
        risk_citations = self._risk_citations(improvement_plan_bundle, top_decision=top_decision, evidence_map=evidence_map, issue_map=issue_map)

        if normalized_surface_mode == "external":
            external_strategy_citations = self._externalize_citations(strategy_citations)
            external_stage_citations = self._externalize_citations(stage_citations)
            external_risk_citations = self._externalize_citations(risk_citations)
            summary_cards = self._external_summary_cards(
                structural_judgment=structural_judgment,
                display_strategy=display_strategy,
                top_decision=top_decision,
                top_issue=top_issue,
                top_stage=top_stage,
                strategy_citations=external_strategy_citations,
                stage_citations=external_stage_citations,
                result_package=result_package,
            )
            section_views = self._external_section_views(
                audience=normalized_audience,
                result_package=result_package,
                strategy_citations=external_strategy_citations,
                stage_citations=external_stage_citations,
                risk_citations=external_risk_citations,
            )
        else:
            summary_cards = [
                ResultExplanationSummaryCard(
                    card_key="judgment",
                    title=self._summary_card_title(
                        result_package=result_package,
                        card_key="judgment",
                        fallback=AUDIENCE_LABELS[normalized_audience]["judgment"],
                    ),
                    body=self._judgment_body(
                        audience=normalized_audience,
                        structural_judgment=structural_judgment,
                        internal_strategy=recommended_strategy,
                        display_strategy=display_strategy,
                        top_decision=top_decision,
                        analysis_first_surface=analysis_first_surface,
                        comparison_first_surface=comparison_first_surface,
                        information_role=information_role,
                    ),
                    citations=strategy_citations,
                ),
                ResultExplanationSummaryCard(
                    card_key="strategy",
                    title=self._summary_card_title(
                        result_package=result_package,
                        card_key="strategy",
                        fallback=AUDIENCE_LABELS[normalized_audience]["strategy"],
                    ),
                    body=self._strategy_body(
                        audience=normalized_audience,
                        internal_strategy=recommended_strategy,
                        display_strategy=display_strategy,
                        top_decision=top_decision,
                        top_issue=top_issue,
                        rationale_override=str(result_package.get("primary_judgment_reason") or "").strip(),
                        analysis_first_surface=analysis_first_surface,
                        comparison_first_surface=comparison_first_surface,
                        information_role=information_role,
                    ),
                    citations=strategy_citations,
                ),
                ResultExplanationSummaryCard(
                    card_key="priority",
                    title=AUDIENCE_LABELS[normalized_audience]["priority"],
                    body=self._priority_body(audience=normalized_audience, top_decision=top_decision),
                    citations=strategy_citations,
                ),
                ResultExplanationSummaryCard(
                    card_key="execution",
                    title=self._summary_card_title(
                        result_package=result_package,
                        card_key="execution",
                        fallback=AUDIENCE_LABELS[normalized_audience]["execution"],
                    ),
                    body=self._execution_body(
                        audience=normalized_audience,
                        execution_stages=improvement_plan_bundle.get("execution_stages"),
                        top_stage=top_stage,
                        analysis_first_surface=analysis_first_surface,
                        comparison_first_surface=comparison_first_surface,
                        information_role=information_role,
                    ),
                    citations=stage_citations,
                ),
                ResultExplanationSummaryCard(
                    card_key="scope",
                    title=AUDIENCE_LABELS[normalized_audience]["scope"],
                    body=self._scope_body(audience=normalized_audience, coverage_summary=coverage_summary),
                    citations=scope_citations,
                ),
            ]
            section_views = self._internal_section_views(
                audience=normalized_audience,
                result_package=result_package,
                polished_sections=polished_sections,
                strategy_citations=strategy_citations,
                stage_citations=stage_citations,
                risk_citations=risk_citations,
            )

        warnings = list(polish_bundle.get("warnings") or []) if polish_bundle else []
        if not polish_bundle:
            warnings.append("polish_bundle unavailable; guard-backed wording was used when available, otherwise deterministic fallback was used.")

        narrative_extension = self._narrative_extension(polish_bundle)
        narrative_guard_metadata = self._narrative_guard_metadata(result_package)
        filtered_review_diff = filter_review_diff_for_access(
            ((result_package.get("extensions") or {}) if isinstance(result_package, dict) else {}).get("review_diff"),
            access_profile=access_policy.access_profile,
        )
        review_diff_preview = (
            self._review_diff_preview(filtered_review_diff.filtered)
            if can_view_review_diff_preview(access_policy.access_profile)
            else ResultExplanationReviewDiffPreview()
        )
        return ResultExplanationResponse(
            project_id=project_id,
            audience=normalized_audience,
            surface_mode=normalized_surface_mode,
            taxonomy_view=ResultExplanationTaxonomyView(
                core_judgment=ResultExplanationCoreJudgmentView(
                    structural_judgment=structural_judgment,
                    recommended_strategy=recommended_strategy,
                    display_strategy=display_strategy,
                    top_decision_type=str(top_decision.get("decision_type") or ""),
                ),
                evidence_view=ResultExplanationEvidenceView(
                    top_priority_score=top_decision.get("priority_score") if top_decision else None,
                    score_breakdown=dict(top_decision.get("score_breakdown") or {}),
                    explainability=dict(top_decision.get("explainability") or {}),
                    citations=strategy_citations,
                ),
                explanation_context=ResultExplanationContextView(
                    narrative_axis=narrative_axis,
                ),
            ),
            review_diff_preview=review_diff_preview,
            judgment_canvas=(
                result_package.get("judgment_canvas")
                if isinstance(result_package.get("judgment_canvas"), dict)
                else authoritative.get("judgment_canvas", {})
            ),
            summary_cards=summary_cards,
            section_views=section_views,
            warnings=warnings,
            provenance={
                "fact_source": "authoritative_payload",
                "wording_source": wording_source,
                "delivery_mode_applied": False,
                "narrative_override_applied": wording_source in {"validated_explanation_blocks", "validated_narrative_layer"} or narrative_extension.get("source") == "ai",
                "narrative_source": (
                    str(narrative_guard_metadata.get("source") or "").strip()
                    or str(narrative_extension.get("source") or "").strip()
                    or "deterministic_fallback"
                ),
                "surface_mode": normalized_surface_mode,
                "access_profile": access_policy.access_profile,
                "review_diff_surface": review_diff_preview_surface_state(
                    filtered_review_diff.filtered,
                    access_profile=access_policy.access_profile,
                ),
                "review_diff_surface_policy": filtered_review_diff.review_diff_surface_policy,
                "field_visibility": dict(filtered_review_diff.field_visibility),
            },
        )

    def _judgment_body(
        self,
        *,
        audience: str,
        structural_judgment: str,
        internal_strategy: str,
        display_strategy: str,
        top_decision: dict[str, Any],
        analysis_first_surface: bool,
        comparison_first_surface: bool,
        information_role: str = "",
    ) -> str:
        decision_type = str(top_decision.get("decision_type") or "-")
        normalized_judgment = structural_judgment or "-"
        if analysis_first_surface:
            if information_role == "diagnosis":
                return "현재 결과는 전표/GL 연계의 기준 불일치 가능성과 회계 영향을 진단하는 문서입니다."
            if information_role == "decision":
                return "현재 결과는 계산 기준 선택지를 비교해 우선 추천안과 적용 검증 기준을 정리하는 문서입니다."
            if audience == "developer":
                return (
                    f"canonical 구조 판단은 {normalized_judgment}이며, 내부 taxonomy 전략은 {internal_strategy}입니다. "
                    f"사용자 노출 문구는 {display_strategy}로 유지하고, 상위 decision type은 {decision_type}입니다."
                )
            if audience == "client":
                return (
                    f"이번 결과는 {display_strategy} 기준으로 현행 운영 구조를 먼저 설명합니다. "
                    f"내부 판단 축은 {normalized_judgment}이고, 실행 해석은 {decision_type} 기준으로 유지됩니다."
                )
            return (
                f"현재 결과는 {display_strategy} 기준으로 현행 구조와 처리 흐름을 먼저 복원하는 분석 성격입니다. "
                f"내부 판단 축은 {normalized_judgment}이고, 상위 판단은 {decision_type}입니다."
            )
        if comparison_first_surface:
            if audience == "developer":
                return (
                    f"canonical 구조 판단은 {normalized_judgment}이며, 내부 taxonomy 전략은 {internal_strategy}입니다. "
                    f"사용자 노출 문구는 {display_strategy}로 유지하고, 상위 decision type은 {decision_type}입니다."
                )
            if audience == "client":
                return (
                    f"이번 결과는 {display_strategy} 기준으로 복수 선택지를 비교해 우선 검토안을 정리합니다. "
                    f"내부 판단 축은 {normalized_judgment}이고, 실행 해석은 {decision_type} 기준으로 유지됩니다."
                )
            return (
                f"현재 결과는 {display_strategy} 기준으로 복수 선택지를 비교해 추천안을 좁히는 판단 성격입니다. "
                f"내부 판단 축은 {normalized_judgment}이고, 상위 판단은 {decision_type}입니다."
            )
        if audience == "developer":
            return (
                f"canonical 구조 판단은 {normalized_judgment}이며, 권장 전략은 {internal_strategy}입니다. "
                f"상위 decision type은 {decision_type}입니다."
            )
        if audience == "client":
            return (
                f"이번 분석의 핵심 구조 판단은 {normalized_judgment}이고, 현재 권장 방향은 {display_strategy}입니다. "
                f"실행 해석은 {decision_type} 기준으로 정리됩니다."
            )
        return (
            f"현재 구조 판단은 {normalized_judgment}이며, 권장 전략은 {display_strategy}입니다. "
            f"상위 개선 방식은 {decision_type}입니다."
        )

    def _external_judgment_body(
        self,
        *,
        structural_judgment: str,
        display_strategy: str,
        result_package: dict[str, Any],
        analysis_first_surface: bool,
        comparison_first_surface: bool,
        information_role: str = "",
    ) -> str:
        state = self._planner_surface_state(result_package)
        state_label = STATE_LABELS[state]
        if analysis_first_surface:
            if information_role == "diagnosis":
                return f"현재 상태는 {state_label}입니다. 전표/GL 불일치와 회계 영향을 확인합니다."
            if information_role == "decision":
                return f"현재 상태는 {state_label}입니다. 계산 기준 선택지를 비교합니다."
            return f"현재 상태는 {state_label}입니다. 현행 흐름과 자산 경계를 먼저 확인합니다."
        if comparison_first_surface:
            return f"현재 상태는 {state_label}입니다. {display_strategy} 기준으로 선택지를 비교합니다."
        label = self._humanize_structural_judgment(structural_judgment)
        strategy = display_strategy or "리팩터링 우선"
        if state == "blocked":
            return f"현재 상태는 {state_label}입니다. 차단 요인을 해소한 뒤 {strategy} 방향을 다시 판단합니다."
        if state == "review_required":
            return f"현재 상태는 {state_label}입니다. {label} 성격이 강해 검증 뒤 적용 여부를 정합니다."
        if state == "conditional":
            return f"현재 상태는 {state_label}입니다. {label} 성격이 강해 선행 조건을 먼저 확인합니다."
        return f"현재 상태는 {state_label}입니다. {label} 성격이 강해 {strategy} 방향으로 진행합니다."

    def _external_strategy_body(
        self,
        *,
        display_strategy: str,
        top_decision: dict[str, Any],
        top_issue: dict[str, Any],
        result_package: dict[str, Any],
        analysis_first_surface: bool,
        comparison_first_surface: bool,
        information_role: str = "",
        rationale_override: str = "",
    ) -> str:
        state = self._planner_surface_state(result_package)
        state_label = STATE_LABELS[state]
        rationale = self._compress_external_sentence(
            rationale_override or str(top_decision.get("rationale") or "").strip() or str(top_issue.get("summary") or "").strip()
        )
        if state == "blocked":
            return f"현재 상태는 {state_label}입니다. 차단 요인과 누락 근거를 먼저 정리합니다."
        if analysis_first_surface:
            if information_role == "diagnosis":
                return f"현재 상태는 {state_label}입니다. 전표/GL 기준 불일치와 회계 영향만 정리합니다."
            if information_role == "decision":
                return f"현재 상태는 {state_label}입니다. {display_strategy} 기준으로 선택지를 좁힙니다."
            if rationale:
                return f"현재 상태는 {state_label}입니다. {self._short_external_fragment(rationale)}를 먼저 확인합니다."
            return f"현재 상태는 {state_label}입니다. 핵심 객체와 처리 흐름을 먼저 정리합니다."
        if comparison_first_surface:
            if rationale:
                return f"현재 상태는 {state_label}입니다. {display_strategy} 기준으로 {self._short_external_fragment(rationale)}를 비교합니다."
            return f"현재 상태는 {state_label}입니다. {display_strategy} 기준으로 선택지를 비교합니다."
        if state == "review_required":
            if rationale:
                return f"현재 상태는 {state_label}입니다. {self._short_external_fragment(rationale)}를 기준으로 검증합니다."
            return f"현재 상태는 {state_label}입니다. 검증을 마친 뒤 적용 여부를 정합니다."
        if state == "conditional":
            if rationale:
                return f"현재 상태는 {state_label}입니다. {self._short_external_fragment(rationale)}를 기준으로 선행 조건을 확인합니다."
            return f"현재 상태는 {state_label}입니다. 조건 충족 여부를 먼저 확인합니다."
        if rationale:
            return f"현재 상태는 {state_label}입니다. {self._short_external_fragment(rationale)}가 핵심 근거입니다."
        return f"현재 상태는 {state_label}입니다. {display_strategy} 방향으로 바로 진행할 수 있습니다."

    def _external_execution_body(
        self,
        *,
        top_stage: dict[str, Any],
        top_decision: dict[str, Any],
        result_package: dict[str, Any],
        analysis_first_surface: bool,
        comparison_first_surface: bool,
        information_role: str = "",
    ) -> str:
        state = self._planner_surface_state(result_package)
        state_label = STATE_LABELS[state]
        stage_title = self._compress_external_sentence(str(top_stage.get("title") or "").strip())
        rationale = self._compress_external_sentence(str(top_decision.get("rationale") or "").strip())
        if state == "blocked":
            return f"현재 상태는 {state_label}입니다. 실행보다 차단 요인 해소를 먼저 진행합니다."
        if analysis_first_surface:
            if information_role == "diagnosis":
                return f"현재 상태는 {state_label}입니다. 전표 기준과 회계 연결 기준을 먼저 확인합니다."
            if information_role == "decision":
                if stage_title:
                    return f"현재 상태는 {state_label}입니다. 첫 단계는 {self._short_external_fragment(stage_title)}입니다."
                return f"현재 상태는 {state_label}입니다. 첫 단계는 적용 검증 항목 정리입니다."
            if stage_title:
                return f"현재 상태는 {state_label}입니다. 첫 단계는 {self._short_external_fragment(stage_title)}입니다."
            return f"현재 상태는 {state_label}입니다. 첫 단계는 핵심 객체와 처리 순서 정리입니다."
        if comparison_first_surface:
            if stage_title:
                return f"현재 상태는 {state_label}입니다. 첫 단계는 {self._short_external_fragment(stage_title)}입니다."
            return f"현재 상태는 {state_label}입니다. 첫 단계는 적용 순서 확인입니다."
        if state == "review_required":
            if stage_title:
                return f"현재 상태는 {state_label}입니다. 첫 단계는 {self._short_external_fragment(stage_title)} 검증입니다."
            return f"현재 상태는 {state_label}입니다. 첫 단계는 근거와 충돌 검증입니다."
        if state == "conditional":
            if stage_title:
                return f"현재 상태는 {state_label}입니다. 첫 단계는 {self._short_external_fragment(stage_title)} 확인입니다."
            return f"현재 상태는 {state_label}입니다. 첫 단계는 선행 조건 확인입니다."
        if stage_title:
            return f"현재 상태는 {state_label}입니다. 첫 단계는 {self._short_external_fragment(stage_title)}입니다."
        return f"현재 상태는 {state_label}입니다. 첫 단계는 구현 경계 정리입니다."

    def _humanize_structural_judgment(self, structural_judgment: str) -> str:
        normalized = str(structural_judgment or "").strip()
        if not normalized:
            return "추가 관찰이 필요한"
        return STRUCTURAL_JUDGMENT_LABELS.get(normalized, normalized)

    def _polished_section_map(self, polish_bundle: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        if not polish_bundle:
            return {}
        sections = polish_bundle.get("polished_sections") or []
        return {
            str(section.get("section_key") or ""): section
            for section in sections
            if isinstance(section, dict) and str(section.get("section_key") or "").strip()
        }

    def _first_list_item(self, values: Any) -> dict[str, Any]:
        if isinstance(values, list) and values and isinstance(values[0], dict):
            return values[0]
        return {}

    def _evidence_map(self, values: Any) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for item in values or []:
            if not isinstance(item, dict):
                continue
            evidence_id = str(item.get("evidence_id") or "").strip()
            if evidence_id:
                output[evidence_id] = item
        return output

    def _issue_map(self, values: Any) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for item in values or []:
            if not isinstance(item, dict):
                continue
            issue_id = str(item.get("issue_id") or "").strip()
            if issue_id:
                output[issue_id] = item
        return output

    def _internal_section_views(
        self,
        *,
        audience: str,
        result_package: dict[str, Any],
        polished_sections: dict[str, dict[str, Any]],
        strategy_citations: list[ResultCitation],
        stage_citations: list[ResultCitation],
        risk_citations: list[ResultCitation],
    ) -> list[ResultExplanationSectionView]:
        information_role = package_information_role(result_package)
        if information_role == "diagnosis":
            return self._diagnosis_section_views(
                audience=audience,
                result_package=result_package,
                polished_sections=polished_sections,
                strategy_citations=strategy_citations,
                risk_citations=risk_citations,
            )

        section_views: list[ResultExplanationSectionView] = []
        section_views.append(
            ResultExplanationSectionView(
                section_key="report_purpose",
                title=self._section_title(result_package=result_package, section_key="report_purpose"),
                audience=audience,
                text=self._section_text(
                    section_key="report_purpose",
                    audience=audience,
                    result_package=result_package,
                    polished_sections=polished_sections,
                ),
                citations=strategy_citations,
            )
        )
        section_views.append(
            ResultExplanationSectionView(
                section_key="one_line_conclusion",
                title=self._section_title(result_package=result_package, section_key="one_line_conclusion"),
                audience=audience,
                text=self._section_text(
                    section_key="one_line_conclusion",
                    audience=audience,
                    result_package=result_package,
                    polished_sections=polished_sections,
                ),
                citations=strategy_citations,
            )
        )
        section_views.append(
            ResultExplanationSectionView(
                section_key="analysis_summary",
                title=self._section_title(result_package=result_package, section_key="analysis_summary"),
                audience=audience,
                text=self._section_text(
                    section_key="analysis_summary",
                    audience=audience,
                    result_package=result_package,
                    polished_sections=polished_sections,
                ),
                citations=strategy_citations,
            )
        )
        section_views.append(
            ResultExplanationSectionView(
                section_key="recommended_option",
                title=self._section_title(result_package=result_package, section_key="recommended_option"),
                audience=audience,
                text=self._section_text(
                    section_key="recommended_option",
                    audience=audience,
                    result_package=result_package,
                    polished_sections=polished_sections,
                ),
                citations=strategy_citations,
            )
        )
        section_views.append(
            ResultExplanationSectionView(
                section_key="execution_plan",
                title=self._section_title(result_package=result_package, section_key="execution_plan"),
                audience=audience,
                text=self._section_text(
                    section_key="execution_plan",
                    audience=audience,
                    result_package=result_package,
                    polished_sections=polished_sections,
                ),
                citations=stage_citations,
            )
        )
        section_views.append(
            ResultExplanationSectionView(
                section_key="risks",
                title=self._section_title(result_package=result_package, section_key="risks"),
                audience=audience,
                text=self._section_text(
                    section_key="risks",
                    audience=audience,
                    result_package=result_package,
                    polished_sections=polished_sections,
                ),
                citations=risk_citations,
            )
        )
        if information_role:
            allowed_by_role = {
                "structure": {"report_purpose", "one_line_conclusion", "analysis_summary", "execution_plan"},
                "decision": {"report_purpose", "one_line_conclusion", "recommended_option", "execution_plan"},
            }
            allowed = allowed_by_role.get(information_role)
            if allowed:
                section_views = [section for section in section_views if section.section_key in allowed]
        return [section for section in section_views if section.text.strip()]

    def _diagnosis_section_views(
        self,
        *,
        audience: str,
        result_package: dict[str, Any],
        polished_sections: dict[str, dict[str, Any]],
        strategy_citations: list[ResultCitation],
        risk_citations: list[ResultCitation],
    ) -> list[ResultExplanationSectionView]:
        sections: list[ResultExplanationSectionView] = []
        for section_key, citations in (
            ("report_purpose", strategy_citations),
            ("executive_summary_v2", strategy_citations),
            ("primary_judgment_reason", strategy_citations),
            ("risks", risk_citations),
        ):
            sections.append(
                ResultExplanationSectionView(
                    section_key=section_key,
                    title=self._section_title(result_package=result_package, section_key=section_key),
                    audience=audience,
                    text=self._section_text(
                        section_key=section_key,
                        audience=audience,
                        result_package=result_package,
                        polished_sections=polished_sections,
                    ),
                    citations=citations,
                )
            )
        return [section for section in sections if section.text.strip()]

    def _external_summary_cards(
        self,
        *,
        structural_judgment: str,
        display_strategy: str,
        top_decision: dict[str, Any],
        top_issue: dict[str, Any],
        top_stage: dict[str, Any],
        strategy_citations: list[ResultCitation],
        stage_citations: list[ResultCitation],
        result_package: dict[str, Any],
    ) -> list[ResultExplanationSummaryCard]:
        analysis_first_surface = self._uses_analysis_first_surface(result_package)
        comparison_first_surface = self._uses_comparison_first_surface(result_package)
        information_role = package_information_role(result_package)
        surface_style = self._external_surface_style(result_package)
        if surface_style == "technical_style":
            return [
                ResultExplanationSummaryCard(
                    card_key="judgment",
                    title="핵심 문제",
                    body="\n".join(self._technical_problem_lines(result_package)[:2]),
                    citations=strategy_citations,
                ),
                ResultExplanationSummaryCard(
                    card_key="strategy",
                    title="영향",
                    body="\n".join(self._technical_impact_lines(result_package)[:2]),
                    citations=strategy_citations,
                ),
                ResultExplanationSummaryCard(
                    card_key="execution",
                    title="권장 조치",
                    body="\n".join(self._technical_action_lines(result_package)[:2]),
                    citations=stage_citations,
                ),
            ]
        return [
            ResultExplanationSummaryCard(
                card_key="judgment",
                title=self._summary_card_title(result_package=result_package, card_key="judgment", fallback="핵심 판단"),
                body=self._external_judgment_body(
                    structural_judgment=structural_judgment,
                    display_strategy=display_strategy,
                    result_package=result_package,
                    analysis_first_surface=analysis_first_surface,
                    comparison_first_surface=comparison_first_surface,
                    information_role=information_role,
                ),
                citations=strategy_citations,
            ),
            ResultExplanationSummaryCard(
                card_key="strategy",
                title=self._summary_card_title(result_package=result_package, card_key="strategy", fallback="왜 이 방향인가"),
                body=self._external_strategy_body(
                    display_strategy=display_strategy,
                    top_decision=top_decision,
                    top_issue=top_issue,
                    result_package=result_package,
                    rationale_override=str(result_package.get("primary_judgment_reason") or "").strip(),
                    analysis_first_surface=analysis_first_surface,
                    comparison_first_surface=comparison_first_surface,
                    information_role=information_role,
                ),
                citations=strategy_citations,
            ),
            ResultExplanationSummaryCard(
                card_key="execution",
                title=self._summary_card_title(result_package=result_package, card_key="execution", fallback="다음 단계"),
                body=self._external_execution_body(
                    top_stage=top_stage,
                    top_decision=top_decision,
                    result_package=result_package,
                    analysis_first_surface=analysis_first_surface,
                    comparison_first_surface=comparison_first_surface,
                    information_role=information_role,
                ),
                citations=stage_citations,
            ),
        ]

    def _external_section_views(
        self,
        *,
        audience: str,
        result_package: dict[str, Any],
        strategy_citations: list[ResultCitation],
        stage_citations: list[ResultCitation],
        risk_citations: list[ResultCitation],
    ) -> list[ResultExplanationSectionView]:
        analysis_first_surface = self._uses_analysis_first_surface(result_package)
        comparison_first_surface = self._uses_comparison_first_surface(result_package)
        titled_surface = analysis_first_surface or comparison_first_surface
        information_role = package_information_role(result_package)
        surface_style = self._external_surface_style(result_package)
        if information_role == "diagnosis":
            return self._diagnosis_section_views(
                audience=audience,
                result_package=result_package,
                polished_sections={},
                strategy_citations=strategy_citations,
                risk_citations=risk_citations,
            )

        sections: list[ResultExplanationSectionView] = []
        if surface_style == "technical_style":
            sections.append(
                ResultExplanationSectionView(
                    section_key="recommended_option",
                    title="권장 조치",
                    audience=audience,
                    text="\n".join(self._technical_action_lines(result_package)),
                    citations=strategy_citations,
                )
            )
            sections.append(
                ResultExplanationSectionView(
                    section_key="execution_plan",
                    title="검증 포인트",
                    audience=audience,
                    text="\n".join(self._technical_verification_lines(result_package)),
                    citations=stage_citations,
                )
            )
            sections.append(
                ResultExplanationSectionView(
                    section_key="risks",
                    title="영향",
                    audience=audience,
                    text="\n".join(self._technical_impact_lines(result_package)),
                    citations=risk_citations,
                )
            )
            return [section for section in sections if section.text.strip()]
        if not information_role or information_role == "decision":
            sections.append(
                ResultExplanationSectionView(
                    section_key="recommended_option",
                    title=(
                        self._section_title(result_package=result_package, section_key="recommended_option", fallback="이 방향의 효과")
                        if titled_surface
                        else "이 방향의 효과"
                    ),
                    audience=audience,
                    text=self._clean_presented_text(
                        section_key="recommended_option",
                        text=self._external_recommended_option_text(result_package),
                        external=True,
                        result_package=result_package,
                    ),
                    citations=strategy_citations,
                )
            )
        if not information_role or information_role in {"structure", "diagnosis", "decision"}:
            sections.append(
                ResultExplanationSectionView(
                    section_key="execution_plan",
                    title=(
                        self._section_title(result_package=result_package, section_key="execution_plan", fallback="진행 흐름")
                        if titled_surface
                        else "코드 분석 포인트" if surface_style == "mixed_style" else "진행 흐름"
                    ),
                    audience=audience,
                    text=(
                        "\n".join(self._technical_verification_lines(result_package))
                        if surface_style == "mixed_style"
                        else self._clean_presented_text(
                            section_key="execution_plan",
                            text=self._external_execution_plan_text(result_package),
                            external=True,
                            result_package=result_package,
                        )
                    ),
                    citations=stage_citations,
                )
            )
        if not information_role or information_role == "diagnosis":
            sections.append(
                ResultExplanationSectionView(
                    section_key="risks",
                    title=(
                        self._section_title(result_package=result_package, section_key="risks", fallback="주의할 영향")
                        if titled_surface
                        else "주의할 영향"
                    ),
                    audience=audience,
                    text=self._clean_presented_text(
                        section_key="risks",
                        text=self._external_risk_text(result_package),
                        external=True,
                        result_package=result_package,
                    ),
                    citations=risk_citations,
                )
            )
        return [section for section in sections if section.text.strip()]

    def _decision_citations(
        self,
        decision: dict[str, Any],
        *,
        evidence_map: dict[str, dict[str, Any]],
        issue_map: dict[str, dict[str, Any]],
    ) -> list[ResultCitation]:
        citations: list[ResultCitation] = []
        decision_id = str(decision.get("decision_id") or "").strip()
        issue_ids = [str(item).strip() for item in decision.get("issue_ids") or [] if str(item).strip()]
        issue_id = issue_ids[0] if issue_ids else None
        evidence_ids = [str(item).strip() for item in decision.get("evidence_ids") or [] if str(item).strip()]
        if not evidence_ids and issue_id and issue_id in issue_map:
            evidence_ids = [str(item).strip() for item in issue_map[issue_id].get("evidence_ids") or [] if str(item).strip()]
        for evidence_id in evidence_ids[:2]:
            evidence = evidence_map.get(evidence_id) or {}
            citations.append(
                ResultCitation(
                    decision_id=decision_id or None,
                    issue_id=issue_id,
                    evidence_id=evidence_id,
                    locator=str(evidence.get("locator") or ""),
                    excerpt=str(evidence.get("excerpt") or ""),
                )
            )
        if not citations and decision_id:
            citations.append(ResultCitation(decision_id=decision_id, issue_id=issue_id))
        return citations

    def _stage_citations(
        self,
        stage: dict[str, Any],
        *,
        top_decision: dict[str, Any],
        evidence_map: dict[str, dict[str, Any]],
        issue_map: dict[str, dict[str, Any]],
    ) -> list[ResultCitation]:
        stage_id = str(stage.get("stage_id") or "").strip()
        decision_citations = self._decision_citations(top_decision, evidence_map=evidence_map, issue_map=issue_map)
        if not stage_id:
            return decision_citations
        output = [ResultCitation(stage_id=stage_id)]
        output.extend(
            ResultCitation(
                stage_id=stage_id,
                decision_id=item.decision_id,
                issue_id=item.issue_id,
                evidence_id=item.evidence_id,
                locator=item.locator,
                excerpt=item.excerpt,
            )
            for item in decision_citations[:2]
        )
        return output

    def _scope_citations(
        self,
        structure_snapshot: dict[str, Any],
        *,
        evidence_map: dict[str, dict[str, Any]],
    ) -> list[ResultCitation]:
        citations: list[ResultCitation] = []
        feature_slices = structure_snapshot.get("feature_slices") or []
        if feature_slices:
            first_slice = feature_slices[0] if isinstance(feature_slices[0], dict) else {}
            for evidence in list(evidence_map.values())[:2]:
                citations.append(
                    ResultCitation(
                        locator=str(evidence.get("locator") or ""),
                        excerpt=str(evidence.get("excerpt") or ""),
                        evidence_id=str(evidence.get("evidence_id") or ""),
                    )
                )
            if citations:
                return citations
            slice_name = str(first_slice.get("name") or first_slice.get("slice_id") or "").strip()
            if slice_name:
                return [ResultCitation(locator=f"feature_slice:{slice_name}")]
        return citations

    def _risk_citations(
        self,
        improvement_plan_bundle: dict[str, Any],
        *,
        top_decision: dict[str, Any],
        evidence_map: dict[str, dict[str, Any]],
        issue_map: dict[str, dict[str, Any]],
    ) -> list[ResultCitation]:
        risk_checkpoints = improvement_plan_bundle.get("risk_checkpoints") or []
        if isinstance(risk_checkpoints, list) and risk_checkpoints:
            first = risk_checkpoints[0] if isinstance(risk_checkpoints[0], dict) else {}
            decision_id = ""
            decision_ids = [str(item).strip() for item in first.get("decision_ids") or [] if str(item).strip()]
            if decision_ids:
                decision_id = decision_ids[0]
            if decision_id:
                return [ResultCitation(decision_id=decision_id)]
        return self._decision_citations(top_decision, evidence_map=evidence_map, issue_map=issue_map)

    def _strategy_body(
        self,
        *,
        audience: str,
        internal_strategy: str,
        display_strategy: str,
        top_decision: dict[str, Any],
        top_issue: dict[str, Any],
        analysis_first_surface: bool,
        comparison_first_surface: bool,
        information_role: str = "",
        rationale_override: str = "",
    ) -> str:
        decision_type = str(top_decision.get("decision_type") or "-")
        rationale = rationale_override or str(top_decision.get("rationale") or "").strip() or str(top_issue.get("summary") or "-")
        if analysis_first_surface:
            if information_role == "diagnosis":
                return f"진단 기준은 {display_strategy}입니다. 불일치 가능성과 회계 영향만 정리합니다."
            if information_role == "decision":
                return f"비교 기준은 {display_strategy}입니다. 흐름 설명 대신 선택지, 추천안, 적용 검증 기준을 정리합니다."
            templates = {
                "developer": f"내부 taxonomy 전략은 {internal_strategy}이지만 사용자 노출 문구는 {display_strategy}입니다. 최상위 decision은 {decision_type}이고, 근거는 {rationale}입니다.",
                "manager": f"내부 권장 전략은 {internal_strategy}이지만 우선 검토 기준은 {display_strategy}입니다. 핵심 근거는 {rationale}이며, 개선 제안은 현행 구조 해석 이후에 배치합니다.",
                "client": f"내부 권장 전략은 {internal_strategy}이며 이번 결과는 {display_strategy} 기준으로 정리했습니다. 이유는 {rationale}이므로 개선 제안은 후속 검토로 다룹니다.",
            }
            return templates.get(audience, templates["manager"])
        if comparison_first_surface:
            templates = {
                "developer": f"내부 taxonomy 전략은 {internal_strategy}이지만 사용자 노출 문구는 {display_strategy}입니다. 최상위 decision은 {decision_type}이고, 비교 근거는 {rationale}입니다.",
                "manager": f"내부 권장 전략은 {internal_strategy}이지만 사용자 설명은 {display_strategy}입니다. 핵심 비교 근거는 {rationale}이며, 추천안은 동일 기준으로 비교한 뒤 제시합니다.",
                "client": f"내부 권장 전략은 {internal_strategy}이며 이번 결과는 {display_strategy} 기준으로 정리했습니다. 이유는 {rationale}이므로 추천안과 대안을 같은 축으로 비교합니다.",
            }
            return templates.get(audience, templates["manager"])
        templates = {
            "developer": f"추천 전략은 {internal_strategy}입니다. 최상위 decision은 {decision_type}로 분류되며, 근거는 {rationale}입니다.",
            "manager": f"현재 권장 전략은 {internal_strategy}이며, 사용자 설명은 {display_strategy}입니다. 최상위 판단은 {decision_type}이며, 핵심 근거는 {rationale}입니다.",
            "client": f"권장 방향은 {internal_strategy}이며, 사용자 설명은 {display_strategy}입니다. 최상위 판단 유형은 {decision_type}이고, 주된 이유는 {rationale}입니다.",
        }
        return templates.get(audience, templates["manager"])

    def _priority_body(self, *, audience: str, top_decision: dict[str, Any]) -> str:
        score = int(top_decision.get("priority_score") or 0)
        breakdown = top_decision.get("score_breakdown") or {}
        severity = int(breakdown.get("severity_component") or 0)
        blast_radius = int(breakdown.get("blast_radius_component") or 0)
        effort = int(breakdown.get("effort_component") or 0)
        explainability = top_decision.get("explainability") or {}
        score_summary = str(explainability.get("score_summary") or "").strip()
        templates = {
            "developer": (
                f"최상위 priority score는 {score}입니다. severity component는 {severity}, blast radius component는 {blast_radius}, "
                f"effort component는 {effort}이며, 계산 요약은 {score_summary}입니다."
            ),
            "manager": (
                f"최상위 우선순위 점수는 {score}입니다. severity {severity}, blast radius {blast_radius}, effort {effort}가 반영되었고, "
                f"계산 요약은 {score_summary}입니다."
            ),
            "client": (
                f"최우선 항목의 점수는 {score}입니다. severity {severity}, blast radius {blast_radius}, effort {effort}를 반영한 결과이며, "
                f"요약 근거는 {score_summary}입니다."
            ),
        }
        return templates.get(audience, templates["manager"])

    def _execution_body(
        self,
        *,
        audience: str,
        execution_stages: Any,
        top_stage: dict[str, Any],
        analysis_first_surface: bool,
        comparison_first_surface: bool,
        information_role: str = "",
    ) -> str:
        stages = execution_stages if isinstance(execution_stages, list) else []
        stage_count = len(stages)
        top_title = str(top_stage.get("title") or "-")
        if analysis_first_surface:
            if information_role == "diagnosis":
                return "리스크 범위는 기준 불일치, 회계 반영 누락, 취소·역처리 불일치입니다."
            if information_role == "decision":
                return f"적용 검증 단계는 총 {stage_count}개이며, 시작 단계는 {top_title}입니다. 추천 기준을 검증 항목으로 연결합니다."
            templates = {
                "developer": f"검토 단계는 {stage_count}개입니다. 시작 단계 제목은 {top_title}이며, 현행 객체와 처리 순서 복원이 우선입니다.",
                "manager": f"검토 단계는 총 {stage_count}개이며, 시작 단계는 {top_title}입니다. 현행 구조 복원을 먼저 진행합니다.",
                "client": f"검토 단계는 {stage_count}개로 정리되어 있고, 첫 단계는 {top_title}입니다. 현행 운영 흐름부터 확인합니다.",
            }
            return templates.get(audience, templates["manager"])
        if comparison_first_surface:
            templates = {
                "developer": f"도입 단계는 {stage_count}개입니다. 시작 단계 제목은 {top_title}이며, 비교 기준을 실행 순서로 고정하는 단계부터 시작합니다.",
                "manager": f"도입 단계는 총 {stage_count}개이며, 시작 단계는 {top_title}입니다. 추천안의 적용 순서를 먼저 고정합니다.",
                "client": f"도입 단계는 {stage_count}개로 정리되어 있고, 첫 단계는 {top_title}입니다. 추천안을 실행 순서로 옮기는 단계부터 시작합니다.",
            }
            return templates.get(audience, templates["manager"])
        templates = {
            "developer": f"실행 단계는 {stage_count}개입니다. 시작 단계 제목은 {top_title}입니다.",
            "manager": f"실행 단계는 총 {stage_count}개이며, 시작 단계는 {top_title}입니다.",
            "client": f"진행 단계는 {stage_count}개로 정리되어 있고, 첫 단계는 {top_title}입니다.",
        }
        return templates.get(audience, templates["manager"])

    def _scope_body(self, *, audience: str, coverage_summary: dict[str, Any]) -> str:
        asset_count = int(coverage_summary.get("asset_count") or 0)
        component_count = int(coverage_summary.get("component_count") or 0)
        slice_count = int(coverage_summary.get("slice_count") or 0)
        templates = {
            "developer": f"분석 범위는 asset {asset_count}개, component {component_count}개, feature slice {slice_count}개입니다.",
            "manager": f"이번 분석 범위는 자산 {asset_count}개, 컴포넌트 {component_count}개, 기능 슬라이스 {slice_count}개입니다.",
            "client": f"검토 범위는 자산 {asset_count}개, 컴포넌트 {component_count}개, 기능 슬라이스 {slice_count}개입니다.",
        }
        return templates.get(audience, templates["manager"])

    def _section_text(
        self,
        *,
        section_key: str,
        audience: str,
        result_package: dict[str, Any],
        polished_sections: dict[str, dict[str, Any]],
    ) -> str:
        deterministic_text = self._deterministic_fallback_text(section_key=section_key, result_package=result_package)
        validated_block_text = self._validated_block_text(section_key=section_key, result_package=result_package)
        if validated_block_text:
            return self._clean_presented_text(
                section_key=section_key,
                text=self._family_aware_section_text(
                    section_key=section_key,
                    result_package=result_package,
                    text=validated_block_text,
                    fallback_text=deterministic_text,
                ),
                external=False,
                result_package=result_package,
            )
        validated_narrative_text = self._validated_narrative_text(section_key=section_key, result_package=result_package)
        if validated_narrative_text:
            return self._clean_presented_text(
                section_key=section_key,
                text=self._family_aware_section_text(
                    section_key=section_key,
                    result_package=result_package,
                    text=validated_narrative_text,
                    fallback_text=deterministic_text,
                ),
                external=False,
                result_package=result_package,
            )
        polished = polished_sections.get(section_key) or {}
        audience_variants = polished.get("audience_variants") or {}
        if isinstance(audience_variants, dict):
            audience_text = str(audience_variants.get(audience) or "").strip()
            if audience_text:
                return self._clean_presented_text(
                    section_key=section_key,
                    text=self._family_aware_section_text(
                        section_key=section_key,
                        result_package=result_package,
                        text=audience_text,
                        fallback_text=deterministic_text,
                    ),
                    external=False,
                    result_package=result_package,
                )
        return self._clean_presented_text(
            section_key=section_key,
            text=self._family_aware_section_text(
                section_key=section_key,
                result_package=result_package,
                text=deterministic_text,
                fallback_text=deterministic_text,
            ),
            external=False,
            result_package=result_package,
        )

    def _family_aware_section_text(
        self,
        *,
        section_key: str,
        result_package: dict[str, Any],
        text: str,
        fallback_text: str,
    ) -> str:
        family = str(((result_package.get("family_classification") or {}) if isinstance(result_package, dict) else {}).get("family") or "").strip()
        if family != "operational_source":
            return str(text or "").strip()
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        fallback_lines = [line.strip() for line in str(fallback_text or "").splitlines() if line.strip()]
        rendered_lines = self.template_support.render_operational_section_lines(
            section_key=section_key,
            lines=lines,
            domain_override=str(result_package.get("narrative_axis") or "").strip(),
            fallback_lines=fallback_lines,
        )
        if package_information_role(result_package) == "diagnosis":
            rendered_lines = purify_diagnosis_lines(section_key, rendered_lines)
        if not rendered_lines:
            return str(fallback_text or text or "").strip()
        multi_line_sections = {"analysis_summary", "executive_summary_v2", "recommended_option", "execution_plan", "risks"}
        return "\n".join(rendered_lines) if section_key in multi_line_sections else rendered_lines[0]

    def _validated_block_text(self, *, section_key: str, result_package: dict[str, Any]) -> str:
        block = self._validated_block_map(result_package).get(section_key) or {}
        if not isinstance(block, dict):
            return ""
        lines = block.get("resolved_lines")
        if not isinstance(lines, list) or not lines:
            lines = block.get("deterministic_lines")
        if not isinstance(lines, list):
            return ""
        normalized = [str(item or "").strip() for item in lines if str(item or "").strip()]
        if not normalized:
            return ""
        return "\n".join(normalized) if section_key in {"analysis_summary", "executive_summary_v2", "recommended_option", "execution_plan", "risks"} else normalized[0]

    def _validated_narrative_text(self, *, section_key: str, result_package: dict[str, Any]) -> str:
        narrative_layer = result_package.get("validated_narrative_layer")
        if not isinstance(narrative_layer, dict):
            return ""
        value = narrative_layer.get(section_key)
        if isinstance(value, list):
            normalized = [str(item or "").strip() for item in value if str(item or "").strip()]
            return "\n".join(normalized)
        return str(value or "").strip()

    def _validated_block_map(self, result_package: dict[str, Any]) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for item in result_package.get("validated_explanation_blocks") or []:
            if not isinstance(item, dict):
                continue
            block_id = str(item.get("block_id") or "").strip()
            if block_id:
                output[block_id] = item
        return output

    def _wording_source(self, *, result_package: dict[str, Any], polish_bundle: dict[str, Any] | None) -> str:
        for section_key in (
            "report_purpose",
            "executive_summary_v2",
            "one_line_conclusion",
            "primary_judgment_reason",
            "recommended_option",
            "execution_plan",
            "risks",
        ):
            if self._validated_block_text(section_key=section_key, result_package=result_package):
                return "validated_explanation_blocks"
        for section_key in (
            "report_purpose",
            "executive_summary_v2",
            "one_line_conclusion",
            "analysis_summary",
            "primary_judgment_reason",
            "recommended_option",
            "execution_plan",
            "risks",
        ):
            if self._validated_narrative_text(section_key=section_key, result_package=result_package):
                return "validated_narrative_layer"
        if polish_bundle:
            return "polish_bundle.audience_variants"
        return "deterministic_fallback"

    def _narrative_guard_metadata(self, result_package: dict[str, Any]) -> dict[str, Any]:
        guard = result_package.get("narrative_guard_metadata")
        if isinstance(guard, dict):
            return guard
        fallback = result_package.get("fallback_narrative_metadata")
        return fallback if isinstance(fallback, dict) else {}

    def _external_recommended_option_text(self, result_package: dict[str, Any]) -> str:
        contract_text = self._contract_section_text(
            result_package=result_package,
            section_key="recommended_option",
            external=True,
        )
        if contract_text:
            return contract_text
        information_role = package_information_role(result_package)
        if information_role in {"structure", "diagnosis"}:
            return ""
        if information_role == "decision":
            lines = self._external_reason_lines(
                result_package=result_package,
                headline=str(self._contract_conclusion_lines(result_package)[0] if self._contract_conclusion_lines(result_package) else ""),
                reason=str((result_package.get("recommended_directions") or [""])[0] or ""),
                support=str(self._contract_lines(result_package, "decision_criteria")[0] if self._contract_lines(result_package, "decision_criteria") else ""),
                follow_up=str(self._contract_lines(result_package, "missing_information")[0] if self._contract_lines(result_package, "missing_information") else ""),
            )
            if lines:
                return "\n".join(lines)
            return "\n".join(self._external_reason_lines(result_package=result_package, headline="현행 FIFO 기준 유지", reason="환율 비교와 회계 연결 검증 유지"))
        option = self._preferred_option_payload(result_package)
        if not isinstance(option, dict):
            return ""
        option_name = self._compress_external_sentence(str(option.get("name") or "").strip())
        structure_summary = self._compress_external_sentence(str(option.get("structure_summary") or "").strip())
        selection_reason = self._compress_external_sentence(str(option.get("selection_reason") or "").strip())
        evidence_text = str(self._contract_lines(result_package, "evidence")[0] if self._contract_lines(result_package, "evidence") else "")
        missing_text = str(self._contract_lines(result_package, "missing_information")[0] if self._contract_lines(result_package, "missing_information") else "")
        headline = option_name or structure_summary
        reason = selection_reason or structure_summary
        support = evidence_text or str(self._contract_lines(result_package, "decision_criteria")[0] if self._contract_lines(result_package, "decision_criteria") else "")
        concise_lines = self._external_reason_lines(
            result_package=result_package,
            headline=headline,
            reason=reason,
            support=support,
            follow_up=missing_text,
        )
        if concise_lines:
            return "\n".join(concise_lines)
        if self._uses_analysis_first_surface(result_package):
            lines: list[str] = []
            outcomes = [str(item).strip() for item in option.get("expected_outcomes") or [] if str(item).strip()]
            if structure_summary:
                lines.append(f"현행 분석 뒤 {self._short_external_fragment(structure_summary)}를 검토합니다.")
            if selection_reason:
                lines.append(f"근거는 {self._short_external_fragment(selection_reason)}입니다.")
            for item in outcomes[:2]:
                normalized = self._compress_external_sentence(str(item))
                if normalized:
                    lines.append(f"효과는 {self._short_external_fragment(normalized)}입니다.")
            return "\n".join(lines)
        if self._uses_comparison_first_surface(result_package):
            lines: list[str] = []
            outcomes = [str(item).strip() for item in option.get("expected_outcomes") or option.get("advantages") or [] if str(item).strip()]
            if option_name and structure_summary:
                lines.append(f"{STATE_LABELS[self._planner_surface_state(result_package)]}: {self._short_external_fragment(option_name)}")
            elif option_name:
                lines.append(f"{STATE_LABELS[self._planner_surface_state(result_package)]}: {self._short_external_fragment(option_name)}")
            if selection_reason:
                lines.append(f"- 이유: {self._short_external_fragment(selection_reason)}")
            for item in outcomes[:2]:
                normalized = self._compress_external_sentence(str(item))
                if normalized:
                    lines.append(f"- 근거: {self._short_external_fragment(normalized)}")
            return "\n".join(lines)
        return ""

    def _external_execution_plan_text(self, result_package: dict[str, Any]) -> str:
        contract_text = self._contract_section_text(
            result_package=result_package,
            section_key="execution_plan",
            external=True,
        )
        if contract_text:
            return contract_text
        output: list[str] = []
        analysis_first_surface = self._uses_analysis_first_surface(result_package)
        comparison_first_surface = self._uses_comparison_first_surface(result_package)
        information_role = package_information_role(result_package)
        if information_role == "diagnosis":
            return ""
        for item in (result_package.get("execution_plan") or [])[:2]:
            if not isinstance(item, dict):
                continue
            week_label = str(item.get("week_label") or "").strip()
            goal = self._compress_external_sentence(str(item.get("goal") or "").strip())
            tasks = [str(task).strip() for task in item.get("tasks") or [] if str(task).strip()]
            if information_role == "diagnosis" and week_label and goal:
                output.append(f"{week_label}에는 {goal}을 기준으로 불일치 가능성과 영향을 확인합니다.")
            elif information_role == "decision" and week_label and goal:
                output.append(f"{week_label}에는 {goal}을 기준으로 추천안 적용 검증 항목을 정합니다.")
            elif analysis_first_surface and week_label and goal:
                output.append(f"{week_label}에는 {goal}을 중심으로 객체와 처리 순서를 정리합니다.")
            elif comparison_first_surface and week_label and goal:
                output.append(f"{week_label}에는 {goal}을 기준으로 추천안을 실제 적용 순서에 맞춥니다.")
            elif week_label and goal:
                output.append(f"{week_label}에는 {goal}을 먼저 맞춰 후속 변경 범위를 고정합니다.")
            elif goal:
                output.append(
                    f"{goal}을 먼저 맞추면 다음 단계 누락을 줄일 수 있습니다."
                    if not analysis_first_surface and not comparison_first_surface
                    else f"{goal}을 먼저 정리하면 현행 운영 흐름을 안정적으로 복원할 수 있습니다."
                    if analysis_first_surface
                    else f"{goal}을 먼저 정리하면 비교 결과를 실행 단계로 옮길 수 있습니다."
                )
            first_task = self._compress_external_sentence(tasks[0]) if tasks else ""
            if first_task:
                output.append(
                    f"이 단계에서 {first_task}를 확인하면 진단 근거가 정리됩니다."
                    if information_role == "diagnosis"
                    else f"이 단계에서 {first_task}를 정하면 추천안 적용 기준이 고정됩니다."
                    if information_role == "decision"
                    else f"이 단계에서 {first_task}를 확인하면 처리 순서가 정리됩니다."
                    if information_role == "structure"
                    else
                    f"이 단계에서 {first_task}를 정리하면 구현 흔들림을 줄일 수 있습니다."
                    if not analysis_first_surface and not comparison_first_surface
                    else f"이 단계에서 {first_task}를 확인하면 후속 개선 검토의 기준이 고정됩니다."
                    if analysis_first_surface
                    else f"이 단계에서 {first_task}를 맞추면 우선안의 적용 기준이 고정됩니다."
                )
        return "\n".join(output)

    def _external_risk_text(self, result_package: dict[str, Any]) -> str:
        contract_text = self._contract_section_text(
            result_package=result_package,
            section_key="risks",
            external=True,
        )
        if contract_text:
            return contract_text
        preferred = self._validated_block_text(section_key="risks", result_package=result_package)
        if not preferred:
            preferred = self._validated_narrative_text(section_key="risks", result_package=result_package)
        if preferred:
            source_lines = [line.strip() for line in str(preferred).splitlines() if line.strip()]
        else:
            source_lines = [
                str(risk).strip()
                for risk in (((result_package.get("diagnosis") or {}).get("risks") or []) if isinstance(result_package, dict) else [])
                if str(risk).strip()
            ]
        normalized = [self._compress_external_sentence(item) for item in source_lines]
        normalized = [item for item in normalized if item]
        return "\n".join(f"- {item}" for item in normalized[:2])

    def _surface_wording(self, result_package: dict[str, Any]) -> dict[str, Any]:
        extensions = result_package.get("extensions") if isinstance(result_package, dict) else {}
        extensions = extensions if isinstance(extensions, dict) else {}
        governance = extensions.get("decision_governance") if isinstance(extensions, dict) else {}
        governance = governance if isinstance(governance, dict) else {}
        wording = governance.get("surface_wording")
        return wording if isinstance(wording, dict) else {}

    def _surface_mode(self, result_package: dict[str, Any]) -> str:
        wording = self._surface_wording(result_package)
        return str(wording.get("mode") or "").strip()

    def _external_surface_style(self, result_package: dict[str, Any]) -> str:
        return INPUT_KIND_TO_STYLE[self._input_surface_kind(result_package)]

    def _input_surface_kind(self, result_package: dict[str, Any]) -> str:
        family = str(((result_package.get("family_classification") or {}) if isinstance(result_package, dict) else {}).get("family") or "").strip()
        if family == "operational_source":
            return "code"
        joined_text = "\n".join(self._surface_source_fragments(result_package)).lower()
        code_score = sum(1 for pattern in _CODE_INPUT_HINTS if re.search(pattern, joined_text, re.IGNORECASE))
        document_score = sum(1 for pattern in _DOCUMENT_INPUT_HINTS if re.search(pattern, joined_text, re.IGNORECASE))
        if code_score >= 4 and (document_score <= 2 or code_score >= document_score * 2):
            return "code"
        if code_score >= 3 and document_score >= 3:
            return "mixed"
        return "document"

    def _surface_source_fragments(self, result_package: dict[str, Any]) -> list[str]:
        fragments: list[str] = []
        report_scope = result_package.get("report_scope") if isinstance(result_package, dict) else []
        if isinstance(report_scope, list):
            fragments.extend(str(item).strip() for item in report_scope if str(item).strip())
        analysis_summary = result_package.get("analysis_summary") if isinstance(result_package, dict) else []
        if isinstance(analysis_summary, list):
            fragments.extend(str(item).strip() for item in analysis_summary[:6] if str(item).strip())
        contract = self._consulting_contract(result_package)
        for key in (
            "context",
            "problem_definition",
            "decision_question",
            "options",
            "decision_criteria",
            "evidence",
            "missing_information",
            "as_is",
            "process_flow",
            "rules",
            "risks",
            "actions",
        ):
            values = contract.get(key)
            if isinstance(values, list):
                fragments.extend(str(item).strip() for item in values[:4] if str(item).strip())
        authoritative = result_package.get("authoritative_payload") if isinstance(result_package, dict) else {}
        authoritative = authoritative if isinstance(authoritative, dict) else {}
        appendix = authoritative.get("appendix") if isinstance(authoritative, dict) else {}
        appendix = appendix if isinstance(appendix, dict) else {}
        for evidence in appendix.get("evidence_index") or []:
            if not isinstance(evidence, dict):
                continue
            locator = str(evidence.get("locator") or "").strip()
            excerpt = str(evidence.get("excerpt") or "").strip()
            if locator:
                fragments.append(locator)
            if excerpt:
                fragments.append(excerpt)
        return [fragment for fragment in fragments if fragment]

    def _display_strategy(self, *, result_package: dict[str, Any], fallback: str) -> str:
        wording = self._surface_wording(result_package)
        display = str(wording.get("display_strategy") or "").strip()
        if display:
            return display
        governance = ((result_package.get("extensions") or {}) if isinstance(result_package, dict) else {}).get("decision_governance")
        if isinstance(governance, dict):
            outline = governance.get("document_outline")
            if isinstance(outline, dict):
                outline_strategy = str(outline.get("recommended_strategy") or "").strip()
                if outline_strategy:
                    return outline_strategy
        return fallback

    def _uses_analysis_first_surface(self, result_package: dict[str, Any]) -> bool:
        return self._surface_mode(result_package) == "analysis_first_operational_source"

    def _uses_comparison_first_surface(self, result_package: dict[str, Any]) -> bool:
        return self._surface_mode(result_package) == "comparison_first_option"

    def _preferred_option_payload(self, result_package: dict[str, Any]) -> dict[str, Any]:
        option = result_package.get("recommended_option") if isinstance(result_package, dict) else {}
        if isinstance(option, dict) and any(str(option.get(key) or "").strip() for key in ("name", "structure_summary", "selection_reason")):
            return option
        design = result_package.get("design") if isinstance(result_package, dict) else {}
        design = design if isinstance(design, dict) else {}
        options = design.get("design_options")
        if not isinstance(options, list):
            return {}
        for item in options:
            if isinstance(item, dict) and bool(item.get("recommended")):
                return item
        for item in options:
            if isinstance(item, dict):
                return item
        return {}

    def _consulting_contract(self, result_package: dict[str, Any]) -> dict[str, list[str]]:
        contract = result_package.get("consulting_min_contract") if isinstance(result_package, dict) else {}
        return contract if isinstance(contract, dict) else {}

    def _uses_generic_consulting_contract(self, result_package: dict[str, Any]) -> bool:
        contract = self._consulting_contract(result_package)
        if not contract:
            return False
        family = str(((result_package.get("family_classification") or {}) if isinstance(result_package, dict) else {}).get("family") or "").strip()
        return family not in {"operational_source", "option_comparison"}

    def _contract_lines(self, result_package: dict[str, Any], field_name: str) -> list[str]:
        contract = self._consulting_contract(result_package)
        value = contract.get(field_name) if isinstance(contract, dict) else []
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _contract_conclusion_lines(self, result_package: dict[str, Any]) -> list[str]:
        conclusion_lines = self._contract_lines(result_package, "conclusion")[:1]
        missing_information = self._contract_lines(result_package, "missing_information")
        if not missing_information:
            if not conclusion_lines:
                return []
            state = self._planner_surface_state(result_package)
            if state == "assertive":
                return [f"{STATE_LABELS[state]}: {conclusion_lines[0]}"]
            if state == "conditional":
                return [f"{STATE_LABELS[state]}: {conclusion_lines[0]}"]
            return conclusion_lines
        if conclusion_lines:
            return [f"검증 후 적용: {conclusion_lines[0]}"]
        return ["추가 확인 후 재판단"]

    def _planner_surface_state(self, result_package: dict[str, Any]) -> str:
        extensions = result_package.get("extensions") if isinstance(result_package, dict) else {}
        extensions = extensions if isinstance(extensions, dict) else {}
        governance = extensions.get("decision_governance") if isinstance(extensions, dict) else {}
        governance = governance if isinstance(governance, dict) else {}
        planner_summary = governance.get("planner_summary") if isinstance(governance.get("planner_summary"), dict) else {}
        schedule_summary = governance.get("schedule_summary") if isinstance(governance.get("schedule_summary"), dict) else {}
        recommendation_strength = str(governance.get("recommendation_strength") or "").strip()
        first_stage_kind = str(planner_summary.get("first_stage_kind") or "").strip()
        schedule_mode = str(schedule_summary.get("schedule_mode") or "").strip()
        if bool(planner_summary.get("blocked_execution")) or recommendation_strength == "blocked":
            return "blocked"
        if first_stage_kind == "verification_first" or schedule_mode == "verification_first" or recommendation_strength == "review_required":
            return "review_required"
        if first_stage_kind == "precondition_check" or schedule_mode == "conditional_first" or recommendation_strength == "conditional":
            return "conditional"
        return "assertive"

    def _split_internal_label(self, text: str) -> tuple[str, str]:
        normalized = re.sub(r"^[-*]\s+", "", str(text or "").strip())
        match = re.match(r"^\[(?P<label>[^\]]+)\]\s*(?P<body>.+)$", normalized)
        if not match:
            return "", normalized
        return str(match.group("label") or "").strip(), str(match.group("body") or "").strip()

    def _line_dedupe_key(self, text: str) -> str:
        _, body = self._split_internal_label(text)
        normalized = body if body else str(text or "")
        normalized = re.sub(r"^[-*]\s+", "", normalized)
        normalized = re.sub(r"^(문제|검토 질문|선택지|기준|이유|추가 확인 필요|리스크|가정|근거|핵심 규칙|적용 방향|후속 판단 포인트)\s*:?\s*", "", normalized)
        normalized = re.sub(r"^(실행 착수 가능|조건 확인 후 실행|검증 후 적용|실행 불가)\s*:?\s*", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip().rstrip(".?!")
        return normalized.lower()

    def _short_external_fragment(self, text: str, *, max_length: int = 28) -> str:
        normalized = self._compress_external_sentence(text)
        if not normalized:
            return ""
        separators = ("입니다. ", "입니다 ", "이며 ", "이므로 ", ", ", " · ", " 및 ", "해서 ", "하고 ")
        for separator in separators:
            if len(normalized) <= max_length:
                break
            if separator in normalized:
                candidate = normalized.split(separator, 1)[0].strip(" ,.")
                if candidate:
                    normalized = candidate
        normalized = re.sub(r"\s+", " ", normalized).strip(" ,.")
        if len(normalized) <= max_length:
            return normalized
        clipped = normalized[: max_length + 1].rstrip()
        if " " in clipped:
            clipped = clipped.rsplit(" ", 1)[0].rstrip()
        return clipped.strip(" ,.")

    def _externalize_labeled_line(
        self,
        *,
        label: str,
        body: str,
        section_key: str,
        result_package: dict[str, Any] | None = None,
    ) -> str:
        normalized_body = self._compress_external_sentence(body)
        if not normalized_body:
            return ""
        if label == "결론":
            normalized_body = re.sub(r"^현 단계 우선 검토안:\s*", "", normalized_body).strip()
            normalized_body = re.sub(r"^우선 검토안:\s*", "", normalized_body).strip()
            prefix_match = re.match(r"^(실행 착수 가능|조건 확인 후 실행|검증 후 적용|실행 불가)\s*:?\s*", normalized_body)
            state_label = str(prefix_match.group(1) or "").strip() if prefix_match else STATE_LABELS[self._planner_surface_state(result_package or {})]
            if prefix_match:
                normalized_body = normalized_body[prefix_match.end():].strip()
            if normalized_body == "추가 확인 후 확정 필요":
                return "추가 확인 후 재판단"
            return f"{state_label}: {normalized_body}" if normalized_body else state_label
        prefix = EXTERNAL_LABEL_PREFIXES.get(label, "")
        return f"{prefix}{normalized_body}" if prefix else normalized_body

    def _clean_presented_text(
        self,
        *,
        section_key: str,
        text: str,
        external: bool,
        result_package: dict[str, Any] | None = None,
    ) -> str:
        raw_lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw_line in raw_lines:
            label, body = self._split_internal_label(raw_line)
            if external and label:
                candidate = self._externalize_labeled_line(
                    label=label,
                    body=body,
                    section_key=section_key,
                    result_package=result_package,
                )
            else:
                candidate = self._compress_external_sentence(raw_line) if external else raw_line
            candidate = candidate.strip()
            if not candidate:
                continue
            key = self._line_dedupe_key(candidate)
            if not key or key in seen:
                continue
            seen.add(key)
            cleaned.append(candidate)
        if external:
            line_limits = {
                "report_purpose": 2,
                "one_line_conclusion": 2,
                "analysis_summary": 2,
                "recommended_option": 3,
                "execution_plan": 3,
                "risks": 3,
                "executive_summary_v2": 3,
                "primary_judgment_reason": 3,
            }
            limit = line_limits.get(section_key, 0)
            if limit:
                cleaned = cleaned[:limit]
        return "\n".join(cleaned)

    def _external_reason_lines(
        self,
        *,
        result_package: dict[str, Any],
        headline: str = "",
        reason: str = "",
        support: str = "",
        follow_up: str = "",
    ) -> list[str]:
        state = self._planner_surface_state(result_package)
        state_label = STATE_LABELS[state]
        lines: list[str] = []
        normalized_headline = self._short_external_fragment(headline, max_length=30)
        normalized_headline = re.sub(r"^(실행 착수 가능|조건 확인 후 실행|검증 후 적용|실행 불가)\s*:?\s*", "", normalized_headline).strip()
        normalized_reason = self._short_external_fragment(reason, max_length=28)
        normalized_support = self._short_external_fragment(support, max_length=28)
        normalized_follow_up = self._short_external_fragment(follow_up, max_length=28)
        if normalized_headline:
            lines.append(f"- {state_label}: {normalized_headline}")
        elif state in {"blocked", "review_required", "conditional"}:
            lines.append(f"- {state_label}")
        if normalized_reason:
            lines.append(f"- 이유: {normalized_reason}")
        elif normalized_support and state == "assertive":
            lines.append(f"- 근거: {normalized_support}")
        if normalized_follow_up:
            lines.append(f"- 추가 확인 필요: {normalized_follow_up}")
        elif state == "blocked":
            lines.append("- 추가 확인 필요: 차단 요인 해소")
        elif state == "review_required":
            lines.append("- 추가 확인 필요: 근거와 충돌 검증")
        elif state == "conditional":
            lines.append("- 추가 확인 필요: 선행 조건 확인")
        elif normalized_support:
            lines.append(f"- 근거: {normalized_support}")
        deduped: list[str] = []
        seen: set[str] = set()
        for line in lines:
            key = self._line_dedupe_key(line)
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(line)
        return deduped[:3]

    def _technical_problem_lines(self, result_package: dict[str, Any]) -> list[str]:
        lines = self._prefixed_external_lines(
            "핵심 문제",
            self._contract_lines(result_package, "problem_definition")[:2]
            or self._contract_lines(result_package, "as_is")[:2]
            or list(result_package.get("analysis_summary") or [])[:2],
        )
        return lines or ["- 핵심 문제: 분석 대상 구조를 먼저 확인합니다"]

    def _technical_impact_lines(self, result_package: dict[str, Any]) -> list[str]:
        lines = self._prefixed_external_lines(
            "영향",
            self._contract_lines(result_package, "risks")[:2]
            or self._contract_lines(result_package, "gap")[:2]
            or self._contract_lines(result_package, "evidence")[:2],
        )
        return lines or ["- 영향: 구조 변경 영향 범위를 먼저 확인합니다"]

    def _technical_action_lines(self, result_package: dict[str, Any]) -> list[str]:
        state_label = STATE_LABELS[self._planner_surface_state(result_package)]
        output: list[str] = []
        conclusion = self._contract_conclusion_lines(result_package)[:1]
        if conclusion:
            headline = self._short_external_fragment(conclusion[0], max_length=32)
            headline = re.sub(r"^(실행 착수 가능|조건 확인 후 실행|검증 후 적용|실행 불가)\s*:?\s*", "", headline).strip()
            if headline:
                output.append(f"- {state_label}: {headline}")
        output.extend(self._prefixed_external_lines("권장 조치", self._contract_lines(result_package, "actions")[:2], max_lines=2))
        return output[:3] or [f"- {state_label}: 권장 조치를 정리합니다"]

    def _technical_verification_lines(self, result_package: dict[str, Any]) -> list[str]:
        lines = self._prefixed_external_lines(
            "검증 포인트",
            self._contract_lines(result_package, "missing_information")[:2]
            or self._contract_lines(result_package, "rules")[:2]
            or self._contract_lines(result_package, "process_flow")[:2],
        )
        return lines or ["- 검증 포인트: 추가 확인 기준을 먼저 정리합니다"]

    def _prefixed_external_lines(self, prefix: str, items: list[Any], *, max_lines: int = 3) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for item in items or []:
            normalized = self._short_external_fragment(str(item).strip(), max_length=32)
            normalized = re.sub(r"^(실행 착수 가능|조건 확인 후 실행|검증 후 적용|실행 불가)\s*:?\s*", "", normalized).strip()
            if not normalized:
                continue
            rendered = f"- {prefix}: {normalized}"
            key = self._line_dedupe_key(rendered)
            if not key or key in seen:
                continue
            seen.add(key)
            output.append(rendered)
            if len(output) >= max_lines:
                break
        return output

    def _grouped_contract_text(
        self,
        *,
        result_package: dict[str, Any],
        groups: list[tuple[str, list[str]]],
        external: bool = False,
    ) -> str:
        lines: list[str] = []
        for label, items in groups:
            normalized_items: list[str] = []
            for item in items or []:
                normalized = str(item or "").strip()
                if not normalized:
                    continue
                if external:
                    normalized = self._compress_external_sentence(normalized)
                if normalized:
                    normalized_items.append(normalized)
            for index, item in enumerate(normalized_items):
                rendered = f"[{label}] {item}" if index == 0 else item
                lines.append(f"- {rendered}")
        return "\n".join(lines)

    def _contract_section_text(self, *, result_package: dict[str, Any], section_key: str, external: bool = False) -> str:
        if not self._uses_generic_consulting_contract(result_package):
            return ""
        if external:
            if section_key == "report_purpose":
                return self._clean_presented_text(
                    section_key=section_key,
                    text=self._grouped_contract_text(
                        result_package=result_package,
                        groups=[
                            ("상황 / 목적", self._contract_lines(result_package, "context")[:1]),
                            ("문제 정의", self._contract_lines(result_package, "problem_definition")[:1]),
                        ],
                        external=True,
                    ),
                    external=True,
                    result_package=result_package,
                )
            if section_key == "one_line_conclusion":
                return self._clean_presented_text(
                    section_key=section_key,
                    text=self._grouped_contract_text(
                        result_package=result_package,
                        groups=[
                            ("판단 질문", self._contract_lines(result_package, "decision_question")[:1]),
                            ("결론", self._contract_conclusion_lines(result_package)[:1]),
                        ],
                        external=True,
                    ),
                    external=True,
                    result_package=result_package,
                )
            if section_key == "analysis_summary":
                return self._clean_presented_text(
                    section_key=section_key,
                    text=self._grouped_contract_text(
                        result_package=result_package,
                        groups=[("근거", self._contract_lines(result_package, "evidence")[:2])],
                        external=True,
                    ),
                    external=True,
                    result_package=result_package,
                )
            if section_key == "recommended_option":
                lines = self._external_reason_lines(
                    result_package=result_package,
                    headline=str(self._contract_conclusion_lines(result_package)[0] if self._contract_conclusion_lines(result_package) else ""),
                    reason=str(self._contract_lines(result_package, "key_reasons")[0] if self._contract_lines(result_package, "key_reasons") else ""),
                    support=str(self._contract_lines(result_package, "evidence")[0] if self._contract_lines(result_package, "evidence") else self._contract_lines(result_package, "decision_criteria")[0] if self._contract_lines(result_package, "decision_criteria") else ""),
                    follow_up=str(self._contract_lines(result_package, "missing_information")[0] if self._contract_lines(result_package, "missing_information") else ""),
                )
                return self._clean_presented_text(
                    section_key=section_key,
                    text="\n".join(lines),
                    external=True,
                    result_package=result_package,
                )
            if section_key == "execution_plan":
                return self._clean_presented_text(
                    section_key=section_key,
                    text=self._grouped_contract_text(
                        result_package=result_package,
                        groups=[
                            ("단계별 추진 흐름", self._contract_lines(result_package, "process_flow")[:2]),
                            ("중점 실행 과제", self._contract_lines(result_package, "actions")[:1]),
                        ],
                        external=True,
                    ),
                    external=True,
                    result_package=result_package,
                )
            if section_key == "risks":
                return self._clean_presented_text(
                    section_key=section_key,
                    text=self._grouped_contract_text(
                        result_package=result_package,
                        groups=[
                            ("누락된 정보", self._contract_lines(result_package, "missing_information")[:1]),
                            ("리스크", self._contract_lines(result_package, "risks")[:1]),
                            ("숨겨진 전제 / 가정", self._contract_lines(result_package, "assumptions")[:1]),
                        ],
                        external=True,
                    ),
                    external=True,
                    result_package=result_package,
                )
        if section_key == "report_purpose":
            return self._grouped_contract_text(
                result_package=result_package,
                groups=[
                    ("상황 / 목적", self._contract_lines(result_package, "context")),
                    ("문제 정의", self._contract_lines(result_package, "problem_definition")),
                ],
                external=external,
            )
        if section_key == "one_line_conclusion":
            return self._grouped_contract_text(
                result_package=result_package,
                groups=[
                    ("판단 질문", self._contract_lines(result_package, "decision_question")),
                    ("결론", self._contract_conclusion_lines(result_package)),
                ],
                external=external,
            )
        if section_key == "analysis_summary":
            return self._grouped_contract_text(
                result_package=result_package,
                groups=[("근거", self._contract_lines(result_package, "evidence"))],
                external=external,
            )
        if section_key == "recommended_option":
            groups = [
                ("선택지 비교", self._contract_lines(result_package, "options")),
                ("판단 기준", self._contract_lines(result_package, "decision_criteria")),
            ]
            if external:
                groups.append(("결론", self._contract_conclusion_lines(result_package)))
            groups.append(("핵심 이유", self._contract_lines(result_package, "key_reasons")))
            return self._grouped_contract_text(
                result_package=result_package,
                groups=groups,
                external=external,
            )
        if section_key == "execution_plan":
            return self._grouped_contract_text(
                result_package=result_package,
                groups=[
                    ("단계별 추진 흐름", self._contract_lines(result_package, "process_flow")),
                    ("중점 실행 과제", self._contract_lines(result_package, "actions")),
                ],
                external=external,
            )
        if section_key == "risks":
            return self._grouped_contract_text(
                result_package=result_package,
                groups=[
                    ("숨겨진 전제 / 가정", self._contract_lines(result_package, "assumptions")),
                    ("누락된 정보", self._contract_lines(result_package, "missing_information")),
                    ("리스크", self._contract_lines(result_package, "risks")),
                ],
                external=external,
            )
        return ""

    def _section_title(self, *, result_package: dict[str, Any], section_key: str, fallback: str | None = None) -> str:
        wording = self._surface_wording(result_package)
        titles = wording.get("section_titles") if isinstance(wording, dict) else {}
        if isinstance(titles, dict):
            title = str(titles.get(section_key) or "").strip()
            if title:
                return title
        return fallback or SECTION_TITLES.get(section_key, section_key)

    def _summary_card_title(self, *, result_package: dict[str, Any], card_key: str, fallback: str) -> str:
        wording = self._surface_wording(result_package)
        titles = wording.get("summary_card_titles") if isinstance(wording, dict) else {}
        if isinstance(titles, dict):
            title = str(titles.get(card_key) or "").strip()
            if title:
                return title
        return fallback

    def _compress_external_sentence(self, text: str) -> str:
        normalized = " ".join(str(text or "").split()).strip()
        if not normalized:
            return ""
        normalized = normalized.rstrip(".")
        normalized = re.sub(
            r"^(실행 착수 가능|조건 확인 후 실행|검증 후 적용|실행 불가)\s*:?\s*(?:\1\s*:?\s*)+",
            lambda match: f"{match.group(1)}: ",
            normalized,
        )
        normalized = normalized.replace("추가 검토 전까지 실행 후보로만 유지합니다.", "검증 후 적용 상태로 유지합니다")
        normalized = normalized.replace("추가 검토 전까지는 실행보다 근거와 충돌 검증이 우선입니다.", "검증 후 적용 단계이므로 근거와 충돌을 먼저 확인합니다")
        normalized = normalized.replace("입력 자산이 제한적이므로 제안은 설계 초안 수준이며 추가 파일 확인이 필요합니다.", "입력 자산이 제한적이므로 추가 파일 확인이 먼저 필요합니다")
        normalized = normalized.replace("우선 검토안", "적용 방향")
        normalized = normalized.replace("검토안", "적용 방향")
        normalized = normalized.replace("개선 후보", "개선안")
        normalized = normalized.replace("후속 개선 후보", "후속 개선안")
        normalized = normalized.replace("후보", "대상")
        normalized = re.sub(r"^(따라서|즉|그리고)\s+", "", normalized)
        normalized = re.sub(r"([가-힣A-Za-z0-9_]+)해야\s+하므로", r"\1하면", normalized)
        normalized = re.sub(r"([가-힣A-Za-z0-9_]+)해야", r"\1하면", normalized)
        normalized = normalized.replace("해야 합니다", "")
        normalized = normalized.replace("해야합니다", "")
        normalized = normalized.replace("해야 한다", "")
        normalized = normalized.replace("검토하는 것이 필요합니다", "")
        normalized = normalized.replace("확정하는 것이 필요합니다", "")
        normalized = normalized.replace("정리하는 것이 필요합니다", "")
        normalized = normalized.replace("확인하는 것이 필요합니다", "")
        normalized = normalized.replace("필요합니다", "")
        normalized = normalized.strip(" ,")
        return normalized

    def _externalize_citations(self, citations: list[ResultCitation]) -> list[ResultCitation]:
        return [ResultCitation() for _ in citations]

    def _deterministic_fallback_text(self, *, section_key: str, result_package: dict[str, Any]) -> str:
        contract_text = self._contract_section_text(result_package=result_package, section_key=section_key)
        if contract_text:
            return contract_text
        if section_key == "report_purpose":
            return str(result_package.get("report_purpose") or "").strip()
        if section_key == "executive_summary_v2":
            executive_summary = result_package.get("executive_summary_v2") or []
            return "\n".join(f"- {str(item).strip()}" for item in executive_summary if str(item).strip())
        if section_key == "one_line_conclusion":
            return str(result_package.get("core_conclusion") or "").strip()
        if section_key == "analysis_summary":
            analysis_summary = result_package.get("analysis_summary") or []
            return "\n".join(f"- {str(item).strip()}" for item in analysis_summary if str(item).strip())
        if section_key == "primary_judgment_reason":
            return str(result_package.get("primary_judgment_reason") or "").strip()
        if section_key == "recommended_option":
            information_role = package_information_role(result_package)
            if information_role in {"structure", "diagnosis"}:
                return ""
            if information_role == "decision":
                lines = [
                    str(item).strip()
                    for item in (result_package.get("recommended_directions") or [])
                    if str(item).strip()
                ]
                if lines:
                    return "\n".join(f"- {line}" for line in lines[:3])
                return "- 추천안은 현행 FIFO 기준을 유지하고 환율 비교와 회계 연결 검증을 함께 두는 것입니다."
            option = result_package.get("recommended_option") or {}
            if not isinstance(option, dict):
                return ""
            parts = [
                str(option.get("name") or "").strip(),
                str(option.get("structure_summary") or "").strip(),
                str(option.get("selection_reason") or "").strip(),
            ]
            parts.extend(str(item).strip() for item in option.get("expected_outcomes") or [] if str(item).strip())
            return "\n".join(f"- {part}" for part in parts if part)
        if section_key == "execution_plan":
            if package_information_role(result_package) == "diagnosis":
                return ""
            if self._uses_analysis_first_surface(result_package) or self._uses_comparison_first_surface(result_package):
                return self._external_execution_plan_text(result_package)
            lines: list[str] = []
            for item in result_package.get("execution_plan") or []:
                if not isinstance(item, dict):
                    continue
                week_label = str(item.get("week_label") or "").strip()
                goal = str(item.get("goal") or "").strip()
                if week_label and goal:
                    lines.append(f"- {week_label}: {goal}")
                lines.extend(f"  - {str(task).strip()}" for task in item.get("tasks") or [] if str(task).strip())
            return "\n".join(lines)
        if section_key == "risks":
            risks = ((result_package.get("diagnosis") or {}).get("risks") or []) if isinstance(result_package, dict) else []
            return "\n".join(f"- {str(risk).strip()}" for risk in risks if str(risk).strip())
        return ""

    def _narrative_extension(self, polish_bundle: dict[str, Any] | None) -> dict[str, Any]:
        if not polish_bundle:
            return {}
        original_result = polish_bundle.get("original_result") or {}
        if not isinstance(original_result, dict):
            return {}
        extensions = original_result.get("extensions") or {}
        if not isinstance(extensions, dict):
            return {}
        narrative = extensions.get("narrative") or {}
        return narrative if isinstance(narrative, dict) else {}

    def _review_diff_preview(self, review_diff: dict[str, Any] | None) -> ResultExplanationReviewDiffPreview:
        if not isinstance(review_diff, dict):
            return ResultExplanationReviewDiffPreview()
        structural_diff = review_diff.get("structural_diff") if isinstance(review_diff.get("structural_diff"), dict) else {}
        evidence_diff = review_diff.get("evidence_diff") if isinstance(review_diff.get("evidence_diff"), dict) else {}
        decision_diff = review_diff.get("decision_diff") if isinstance(review_diff.get("decision_diff"), dict) else {}
        return ResultExplanationReviewDiffPreview(
            available=True,
            structural_signals=self._review_diff_structural_signals(structural_diff),
            evidence_signals=self._review_diff_evidence_signals(evidence_diff),
            blocked_decisions=self._review_diff_blocked_decisions(decision_diff),
            synthetic_signal_detected=bool(decision_diff.get("synthetic_signal_detected")),
            decision_engine_guard_applied=bool(decision_diff.get("decision_engine_guard_applied")),
            result_packager_guard_applied=bool(decision_diff.get("result_packager_guard_applied")),
        )

    def _review_diff_structural_signals(self, structural_diff: dict[str, Any]) -> list[str]:
        output: list[str] = []
        for item in structural_diff.get("layer_boundary_notes") or []:
            if not isinstance(item, dict):
                continue
            note = str(item.get("note") or "").strip()
            if note:
                output.append(note)
        if not output:
            for item in structural_diff.get("dependency_flows") or []:
                flow = str(item).strip()
                if flow:
                    output.append(flow)
        if not output:
            for item in structural_diff.get("data_flow_notes") or []:
                if not isinstance(item, dict):
                    continue
                slice_name = str(item.get("slice") or "-").strip()
                components = ", ".join(str(component).strip() for component in item.get("components") or [] if str(component).strip())
                data_stores = ", ".join(str(store).strip() for store in item.get("data_stores") or [] if str(store).strip())
                output.append(f"{slice_name} -> components={components or '-'} -> data_stores={data_stores or '-'}")
        return output[:3]

    def _review_diff_evidence_signals(self, evidence_diff: dict[str, Any]) -> list[str]:
        output: list[str] = []
        for item in evidence_diff.get("repeated_fingerprints") or []:
            if not isinstance(item, dict):
                continue
            alias = str(item.get("fingerprint_alias") or "").strip()
            occurrence_count = int(item.get("occurrence_count") or 0)
            if alias:
                output.append(f"{alias} repeated at {occurrence_count} locations")
        if not output:
            for item in evidence_diff.get("detector_evidence_map") or []:
                if not isinstance(item, dict):
                    continue
                detector_id = str(item.get("detector_id") or "").strip()
                location_count = len(item.get("locations") or [])
                if detector_id:
                    output.append(f"{detector_id} -> {location_count} locations")
        return output[:3]

    def _review_diff_blocked_decisions(self, decision_diff: dict[str, Any]) -> list[str]:
        output: list[str] = []
        for item in decision_diff.get("blocked_decisions") or []:
            if not isinstance(item, dict):
                continue
            decision_type = str(item.get("decision_type") or "").strip()
            downgraded_to = str(item.get("downgraded_to") or "").strip()
            if decision_type and downgraded_to:
                output.append(f"{decision_type} -> {downgraded_to}")
            elif decision_type:
                output.append(decision_type)
        return output[:3]
