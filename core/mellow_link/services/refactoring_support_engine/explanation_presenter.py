from __future__ import annotations

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


SECTION_TITLES: dict[str, str] = {
    "report_purpose": "보고 목적",
    "one_line_conclusion": "핵심 결론",
    "recommended_option": "추천안",
    "execution_plan": "실행 계획",
    "risks": "리스크",
}


class ExplanationPresenter:
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

        decision_summary = authoritative.get("decision_summary") or {}
        diagnosis_report = authoritative.get("diagnosis_report") or {}
        structure_snapshot = authoritative.get("structure_snapshot") or {}
        improvement_plan_bundle = authoritative.get("improvement_plan_bundle") or {}
        appendix = authoritative.get("appendix") or {}

        top_decision = self._first_list_item(decision_summary.get("decisions"))
        top_issue = self._first_list_item(diagnosis_report.get("issues"))
        top_stage = self._first_list_item(improvement_plan_bundle.get("execution_stages"))
        coverage_summary = structure_snapshot.get("coverage_summary") or {}
        evidence_map = self._evidence_map(appendix.get("evidence_index"))
        issue_map = self._issue_map(diagnosis_report.get("issues"))
        structural_judgment = str(result_package.get("structural_judgment") or "").strip()
        narrative_axis = str(result_package.get("narrative_axis") or "").strip()

        strategy_citations = self._decision_citations(top_decision, evidence_map=evidence_map, issue_map=issue_map)
        stage_citations = self._stage_citations(top_stage, top_decision=top_decision, evidence_map=evidence_map, issue_map=issue_map)
        scope_citations = self._scope_citations(structure_snapshot, evidence_map=evidence_map)
        risk_citations = self._risk_citations(improvement_plan_bundle, top_decision=top_decision, evidence_map=evidence_map, issue_map=issue_map)

        summary_cards = [
            ResultExplanationSummaryCard(
                card_key="judgment",
                title=AUDIENCE_LABELS[normalized_audience]["judgment"],
                body=self._judgment_body(
                    audience=normalized_audience,
                    structural_judgment=structural_judgment,
                    recommended_strategy=str(decision_summary.get("recommended_strategy") or "-"),
                    top_decision=top_decision,
                ),
                citations=strategy_citations,
            ),
            ResultExplanationSummaryCard(
                card_key="strategy",
                title=AUDIENCE_LABELS[normalized_audience]["strategy"],
                body=self._strategy_body(
                    audience=normalized_audience,
                    recommended_strategy=str(decision_summary.get("recommended_strategy") or "-"),
                    top_decision=top_decision,
                    top_issue=top_issue,
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
                title=AUDIENCE_LABELS[normalized_audience]["execution"],
                body=self._execution_body(
                    audience=normalized_audience,
                    execution_stages=improvement_plan_bundle.get("execution_stages"),
                    top_stage=top_stage,
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

        section_views: list[ResultExplanationSectionView] = []
        section_views.append(
            ResultExplanationSectionView(
                section_key="report_purpose",
                title=SECTION_TITLES["report_purpose"],
                audience=normalized_audience,
                text=self._section_text(
                    section_key="report_purpose",
                    audience=normalized_audience,
                    result_package=result_package,
                    polished_sections=polished_sections,
                ),
                citations=strategy_citations,
            )
        )
        section_views.append(
            ResultExplanationSectionView(
                section_key="one_line_conclusion",
                title=SECTION_TITLES["one_line_conclusion"],
                audience=normalized_audience,
                text=self._section_text(
                    section_key="one_line_conclusion",
                    audience=normalized_audience,
                    result_package=result_package,
                    polished_sections=polished_sections,
                ),
                citations=strategy_citations,
            )
        )
        section_views.append(
            ResultExplanationSectionView(
                section_key="recommended_option",
                title=SECTION_TITLES["recommended_option"],
                audience=normalized_audience,
                text=self._section_text(
                    section_key="recommended_option",
                    audience=normalized_audience,
                    result_package=result_package,
                    polished_sections=polished_sections,
                ),
                citations=strategy_citations,
            )
        )
        section_views.append(
            ResultExplanationSectionView(
                section_key="execution_plan",
                title=SECTION_TITLES["execution_plan"],
                audience=normalized_audience,
                text=self._section_text(
                    section_key="execution_plan",
                    audience=normalized_audience,
                    result_package=result_package,
                    polished_sections=polished_sections,
                ),
                citations=stage_citations,
            )
        )
        section_views.append(
            ResultExplanationSectionView(
                section_key="risks",
                title=SECTION_TITLES["risks"],
                audience=normalized_audience,
                text=self._section_text(
                    section_key="risks",
                    audience=normalized_audience,
                    result_package=result_package,
                    polished_sections=polished_sections,
                ),
                citations=risk_citations,
            )
        )
        section_views = [section for section in section_views if section.text.strip()]

        warnings = list(polish_bundle.get("warnings") or []) if polish_bundle else []
        if not polish_bundle:
            warnings.append("polish_bundle unavailable; deterministic wording fallback was used.")

        narrative_extension = self._narrative_extension(polish_bundle)
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
                    recommended_strategy=str(decision_summary.get("recommended_strategy") or "-"),
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
            summary_cards=summary_cards,
            section_views=section_views,
            warnings=warnings,
            provenance={
                "fact_source": "authoritative_payload",
                "wording_source": "polish_bundle.audience_variants" if polish_bundle else "deterministic_fallback",
                "delivery_mode_applied": False,
                "narrative_override_applied": narrative_extension.get("source") == "ai",
                "narrative_source": narrative_extension.get("source") or "deterministic_fallback",
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
        recommended_strategy: str,
        top_decision: dict[str, Any],
    ) -> str:
        decision_type = str(top_decision.get("decision_type") or "-")
        normalized_judgment = structural_judgment or "-"
        if audience == "developer":
            return (
                f"canonical 구조 판단은 {normalized_judgment}이며, 권장 전략은 {recommended_strategy}입니다. "
                f"상위 decision type은 {decision_type}입니다."
            )
        if audience == "client":
            return (
                f"이번 분석의 핵심 구조 판단은 {normalized_judgment}이고, 현재 권장 방향은 {recommended_strategy}입니다. "
                f"실행 해석은 {decision_type} 기준으로 정리됩니다."
            )
        return (
            f"현재 구조 판단은 {normalized_judgment}이며, 권장 전략은 {recommended_strategy}입니다. "
            f"상위 개선 방식은 {decision_type}입니다."
        )

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
        recommended_strategy: str,
        top_decision: dict[str, Any],
        top_issue: dict[str, Any],
    ) -> str:
        decision_type = str(top_decision.get("decision_type") or "-")
        rationale = str(top_decision.get("rationale") or "").strip() or str(top_issue.get("summary") or "-")
        templates = {
            "developer": f"추천 전략은 {recommended_strategy}입니다. 최상위 decision은 {decision_type}로 분류되며, 근거는 {rationale}입니다.",
            "manager": f"현재 권장 전략은 {recommended_strategy}입니다. 최상위 판단은 {decision_type}이며, 핵심 근거는 {rationale}입니다.",
            "client": f"권장 방향은 {recommended_strategy}입니다. 최상위 판단 유형은 {decision_type}이고, 주된 이유는 {rationale}입니다.",
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

    def _execution_body(self, *, audience: str, execution_stages: Any, top_stage: dict[str, Any]) -> str:
        stages = execution_stages if isinstance(execution_stages, list) else []
        stage_count = len(stages)
        top_title = str(top_stage.get("title") or "-")
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
        polished = polished_sections.get(section_key) or {}
        audience_variants = polished.get("audience_variants") or {}
        if isinstance(audience_variants, dict):
            audience_text = str(audience_variants.get(audience) or "").strip()
            if audience_text:
                return audience_text
        return self._deterministic_fallback_text(section_key=section_key, result_package=result_package)

    def _deterministic_fallback_text(self, *, section_key: str, result_package: dict[str, Any]) -> str:
        if section_key == "report_purpose":
            return str(result_package.get("report_purpose") or "").strip()
        if section_key == "one_line_conclusion":
            return str(result_package.get("core_conclusion") or "").strip()
        if section_key == "recommended_option":
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
