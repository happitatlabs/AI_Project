from __future__ import annotations

from typing import Any

from mellow_link.modules.rebuild_assistant.schemas import (
    ResultExplanationResponse,
    ResultQAResponse,
)
from mellow_link.services.refactoring_support_engine import (
    ExplanationPresenter,
    ResultQuestionAnsweringService,
)


def present_project_result(
    *,
    project_id: str,
    result_package: dict[str, Any],
    audience: str,
    surface_mode: str,
) -> ResultExplanationResponse:
    return ExplanationPresenter().present(
        project_id=project_id,
        result_package=result_package,
        audience=audience,
        surface_mode=surface_mode,
    )


async def answer_project_result_question(
    *,
    project_id: str,
    result_package: dict[str, Any],
    question: str,
    audience: str,
    llm_service: Any,
) -> ResultQAResponse:
    return await ResultQuestionAnsweringService().answer(
        project_id=project_id,
        result_package=result_package,
        question=question,
        audience=audience,
        llm_service=llm_service,
    )


def render_result_explanation_markdown(explanation: ResultExplanationResponse) -> str:
    taxonomy = explanation.taxonomy_view
    cards = explanation.summary_cards or []
    sections = explanation.section_views or []
    analysis_first_surface = _uses_analysis_first_surface(explanation)
    if explanation.surface_mode == "external":
        card_map = {card.card_key: card for card in cards}
        judgment_body = getattr(card_map.get("judgment"), "body", "") or taxonomy.core_judgment.structural_judgment or "-"
        strategy_body = getattr(card_map.get("strategy"), "body", "") or taxonomy.core_judgment.display_strategy or taxonomy.core_judgment.recommended_strategy or "-"
        execution_body = getattr(card_map.get("execution"), "body", "") or ""
        judgment_title = getattr(card_map.get("judgment"), "title", "") or "핵심 판단"
        strategy_title = getattr(card_map.get("strategy"), "title", "") or "왜 이 방향인가"
        execution_title = getattr(card_map.get("execution"), "title", "") or "다음 단계"
        lines = [
            f"# 구조 판단 - {explanation.project_id}",
            "",
            f"## {judgment_title}",
            f"- {judgment_body}",
            "",
            f"## {strategy_title}",
            f"- {strategy_body}",
            "",
            f"## {execution_title}",
        ]
        if execution_body:
            lines.append(f"- {execution_body}")
        if sections:
            for section in sections:
                lines.extend(["", f"### {section.title}"])
                for row in str(section.text or "").splitlines():
                    normalized = row.strip()
                    if normalized:
                        lines.append(f"- {normalized}")
        return "\n".join(lines).strip() + "\n"
    strategy_heading = "우선 검토 기준" if analysis_first_surface else "권장 전략"
    strategy_value = taxonomy.core_judgment.display_strategy if analysis_first_surface else taxonomy.core_judgment.recommended_strategy
    lines = [
        f"# 구조 판단 - {explanation.project_id}",
        "",
        f"## {'분석 성격' if analysis_first_surface else '구조 판단'}",
        f"- {taxonomy.core_judgment.structural_judgment or '-'}",
        "",
        f"## {strategy_heading}",
        f"- {strategy_value or '-'}",
        f"- 개선 방식: {taxonomy.core_judgment.top_decision_type or '-'}",
        "",
        "## 판단 근거",
    ]
    if analysis_first_surface and taxonomy.core_judgment.recommended_strategy:
        lines.insert(7, f"- 내부 taxonomy: {taxonomy.core_judgment.recommended_strategy}")
    if taxonomy.evidence_view.top_priority_score is not None:
        lines.append(f"- 우선순위 점수: {taxonomy.evidence_view.top_priority_score}")
    score_breakdown = taxonomy.evidence_view.score_breakdown or {}
    if score_breakdown:
        lines.append(
            "- 점수 요약: "
            + ", ".join(f"{key}={value}" for key, value in score_breakdown.items())
        )
    explainability = taxonomy.evidence_view.explainability or {}
    if explainability.get("score_summary"):
        lines.append(f"- 계산 요약: {explainability.get('score_summary')}")
    if cards:
        lines.extend(["", "## 요약 카드"])
        for card in cards:
            lines.append(f"### {card.title}")
            lines.append(f"- {card.body}")
    if sections:
        lines.extend(["", "## 다음 단계"])
        for section in sections:
            lines.append(f"### {section.title}")
            for row in str(section.text or "").splitlines():
                normalized = row.strip()
                if normalized:
                    lines.append(f"- {normalized}")
    lines.extend(
        [
            "",
            "## 설명 관점",
            f"- {taxonomy.explanation_context.narrative_axis or '-'}",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _uses_analysis_first_surface(explanation: ResultExplanationResponse) -> bool:
    display_strategy = str(explanation.taxonomy_view.core_judgment.display_strategy or "").strip()
    recommended_strategy = str(explanation.taxonomy_view.core_judgment.recommended_strategy or "").strip()
    return bool(display_strategy) and display_strategy != recommended_strategy
