from __future__ import annotations

import json
import re

from mellow_link.modules.rebuild_assistant.schemas import StructuredRebuildResult

from .audience import build_audience_variant
from .delivery import build_delivery_variant
from .rules import apply_sentence_polish, collect_pattern_warnings
from .schemas import PolishedSection, StructuredResultPolishBundle


class StructuredResultPolishService:
    def polish_result(
        self,
        structured_result: StructuredRebuildResult,
        *,
        audience: str = "manager",
        delivery_mode: str = "client_report",
        use_ai_rewrite: bool = False,
    ) -> StructuredResultPolishBundle:
        original = structured_result.model_dump()
        sections = self._build_sections(structured_result)
        pattern_axis = (
            (structured_result.narrative_axis or "").strip()
            or (structured_result.template_judgment or "").strip()
            or (structured_result.primary_judgment or "").strip()
        )
        warnings: list[str] = []
        polished_sections: list[PolishedSection] = []

        for section_key, title, original_text in sections:
            polished_text = apply_sentence_polish(original_text)
            audience_variants = {
                mode: build_audience_variant(section_key, polished_text, mode)
                for mode in ("developer", "manager", "client")
            }
            delivery_variants = {
                mode: build_delivery_variant(section_key, polished_text, mode)
                for mode in ("internal_review", "client_report", "proposal_appendix")
            }
            warnings.extend(collect_pattern_warnings(pattern_axis, polished_text))
            polished_sections.append(
                PolishedSection(
                    section_key=section_key,
                    title=title,
                    original_text=original_text,
                    polished_text=polished_text,
                    audience_variants=audience_variants,
                    delivery_variants=delivery_variants,
                )
            )

        if use_ai_rewrite:
            warnings.append("AI rewrite hook is not enabled in deterministic v1. Original polished text is used.")

        preserved_facts = self._collect_preserved_facts(structured_result)
        warnings.extend(self._validate_preserved_facts(polished_sections, preserved_facts))
        warnings = self._dedupe(warnings)

        return StructuredResultPolishBundle(
            primary_judgment=structured_result.primary_judgment,
            template_judgment=structured_result.template_judgment or structured_result.primary_judgment,
            structural_judgment=structured_result.structural_judgment,
            narrative_axis=pattern_axis,
            feature_signal_mode=structured_result.feature_signal_mode,
            audience=audience,
            delivery_mode=delivery_mode,
            use_ai_rewrite=use_ai_rewrite,
            original_result=original,
            polished_sections=polished_sections,
            preserved_facts=preserved_facts,
            warnings=warnings,
        )

    def _build_sections(self, result: StructuredRebuildResult) -> list[tuple[str, str, str]]:
        analysis_first = self._uses_analysis_first_surface(result)
        sections = [
            ("report_purpose", self._section_title(result, "report_purpose", "보고서 목적"), result.report_purpose),
            ("report_scope", "분석 범위", self._join_lines(result.report_scope)),
            ("report_questions", "검토 질문" if analysis_first else "검증 질문", self._join_lines(result.report_questions)),
            ("one_line_conclusion", self._section_title(result, "one_line_conclusion", "핵심 결론"), result.one_line_conclusion),
            ("executive_summary_v2", self._section_title(result, "executive_summary_v2", "Executive Summary"), self._join_lines(result.executive_summary_v2)),
            ("grounded_business_rules", "업무 규칙 및 처리 기준" if analysis_first else "핵심 업무 규칙", self._join_grounded_rules(result)),
            ("retained_contracts", "유지해야 할 운영 계약" if analysis_first else "유지해야 할 계약", self._join_retained_contracts(result)),
            ("priority_split_items", "검토 우선순위" if analysis_first else "분리 우선순위", self._join_priority_items(result)),
            ("recommended_option", self._section_title(result, "recommended_option", "추천안"), self._join_recommended_option(result)),
            ("execution_plan", self._section_title(result, "execution_plan", "실행 계획"), self._join_execution_plan(result)),
            ("recommended_directions", self._section_title(result, "recommended_directions", "추천 방향"), self._join_lines(result.recommended_directions)),
            ("risks", self._section_title(result, "risks", "주요 리스크"), self._join_lines(result.risks)),
            ("recomposition_draft", self._section_title(result, "recomposition_draft", "전환 초안"), self._join_recomposition_draft(result)),
        ]
        accounting = self._accounting_extension(result)
        if accounting:
            sections.extend(
                [
                    ("accounting_summary", "회계 계산 요약", str(accounting.get("summary_sentence") or "")),
                    ("accounting_status", "계산 가능 여부", self._join_accounting_status(accounting)),
                    ("accounting_analysis", "회계 방식 분석", self._join_accounting_analysis(accounting)),
                    ("fx_calculation", "외화 계산 결과", self._join_fx_calculation(accounting)),
                    ("voucher_review", "전표 검토 결과", self._join_voucher_review(accounting)),
                ]
            )
        return sections

    def _join_lines(self, items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items if (item or "").strip())

    def _join_grounded_rules(self, result: StructuredRebuildResult) -> str:
        lines = []
        for item in result.grounded_business_rules:
            title = (item.title or "").strip()
            desc = (item.description or "").strip()
            if title and desc:
                lines.append(f"- {title}: {desc}")
            elif title:
                lines.append(f"- {title}")
        return "\n".join(lines)

    def _join_retained_contracts(self, result: StructuredRebuildResult) -> str:
        lines = []
        for item in result.retained_contracts:
            text = (item.item or "").strip()
            basis = (item.basis or "").strip()
            if text and basis:
                lines.append(f"- {text}: {basis}")
            elif text:
                lines.append(f"- {text}")
        return "\n".join(lines)

    def _join_priority_items(self, result: StructuredRebuildResult) -> str:
        lines = []
        for item in sorted(result.priority_split_items, key=lambda value: value.priority):
            title = (item.title or "").strip()
            reason = (item.reason or "").strip()
            if title and reason:
                lines.append(f"- {item.priority}순위 {title}: {reason}")
            elif title:
                lines.append(f"- {item.priority}순위 {title}")
        return "\n".join(lines)

    def _join_recommended_option(self, result: StructuredRebuildResult) -> str:
        option = result.recommended_option
        if option is None:
            return ""
        parts = [option.name.strip(), option.structure_summary.strip(), option.selection_reason.strip()]
        parts.extend(outcome.strip() for outcome in option.expected_outcomes if outcome.strip())
        return "\n".join(f"- {part}" for part in parts if part)

    def _join_execution_plan(self, result: StructuredRebuildResult) -> str:
        lines = []
        for week in result.execution_plan:
            week_label = (week.week_label or "").strip()
            goal = (week.goal or "").strip()
            if week_label and goal:
                lines.append(f"- {week_label}: {goal}")
            lines.extend(f"  - {task.strip()}" for task in week.tasks if task.strip())
        return "\n".join(lines)

    def _join_recomposition_draft(self, result: StructuredRebuildResult) -> str:
        lines = []
        if result.recomposition_draft.database:
            lines.append("[database]")
            lines.extend(f"- {item.strip()}" for item in result.recomposition_draft.database if item.strip())
        if result.recomposition_draft.backend:
            lines.append("[backend]")
            lines.extend(f"- {item.strip()}" for item in result.recomposition_draft.backend if item.strip())
        if result.recomposition_draft.frontend:
            lines.append("[frontend]")
            lines.extend(f"- {item.strip()}" for item in result.recomposition_draft.frontend if item.strip())
        return "\n".join(lines)

    def _join_accounting_status(self, accounting: dict) -> str:
        status = accounting.get("calculation_status") or {}
        validation = accounting.get("input_validation") or {}
        lines = []
        if "can_calculate" in status:
            lines.append(f"- can_calculate: {'true' if status.get('can_calculate') else 'false'}")
        if status.get("reason"):
            lines.append(f"- reason: {status.get('reason')}")
        if status.get("blocking_issue"):
            lines.append(f"- blocking_issue: {status.get('blocking_issue')}")
        if validation.get("missing_required_inputs"):
            lines.append(f"- missing_required_inputs: {', '.join(validation.get('missing_required_inputs') or [])}")
        return "\n".join(lines)

    def _join_accounting_analysis(self, accounting: dict) -> str:
        analysis = accounting.get("accounting_analysis") or {}
        lines = []
        candidates = analysis.get("candidate_methods") or []
        if candidates:
            lines.append(f"- 후보 방식: {', '.join(candidates)}")
        if analysis.get("recommended_method"):
            lines.append(f"- 추천 방식: {analysis.get('recommended_method')}")
        for reason in analysis.get("reasons") or []:
            lines.append(f"- {reason.get('message') or '-'}")
        return "\n".join(lines)

    def _join_fx_calculation(self, accounting: dict) -> str:
        calc = accounting.get("fx_calculation") or {}
        lines = []
        if calc.get("method"):
            lines.append(f"- 방식: {calc.get('method')}")
        if calc.get("realized_gain_loss_krw") is not None:
            lines.append(f"- 환차손익: {calc.get('realized_gain_loss_krw'):,}원")
        if calc.get("failure_reason"):
            lines.append(f"- 실패 사유: {calc.get('failure_reason')}")
        for step in calc.get("detail_steps") or []:
            message = step.get("message") or "-"
            lines.append(f"- {message}")
        return "\n".join(lines)

    def _join_voucher_review(self, accounting: dict) -> str:
        review = accounting.get("voucher_review") or {}
        lines = []
        if review.get("status"):
            lines.append(f"- 상태: {review.get('status')}")
        if review.get("balance_ok") is None and review.get("status") == "input_missing":
            lines.append("- 차변/대변 균형: 검토 불가")
        elif review.get("balance_ok") is not None:
            lines.append(f"- 차변/대변 균형: {'예' if review.get('balance_ok') else '아니오'}")
        if review.get("policy_consistent") is None and review.get("status") == "input_missing":
            lines.append("- 정책 일치: 검토 불가")
        elif review.get("policy_consistent") is not None:
            lines.append(f"- 정책 일치: {'예' if review.get('policy_consistent') else '아니오'}")
        if review.get("failure_reason"):
            lines.append(f"- 실패 사유: {review.get('failure_reason')}")
        for item in review.get("review_points") or []:
            lines.append(f"- {item.get('message') or '-'}")
        for item in review.get("mismatches") or []:
            lines.append(f"- 불일치: {item.get('message') or '-'}")
        return "\n".join(lines)

    def _accounting_extension(self, result: StructuredRebuildResult) -> dict:
        extensions = result.extensions if isinstance(result.extensions, dict) else {}
        accounting = extensions.get("accounting") if isinstance(extensions, dict) else None
        return accounting if isinstance(accounting, dict) else {}

    def _surface_wording(self, result: StructuredRebuildResult) -> dict:
        extensions = result.extensions if isinstance(result.extensions, dict) else {}
        governance = extensions.get("decision_governance") if isinstance(extensions, dict) else {}
        wording = governance.get("surface_wording") if isinstance(governance, dict) else {}
        return wording if isinstance(wording, dict) else {}

    def _uses_analysis_first_surface(self, result: StructuredRebuildResult) -> bool:
        wording = self._surface_wording(result)
        return str(wording.get("mode") or "").strip() == "analysis_first_operational_source"

    def _section_title(self, result: StructuredRebuildResult, section_key: str, fallback: str) -> str:
        wording = self._surface_wording(result)
        titles = wording.get("section_titles") if isinstance(wording, dict) else {}
        if isinstance(titles, dict):
            title = str(titles.get(section_key) or "").strip()
            if title:
                return title
        return fallback

    def _collect_preserved_facts(self, result: StructuredRebuildResult) -> list[str]:
        facts: list[str] = []
        facts.extend(item.title for item in result.grounded_business_rules if item.title)
        facts.extend(item.item for item in result.retained_contracts if item.item)
        if result.recommended_option and result.recommended_option.name:
            facts.append(result.recommended_option.name)
        accounting = self._accounting_extension(result)
        if accounting:
            accounting_text = json.dumps(accounting, ensure_ascii=False)
            facts.extend(re.findall(r"\b\d[\d,]*\b", accounting_text))
            facts.extend(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", accounting_text))
            if accounting.get("summary_sentence"):
                facts.append(str(accounting.get("summary_sentence")))
        important_text = "\n".join(
            [
                result.one_line_conclusion,
                *(item.title for item in result.grounded_business_rules),
                *(item.item for item in result.retained_contracts),
            ]
        )
        facts.extend(re.findall(r"\b\d[\d,]*\b", important_text))
        facts.extend(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", important_text))
        return self._dedupe([fact.strip() for fact in facts if fact and fact.strip()])

    def _validate_preserved_facts(self, polished_sections: list[PolishedSection], preserved_facts: list[str]) -> list[str]:
        warnings: list[str] = []
        combined = "\n".join(section.polished_text for section in polished_sections)
        for fact in preserved_facts:
            if fact and fact not in combined:
                warnings.append(f"보정 결과에 preserved fact가 직접 노출되지 않았습니다: {fact}")
        return warnings

    def _dedupe(self, items: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for item in items:
            key = re.sub(r"\s+", " ", item).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output


def polish_result(
    structured_result: StructuredRebuildResult,
    *,
    audience: str = "manager",
    delivery_mode: str = "client_report",
    use_ai_rewrite: bool = False,
) -> StructuredResultPolishBundle:
    return StructuredResultPolishService().polish_result(
        structured_result,
        audience=audience,
        delivery_mode=delivery_mode,
        use_ai_rewrite=use_ai_rewrite,
    )
