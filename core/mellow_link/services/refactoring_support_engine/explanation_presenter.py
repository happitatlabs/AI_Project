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
        analysis_first_surface: bool,
        comparison_first_surface: bool,
        information_role: str = "",
    ) -> str:
        if analysis_first_surface:
            if information_role == "diagnosis":
                return "이번 결과는 전표/GL 연계의 불일치 가능성과 회계 영향을 진단하는 문서입니다."
            if information_role == "decision":
                return "이번 결과는 계산 기준 선택지를 비교해 추천안을 정하는 문서입니다."
            return f"이번 결과는 {display_strategy} 기준으로 자산 정체와 현행 처리 흐름을 먼저 복원하는 분석 성격입니다."
        if comparison_first_surface:
            return f"이번 결과는 {display_strategy} 기준으로 복수 선택지를 비교해 우선 검토안을 정하는 판단 성격입니다."
        label = self._humanize_structural_judgment(structural_judgment)
        strategy = display_strategy or "리팩터링 우선"
        return f"현재 구조는 {label} 성격이 강해, {strategy} 방향이 변경 영향을 더 작게 유지합니다."

    def _external_strategy_body(
        self,
        *,
        display_strategy: str,
        top_decision: dict[str, Any],
        top_issue: dict[str, Any],
        analysis_first_surface: bool,
        comparison_first_surface: bool,
        information_role: str = "",
        rationale_override: str = "",
    ) -> str:
        rationale = self._compress_external_sentence(
            rationale_override or str(top_decision.get("rationale") or "").strip() or str(top_issue.get("summary") or "").strip()
        )
        if analysis_first_surface:
            if information_role == "diagnosis":
                return f"진단 기준은 {display_strategy}입니다. 전표/GL 기준 불일치 가능성과 회계 영향만 정리합니다."
            if information_role == "decision":
                return f"비교 기준은 {display_strategy}입니다. 선택지와 추천안을 같은 기준으로 좁힙니다."
            if rationale:
                return f"우선 검토 기준은 {display_strategy}입니다. {rationale}부터 확인해야 개선안도 실제 운영 근거 위에서 비교할 수 있습니다."
            return f"우선 검토 기준은 {display_strategy}입니다. 핵심 객체와 처리 흐름을 먼저 정리한 뒤 개선 후보를 비교합니다."
        if comparison_first_surface:
            if rationale:
                return f"추천 기준은 {display_strategy}입니다. {rationale}를 같은 축으로 비교해야 선택지 간 차이가 흐려지지 않습니다."
            return f"추천 기준은 {display_strategy}입니다. 같은 기준으로 선택지를 나란히 비교해 우선안을 정리합니다."
        if rationale:
            return f"문제의 중심이 {rationale}에 있어, {display_strategy} 방향이 회귀 범위를 줄입니다."
        return f"{display_strategy} 방향은 책임 경계를 나눠 변경 범위를 작게 유지합니다."

    def _external_execution_body(
        self,
        *,
        top_stage: dict[str, Any],
        top_decision: dict[str, Any],
        analysis_first_surface: bool,
        comparison_first_surface: bool,
        information_role: str = "",
    ) -> str:
        stage_title = self._compress_external_sentence(str(top_stage.get("title") or "").strip())
        rationale = self._compress_external_sentence(str(top_decision.get("rationale") or "").strip())
        if analysis_first_surface:
            if information_role == "diagnosis":
                return "리스크 범위는 전표 기준과 회계 연결 기준이 달라질 때 발생하는 불일치와 회계 영향입니다."
            if information_role == "decision":
                if stage_title:
                    return f"첫 단계에서는 {stage_title}를 기준으로 추천안 적용 검증 항목을 정합니다."
                return "첫 단계에서는 계산 기준 선택지와 추천안 적용 검증 항목을 정합니다."
            if stage_title:
                return f"첫 단계에서는 {stage_title}를 기준으로 핵심 객체와 처리 순서를 정리합니다."
            return "첫 단계에서는 핵심 객체와 데이터 반영 순서를 정리해 현행 운영 흐름을 복원합니다."
        if comparison_first_surface:
            if stage_title and rationale:
                return f"첫 단계에서 {stage_title}를 먼저 맞추면, {rationale}에 연결된 추천 기준을 실행 순서로 고정할 수 있습니다."
            if stage_title:
                return f"첫 단계에서 {stage_title}를 먼저 맞추면, 비교 결과를 실제 적용 순서로 옮길 수 있습니다."
            return "첫 단계에서 추천 기준과 적용 순서를 먼저 맞추면, 우선안이 실행 단계에서도 흔들리지 않습니다."
        if stage_title and rationale:
            return f"첫 단계에서 {stage_title}를 먼저 정하면, {rationale}와 연결된 변경 범위가 흔들리지 않습니다."
        if stage_title:
            return f"첫 단계에서 {stage_title}를 먼저 정하면, 후속 변경 순서가 더 안정적으로 고정됩니다."
        return "첫 단계에서 범위와 책임 경계를 먼저 정하면, 후속 설계와 구현 범위가 흔들리지 않습니다."

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
        return [
            ResultExplanationSummaryCard(
                card_key="judgment",
                title=self._summary_card_title(result_package=result_package, card_key="judgment", fallback="핵심 판단"),
                body=self._external_judgment_body(
                    structural_judgment=structural_judgment,
                    display_strategy=display_strategy,
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
        if information_role == "diagnosis":
            return self._diagnosis_section_views(
                audience=audience,
                result_package=result_package,
                polished_sections={},
                strategy_citations=strategy_citations,
                risk_citations=risk_citations,
            )

        sections: list[ResultExplanationSectionView] = []
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
                    text=self._external_recommended_option_text(result_package),
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
                        else "진행 흐름"
                    ),
                    audience=audience,
                    text=self._external_execution_plan_text(result_package),
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
                    text=self._external_risk_text(result_package),
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
            return self._family_aware_section_text(
                section_key=section_key,
                result_package=result_package,
                text=validated_block_text,
                fallback_text=deterministic_text,
            )
        validated_narrative_text = self._validated_narrative_text(section_key=section_key, result_package=result_package)
        if validated_narrative_text:
            return self._family_aware_section_text(
                section_key=section_key,
                result_package=result_package,
                text=validated_narrative_text,
                fallback_text=deterministic_text,
            )
        polished = polished_sections.get(section_key) or {}
        audience_variants = polished.get("audience_variants") or {}
        if isinstance(audience_variants, dict):
            audience_text = str(audience_variants.get(audience) or "").strip()
            if audience_text:
                return self._family_aware_section_text(
                    section_key=section_key,
                    result_package=result_package,
                    text=audience_text,
                    fallback_text=deterministic_text,
                )
        return self._family_aware_section_text(
            section_key=section_key,
            result_package=result_package,
            text=deterministic_text,
            fallback_text=deterministic_text,
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
            lines = [
                str(item).strip()
                for item in (result_package.get("recommended_directions") or [])
                if str(item).strip()
            ]
            if lines:
                return "\n".join(lines[:3])
            return "추천안은 현행 FIFO 기준을 유지하고 환율 비교와 회계 연결 검증을 함께 두는 것입니다."
        option = self._preferred_option_payload(result_package)
        if not isinstance(option, dict):
            return ""
        if self._uses_analysis_first_surface(result_package):
            lines: list[str] = []
            structure_summary = self._compress_external_sentence(str(option.get("structure_summary") or "").strip())
            selection_reason = self._compress_external_sentence(str(option.get("selection_reason") or "").strip())
            outcomes = [str(item).strip() for item in option.get("expected_outcomes") or [] if str(item).strip()]
            if structure_summary:
                lines.append(f"현행 분석 이후에는 {structure_summary} 같은 개선 후보를 후속 검토할 수 있습니다.")
            if selection_reason:
                lines.append(f"개선안 비교 기준은 {selection_reason}입니다.")
            for item in outcomes[:2]:
                normalized = self._compress_external_sentence(str(item))
                if normalized:
                    lines.append(f"후속 개선 후보를 적용하면 {normalized}.")
            return "\n".join(lines)
        if self._uses_comparison_first_surface(result_package):
            lines: list[str] = []
            option_name = self._compress_external_sentence(str(option.get("name") or "").strip())
            structure_summary = self._compress_external_sentence(str(option.get("structure_summary") or "").strip())
            selection_reason = self._compress_external_sentence(str(option.get("selection_reason") or "").strip())
            outcomes = [str(item).strip() for item in option.get("expected_outcomes") or option.get("advantages") or [] if str(item).strip()]
            if option_name and structure_summary:
                lines.append(f"우선 검토안은 {option_name}이며, {structure_summary}를 기준으로 비교했습니다.")
            elif option_name:
                lines.append(f"우선 검토안은 {option_name}입니다.")
            if selection_reason:
                lines.append(f"추천 근거는 {selection_reason}")
            for item in outcomes[:2]:
                normalized = self._compress_external_sentence(str(item))
                if normalized:
                    lines.append(f"이 안을 택하면 {normalized}.")
            return "\n".join(lines)
        lines: list[str] = []
        structure_summary = self._compress_external_sentence(str(option.get("structure_summary") or "").strip())
        selection_reason = self._compress_external_sentence(str(option.get("selection_reason") or "").strip())
        outcomes = [str(item).strip() for item in option.get("expected_outcomes") or [] if str(item).strip()]
        if structure_summary:
            lines.append(f"이 방향은 {structure_summary}를 중심으로 경계를 나눠 변경 범위를 줄입니다.")
        if outcomes:
            for item in outcomes[:2]:
                normalized = self._compress_external_sentence(str(item))
                if normalized:
                    lines.append(f"그 결과 {normalized}.")
        elif selection_reason:
            lines.append(f"그 이유는 {selection_reason}이 변경 영향을 크게 만들기 때문입니다.")
        return "\n".join(lines)

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
            return conclusion_lines
        if conclusion_lines:
            return [f"현 단계 우선 검토안: {conclusion_lines[0]}"]
        return ["추가 확인 후 확정 필요"]

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
