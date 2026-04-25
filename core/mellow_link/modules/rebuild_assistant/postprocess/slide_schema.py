from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from .schemas import (
    ConsultingDeck,
    ConsultingDeckChapter,
    SlideRuleCard,
    SlideSchema,
    SlideSchemaDeck,
    SlideStep,
)


_SLIDE_TYPE_POLICY: dict[str, dict[str, Any]] = {
    "overview": {
        "headline_limit": 34,
        "context_limit": 3,
        "scope_limit": 2,
        "constraint_limit": 2,
        "slide_cap": 2,
        "max_text_objects": 5,
        "context_text_limit": 56,
        "scope_text_limit": 52,
        "constraint_text_limit": 52,
        "tagline_limit": 40,
        "overview_scope_summary_limit": 34,
    },
    "as_is_gap": {
        "headline_limit": 34,
        "as_is_limit": 3,
        "gap_limit": 3,
        "to_be_limit": 3,
        "risk_limit": 4,
        "max_text_objects": 6,
        "slide_char_threshold": 560,
        "as_is_gap_first_slide_soft_limit": 500,
        "as_is_gap_continuation_absorb_char_total": 220,
        "as_is_text_limit": 60,
        "gap_text_limit": 66,
        "to_be_text_limit": 60,
        "to_be_display_text_limit": 32,
        "risk_text_limit": 56,
        "decision_limit": 50,
    },
    "flow": {
        "headline_limit": 32,
        "step_limit": 5,
        "action_limit": 3,
        "max_text_objects": 6,
        "step_text_limit": 44,
        "action_text_limit": 44,
    },
    "design": {
        "headline_limit": 32,
        "rule_limit": 4,
        "flow_limit": 3,
        "entity_limit": 4,
        "interface_limit": 3,
        "max_text_objects": 7,
        "slide_char_threshold": 520,
        "design_first_slide_soft_limit": 500,
        "design_continuation_absorb_char_total": 300,
        "rule_title_limit": 20,
        "rule_body_limit": 56,
        "flow_text_limit": 50,
        "entity_text_limit": 46,
        "interface_text_limit": 46,
    },
    "vision": {
        "headline_limit": 30,
        "future_limit": 3,
        "effect_limit": 3,
        "slide_cap": 2,
        "max_text_objects": 5,
        "future_text_limit": 52,
        "effect_text_limit": 48,
        "closing_limit": 44,
    },
}

_DEFAULT_HEADLINES: dict[str, str] = {
    "overview": "배경 및 범위 정리",
    "as_is_gap": "AS-IS / GAP / TO-BE 정리",
    "flow": "구현 계획 및 단계",
    "design": "핵심 규칙 및 구조 설계",
    "vision": "적용 방향",
}

_SCOPE_KEYWORDS: tuple[str, ...] = (
    "범위",
    "중심",
    "대상",
    "우선",
    "기준",
    "프로그램",
    "도메인",
    "분석",
)
_CONSTRAINT_KEYWORDS: tuple[str, ...] = (
    "유지",
    "보존",
    "제약",
    "필요",
    "추가",
    "한계",
    "계약",
    "호환",
    "확인",
)
_EFFECT_KEYWORDS: tuple[str, ...] = (
    "효과",
    "개선",
    "감소",
    "향상",
    "안정",
    "일관",
    "정합",
    "추적",
    "누락 감소",
    "재처리 감소",
)
_ENTITY_KEYWORDS: tuple[str, ...] = (
    "lot",
    "원장",
    "환차손익",
    "전표",
    "gl",
    "기준번호",
    "통화",
    "계좌",
)
_INTERFACE_KEYWORDS: tuple[str, ...] = (
    "gl",
    "인터페이스",
    "전표",
    "연계",
    "api",
    "기준번호",
)
_CONCEPT_STOPWORDS: tuple[str, ...] = (
    "합니다",
    "합니다.",
    "기준",
    "구조",
    "흐름",
    "정리",
    "관리",
    "검토",
    "필요",
    "수준",
    "유지",
)
_DOMAIN_CONCEPTS: tuple[str, ...] = (
    "외화 입출금 fifo",
    "fifo",
    "lot",
    "환차손익",
    "전표",
    "gl",
    "api",
    "조회",
    "권한",
    "상태",
    "workflow",
)
_COMPRESSION_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("동일 거래의 ", "거래별 "),
    ("같은 정책으로 ", "단일 정책으로 "),
    ("일관되게 유지됩니다", "일관성을 유지합니다"),
    ("흔들리지 않습니다", "안정화합니다"),
    ("줄일 수 있습니다", "줄입니다"),
    ("전 과정에서 ", "전 구간에서 "),
    ("계산 결과와 같은 ", "계산 결과와 동일 "),
    ("비교 정책으로 ", "비교 기준으로 "),
    ("기준으로 검증합니다", "기준으로 검증합니다"),
)


def build_slide_schema(deck: ConsultingDeck) -> SlideSchemaDeck:
    chapter_map = {chapter.chapter_key: chapter for chapter in deck.chapters}
    slides: list[SlideSchema] = []
    information_role = str(getattr(deck, "information_role", "") or "").strip()
    if information_role == "structure":
        slides.extend(_build_overview_slides(chapter_map))
        slides.extend(_build_flow_slides(chapter_map))
    elif information_role == "diagnosis":
        slides.extend(_build_overview_slides(chapter_map))
        slides.extend(_build_as_is_gap_slides(chapter_map, information_role=information_role))
    elif information_role == "decision":
        slides.extend(_build_overview_slides(chapter_map))
        slides.extend(_build_design_slides(chapter_map))
        slides.extend(_build_vision_slides(chapter_map))
    else:
        slides.extend(_build_overview_slides(chapter_map))
        slides.extend(_build_as_is_gap_slides(chapter_map))
        slides.extend(_build_flow_slides(chapter_map))
        slides.extend(_build_design_slides(chapter_map))
        slides.extend(_build_vision_slides(chapter_map))
    return SlideSchemaDeck(
        project_name=deck.project_name,
        client_name=deck.client_name,
        surface_mode=deck.surface_mode,
        slides=slides,
    )


def _build_overview_slides(chapter_map: dict[str, ConsultingDeckChapter]) -> list[SlideSchema]:
    policy = _SLIDE_TYPE_POLICY["overview"]
    chapter = chapter_map.get("overview")
    raw_items = _section_items(chapter, "as_is")
    context_items, scope_items, constraint_items = _split_overview_items(
        raw_items,
        context_limit=policy["context_text_limit"],
        scope_limit=policy["scope_text_limit"],
        constraint_limit=policy["constraint_text_limit"],
    )
    context_items, scope_items, constraint_items = _ensure_overview_density_balance(
        context_items,
        scope_items,
        constraint_items,
        scope_limit=policy["overview_scope_summary_limit"],
    )
    slides: list[SlideSchema] = []

    sequence = 1
    while sequence <= policy["slide_cap"]:
        context_chunk = context_items[: policy["context_limit"]]
        scope_chunk = scope_items[: policy["scope_limit"]]
        constraint_chunk = constraint_items[: policy["constraint_limit"]]
        if not any((context_chunk, scope_chunk, constraint_chunk)):
            break
        context_items = context_items[len(context_chunk) :]
        scope_items = scope_items[len(scope_chunk) :]
        constraint_items = constraint_items[len(constraint_chunk) :]
        layout_hint = _overview_layout_hint(scope_chunk, constraint_chunk, sequence)
        slides.append(
            SlideSchema(
                slide_id=f"overview_{sequence:02d}",
                slide_type="overview",
                chapter_key="overview",
                title=chapter.title if chapter else "컨설팅 개요",
                headline=_build_headline(
                    "overview",
                    context_chunk + scope_chunk + constraint_chunk,
                    limit=policy["headline_limit"],
                ),
                source_refs=["overview.as_is"],
                layout_hint=layout_hint,
                sequence=sequence,
                is_continuation=sequence > 1,
                continuation_of="overview_01" if sequence > 1 else "",
                continuation_reason="overview_overflow" if sequence > 1 else "",
                density_tier=_density_tier(len(context_chunk) + len(scope_chunk) + len(constraint_chunk)),
                max_text_objects=policy["max_text_objects"],
                context_bullets=context_chunk,
                scope_bullets=scope_chunk,
                constraint_bullets=constraint_chunk,
                tagline=_build_overview_tagline(scope_chunk, constraint_chunk, limit=policy["tagline_limit"]),
            )
        )
        sequence += 1
        if not any((context_items, scope_items, constraint_items)):
            break
    return slides or [
        SlideSchema(
            slide_id="overview_01",
            slide_type="overview",
            chapter_key="overview",
            title=chapter.title if chapter else "컨설팅 개요",
            headline=_DEFAULT_HEADLINES["overview"],
            source_refs=["overview.as_is"],
            layout_hint="overview_context_only",
            max_text_objects=policy["max_text_objects"],
        )
    ]


def _build_as_is_gap_slides(chapter_map: dict[str, ConsultingDeckChapter], *, information_role: str = "") -> list[SlideSchema]:
    policy = _SLIDE_TYPE_POLICY["as_is_gap"]
    overview_items = _clip_and_dedupe(_section_items(chapter_map.get("overview"), "as_is"), policy["as_is_text_limit"])[: policy["as_is_limit"]]
    gap_items = _clip_and_dedupe(_section_items(chapter_map.get("approach"), "gap"), policy["gap_text_limit"])
    risk_items = _clip_and_dedupe(_section_items(chapter_map.get("approach"), "risks"), policy["risk_text_limit"])
    to_be_items = [] if information_role == "diagnosis" else _build_to_be_items(chapter_map, limit=policy["to_be_limit"], text_limit=policy["to_be_text_limit"])
    to_be_display_items = _build_to_be_display_items(
        to_be_items,
        limit=policy["to_be_limit"],
        text_limit=policy["to_be_display_text_limit"],
    )

    slides: list[SlideSchema] = []
    remaining_gap = gap_items[:]
    remaining_risk = risk_items[:]
    sequence = 1
    while remaining_gap or remaining_risk or sequence == 1:
        gap_chunk = remaining_gap[: policy["gap_limit"]]
        remaining_gap = remaining_gap[len(gap_chunk) :]
        risk_limit = policy["risk_limit"] if sequence == 1 else max(2, policy["risk_limit"] - 1)
        risk_chunk = remaining_risk[:risk_limit]
        remaining_risk = remaining_risk[len(risk_chunk) :]
        gap_chunk = _ensure_minimum_gap_bullets(
            gap_chunk,
            risk_chunk=risk_chunk,
            to_be_items=to_be_items,
            text_limit=policy["gap_text_limit"],
        )
        layout_hint = "three_column_compare_with_risk_strip" if sequence == 1 else "gap_risk_continuation"
        slide = SlideSchema(
            slide_id=f"approach_{sequence:02d}",
            slide_type="as_is_gap",
            chapter_key="approach",
            title=chapter_map.get("approach").title if chapter_map.get("approach") else "컨설팅 전개",
            headline=_build_headline(
                "as_is_gap",
                gap_chunk or risk_chunk or overview_items or to_be_items,
                limit=policy["headline_limit"],
            ),
            source_refs=[
                "overview.as_is",
                "approach.gap",
                "approach.risks",
                "vision.actions",
                "implementation.actions",
            ],
            layout_hint=layout_hint,
            sequence=sequence,
            is_continuation=sequence > 1,
            continuation_of="approach_01" if sequence > 1 else "",
            continuation_reason="gap_risk_overflow" if sequence > 1 else "",
            density_tier=_density_tier(
                len(overview_items if sequence == 1 else []) + len(gap_chunk) + len(to_be_display_items if sequence == 1 else []) + len(risk_chunk)
            ),
            max_text_objects=policy["max_text_objects"],
            as_is_bullets=overview_items if sequence == 1 else [],
            gap_bullets=gap_chunk,
            to_be_bullets=to_be_display_items if sequence == 1 else [],
            risk_bullets=risk_chunk,
            decision_message=(
                ""
                if information_role == "diagnosis"
                else _build_decision_message(to_be_display_items if sequence == 1 else gap_chunk, limit=policy["decision_limit"])
            ),
        )
        if sequence == 1:
            soft_gap, soft_risk = _split_as_is_gap_by_char_threshold(
                slide,
                threshold=policy["as_is_gap_first_slide_soft_limit"],
                gap_text_limit=policy["gap_text_limit"],
                risk_text_limit=policy["risk_text_limit"],
                use_report_total=True,
            )
            if soft_gap:
                remaining_gap = soft_gap + remaining_gap
            if soft_risk:
                remaining_risk = soft_risk + remaining_risk
        overflow_gap, overflow_risk = _split_as_is_gap_by_char_threshold(
            slide,
            threshold=policy["slide_char_threshold"],
            gap_text_limit=policy["gap_text_limit"],
            risk_text_limit=policy["risk_text_limit"],
        )
        if overflow_gap:
            remaining_gap = overflow_gap + remaining_gap
        if overflow_risk:
            remaining_risk = overflow_risk + remaining_risk
        slides.append(slide)
        sequence += 1
        if not (remaining_gap or remaining_risk):
            break
    return _reabsorb_as_is_gap_continuations(slides, policy=policy)


def _build_flow_slides(chapter_map: dict[str, ConsultingDeckChapter]) -> list[SlideSchema]:
    policy = _SLIDE_TYPE_POLICY["flow"]
    process_items = _section_items(chapter_map.get("implementation"), "process_flow")
    step_items = [_to_step(item, index + 1, text_limit=policy["step_text_limit"]) for index, item in enumerate(process_items)]
    step_items = [step for step in step_items if step.step_text]
    action_items = _clip_and_dedupe(_section_items(chapter_map.get("implementation"), "actions"), policy["action_text_limit"])
    action_items = _remove_duplicate_actions(step_items, action_items)
    slides: list[SlideSchema] = []

    if len(step_items) <= 4:
        steps_by_slide = [step_items]
        layout_hints = ["timeline_horizontal"]
    elif len(step_items) == 5:
        steps_by_slide = [step_items]
        layout_hints = ["stacked_flow"]
    else:
        steps_by_slide = [step_items[index : index + policy["step_limit"]] for index in range(0, len(step_items), policy["step_limit"])]
        layout_hints = ["stacked_flow"] + ["flow_continuation"] * max(0, len(steps_by_slide) - 1)

    for index, steps in enumerate(steps_by_slide, start=1):
        slides.append(
            SlideSchema(
                slide_id=f"implementation_{index:02d}",
                slide_type="flow",
                chapter_key="implementation",
                title=chapter_map.get("implementation").title if chapter_map.get("implementation") else "컨설팅 구현",
                headline=_build_headline(
                    "flow",
                    [step.step_text for step in steps] + (action_items if index == 1 else []),
                    limit=policy["headline_limit"],
                ),
                source_refs=["implementation.process_flow", "implementation.actions"],
                layout_hint=layout_hints[index - 1],
                sequence=index,
                is_continuation=index > 1,
                continuation_of="implementation_01" if index > 1 else "",
                continuation_reason="flow_overflow" if index > 1 else "",
                density_tier=_density_tier(len(steps) + len(action_items if index == 1 else [])),
                max_text_objects=policy["max_text_objects"],
                steps=steps,
                action_bullets=action_items[: policy["action_limit"]] if index == 1 else [],
                milestones=[step.step_label for step in steps],
                footer_note=_build_flow_footer_note(index, len(steps_by_slide)),
            )
        )
    return _annotate_continuation_values(slides, slide_type="flow", policy=policy)


def _build_design_slides(chapter_map: dict[str, ConsultingDeckChapter]) -> list[SlideSchema]:
    policy = _SLIDE_TYPE_POLICY["design"]
    rules = _section_items(chapter_map.get("design"), "rules")
    flow_items = _clip_and_dedupe(_section_items(chapter_map.get("design"), "process_flow"), policy["flow_text_limit"])
    cards = [
        _to_rule_card(
            rule,
            title_limit=policy["rule_title_limit"],
            body_limit=policy["rule_body_limit"],
        )
        for rule in rules
    ]
    cards = [card for card in cards if card.title or card.body]
    cards = _ensure_minimum_rule_cards(cards, flow_items, body_limit=policy["rule_body_limit"], title_limit=policy["rule_title_limit"])
    use_meta_sidebar = _should_use_design_meta_sidebar(cards)
    entity_blocks = _extract_keyword_blocks(
        rules + flow_items,
        _ENTITY_KEYWORDS,
        limit=policy["entity_limit"],
        text_limit=policy["entity_text_limit"],
    ) if use_meta_sidebar else []
    interface_points = _extract_keyword_blocks(
        rules + flow_items,
        _INTERFACE_KEYWORDS,
        limit=policy["interface_limit"],
        text_limit=policy["interface_text_limit"],
    ) if use_meta_sidebar else []
    slides: list[SlideSchema] = []

    remaining_cards = cards[:]
    remaining_flow_bullets: list[str] = []
    sequence = 1
    while remaining_cards or remaining_flow_bullets or sequence == 1:
        chunk = remaining_cards[: policy["rule_limit"]]
        remaining_cards = remaining_cards[len(chunk) :]
        if sequence == 1:
            flow_bullets = flow_items[: policy["flow_limit"]]
        else:
            flow_bullets = remaining_flow_bullets[: policy["flow_limit"]]
            remaining_flow_bullets = remaining_flow_bullets[len(flow_bullets) :]
        design_entity_blocks = entity_blocks if sequence == 1 else entity_blocks[: max(1, policy["entity_limit"] - 2)]
        design_interface_points = interface_points if sequence == 1 else interface_points[: max(1, policy["interface_limit"] - 1)]
        layout_hint = _design_layout_hint(flow_bullets, design_entity_blocks, design_interface_points, continuation=sequence > 1)
        slide = SlideSchema(
            slide_id=f"design_{sequence:02d}",
            slide_type="design",
            chapter_key="design",
            title=chapter_map.get("design").title if chapter_map.get("design") else "컨설팅 설계",
            headline=_build_headline(
                "design",
                [card.title for card in chunk] + flow_bullets + design_entity_blocks + design_interface_points,
                limit=policy["headline_limit"],
            ),
            source_refs=["design.rules", "design.process_flow"],
            layout_hint=layout_hint,
            sequence=sequence,
            is_continuation=sequence > 1,
            continuation_of="design_01" if sequence > 1 else "",
            continuation_reason="design_rule_card_overflow" if sequence > 1 else "",
            density_tier=_density_tier(len(chunk) + len(flow_bullets) + len(design_entity_blocks) + len(design_interface_points)),
            max_text_objects=policy["max_text_objects"],
            rule_cards=chunk,
            flow_bullets=flow_bullets,
            entity_blocks=design_entity_blocks,
            interface_points=design_interface_points,
        )
        if sequence == 1:
            overflow_flow_bullets = _split_design_first_slide_by_soft_limit(
                slide,
                soft_limit=policy["design_first_slide_soft_limit"],
            )
            if overflow_flow_bullets:
                remaining_flow_bullets = overflow_flow_bullets + remaining_flow_bullets
        overflow_cards = _split_design_by_char_threshold(
            slide,
            threshold=policy["slide_char_threshold"],
            minimum_cards=2 if sequence == 1 else 1,
        )
        if overflow_cards:
            remaining_cards = overflow_cards + remaining_cards
        slides.append(slide)
        sequence += 1
        if not (remaining_cards or remaining_flow_bullets):
            break
    return _reabsorb_design_continuations(slides, policy=policy)


def _build_vision_slides(chapter_map: dict[str, ConsultingDeckChapter]) -> list[SlideSchema]:
    policy = _SLIDE_TYPE_POLICY["vision"]
    future_state = _clip_and_dedupe(_section_items(chapter_map.get("vision"), "actions"), policy["future_text_limit"])
    effect_bullets = _extract_effect_bullets(
        _section_items(chapter_map.get("vision"), "actions"),
        limit=policy["effect_limit"],
        text_limit=policy["effect_text_limit"],
    )
    slides: list[SlideSchema] = []

    chunks = [future_state[index : index + policy["future_limit"]] for index in range(0, len(future_state), policy["future_limit"])] or [[]]
    for index, chunk in enumerate(chunks[: policy["slide_cap"]], start=1):
        slides.append(
            SlideSchema(
                slide_id=f"vision_{index:02d}",
                slide_type="vision",
                chapter_key="vision",
                title=chapter_map.get("vision").title if chapter_map.get("vision") else "컨설팅 비전",
                headline=_build_headline(
                    "vision",
                    chunk or effect_bullets,
                    limit=policy["headline_limit"],
                ),
                source_refs=["vision.actions"],
                layout_hint=_vision_layout_hint(effect_bullets, continuation=index > 1, item_count=len(chunk)),
                sequence=index,
                is_continuation=index > 1,
                continuation_of="vision_01" if index > 1 else "",
                continuation_reason="vision_future_state_overflow" if index > 1 else "",
                density_tier=_density_tier(len(chunk) + len(effect_bullets if index == 1 else [])),
                max_text_objects=policy["max_text_objects"],
                future_state_bullets=chunk,
                effect_bullets=effect_bullets if index == 1 else [],
                closing_statement=_build_closing_statement(chunk, limit=policy["closing_limit"]) if index == 1 else "",
            )
        )
    return _annotate_continuation_values(slides, slide_type="vision", policy=policy)


def _section_items(chapter: ConsultingDeckChapter | None, section_key: str) -> list[str]:
    if chapter is None:
        return []
    for section in chapter.sections:
        if section.section_key == section_key:
            return [_normalize_text(item) for item in section.items if _normalize_text(item)]
    return []


def _split_overview_items(
    items: list[str],
    *,
    context_limit: int,
    scope_limit: int,
    constraint_limit: int,
) -> tuple[list[str], list[str], list[str]]:
    context: list[str] = []
    scope: list[str] = []
    constraints: list[str] = []
    for item in items:
        candidate = _fit_text(item, context_limit)
        if not candidate:
            continue
        lowered = candidate.lower()
        if any(keyword in lowered for keyword in _CONSTRAINT_KEYWORDS):
            constraints.append(_fit_text(candidate, constraint_limit))
            continue
        if any(keyword in lowered for keyword in _SCOPE_KEYWORDS):
            scope.append(_fit_text(candidate, scope_limit))
            continue
        context.append(candidate)
    if not context and scope:
        context.append(scope.pop(0))
    if not context and constraints:
        context.append(constraints.pop(0))
    return (
        _dedupe_items(context, limit=context_limit),
        _dedupe_items(scope, limit=scope_limit),
        _dedupe_items(constraints, limit=constraint_limit),
    )


def _build_to_be_items(chapter_map: dict[str, ConsultingDeckChapter], *, limit: int, text_limit: int) -> list[str]:
    vision_actions = _section_items(chapter_map.get("vision"), "actions")
    implementation_actions = _section_items(chapter_map.get("implementation"), "actions")
    source = vision_actions or implementation_actions
    if source:
        return _clip_and_dedupe(source, text_limit)[:limit]
    gap_items = _section_items(chapter_map.get("approach"), "gap")
    derived = [_derive_to_be(item) for item in gap_items]
    return [item for item in _clip_and_dedupe(derived, text_limit)[:limit] if item]


def _build_to_be_display_items(items: list[str], *, limit: int, text_limit: int) -> list[str]:
    compacted = [_compact_direction_text(item, text_limit=text_limit) for item in items]
    return _dedupe_items(compacted, limit=text_limit)[:limit]


def _derive_to_be(text: str) -> str:
    normalized = _normalize_text(text)
    replacements = (
        ("분리해야", "분리하는 구조로 전환"),
        ("고정해야", "고정 기준으로 정렬"),
        ("관리해야", "관리 체계로 정리"),
        ("연결해야", "연결 구조로 정리"),
        ("정리해야", "정리 구조로 전환"),
        ("검토해야", "검토 기준으로 정리"),
    )
    for old, new in replacements:
        if old in normalized:
            candidate = normalized.replace(old, new)
            return _fit_text(candidate, 60)
    return _fit_text(normalized, 60)


def _to_step(text: str, sequence: int, *, text_limit: int) -> SlideStep:
    normalized = _normalize_text(text)
    match = re.match(r"^\s*([^:：]{1,10})[:：]\s*(.+)$", normalized)
    if match:
        label = _clip_text(match.group(1).strip(), 8)
        body = _fit_text(match.group(2).strip(), text_limit)
        return SlideStep(step_label=label or f"{sequence}단계", step_text=body)
    return SlideStep(step_label=f"{sequence}단계", step_text=_fit_text(normalized, text_limit))


def _to_rule_card(text: str, *, title_limit: int, body_limit: int) -> SlideRuleCard:
    normalized = _normalize_text(text)
    title, body = "", normalized
    if ":" in normalized:
        title, body = normalized.split(":", 1)
    elif " -" in normalized:
        title, body = normalized.split(" -", 1)
    title = _clip_text(title.strip() or _fallback_card_title(body), title_limit)
    body = _fit_text(body.strip() or normalized, body_limit)
    return SlideRuleCard(title=title, body=body)


def _fallback_card_title(body: str) -> str:
    concept = _top_concepts([body], max_count=1)
    return _clip_text(concept or "핵심 규칙", 18)


def _remove_duplicate_actions(steps: list[SlideStep], actions: list[str]) -> list[str]:
    filtered: list[str] = []
    step_keys = [_comparison_key(step.step_text) for step in steps]
    step_concepts = [_concept_tokens(step.step_text) for step in steps]
    for action in actions:
        action_key = _comparison_key(action)
        action_concepts = _concept_tokens(action)
        duplicated = any(
            action_key == step_key
            or action_key in step_key
            or step_key in action_key
            or (action_concepts and action_concepts == concepts)
            for step_key, concepts in zip(step_keys, step_concepts)
            if step_key
        )
        if duplicated:
            continue
        filtered.append(action)
    return filtered


def _ensure_minimum_gap_bullets(
    gap_chunk: list[str],
    *,
    risk_chunk: list[str],
    to_be_items: list[str],
    text_limit: int,
) -> list[str]:
    prepared = gap_chunk[:]
    if len(prepared) >= 2:
        return prepared
    for item in to_be_items:
        candidate = _fit_text(f"목표 구조 기준: {item}", text_limit)
        if candidate and candidate not in prepared:
            prepared.append(candidate)
        if len(prepared) >= 2:
            return prepared[:2]
    for item in risk_chunk:
        candidate = _fit_text(f"리스크 기준: {item}", text_limit)
        if candidate and candidate not in prepared:
            prepared.append(candidate)
        if len(prepared) >= 2:
            return prepared[:2]
    return prepared


def _ensure_minimum_rule_cards(
    cards: list[SlideRuleCard],
    flow_items: list[str],
    *,
    body_limit: int,
    title_limit: int,
) -> list[SlideRuleCard]:
    prepared = cards[:]
    if len(prepared) >= 2:
        return prepared
    for item in flow_items:
        if len(prepared) >= 2:
            break
        prepared.append(
            SlideRuleCard(
                title=_clip_text("구조 흐름", title_limit),
                body=_fit_text(item, body_limit),
            )
        )
    return prepared


def _split_as_is_gap_by_char_threshold(
    slide: SlideSchema,
    *,
    threshold: int,
    gap_text_limit: int,
    risk_text_limit: int,
    use_report_total: bool = False,
) -> tuple[list[str], list[str]]:
    overflow_gap: list[str] = []
    overflow_risk: list[str] = []
    total_fn = _estimate_report_slide_char_total if use_report_total else _estimate_slide_char_total
    while total_fn(slide) > threshold and len(slide.risk_bullets) > 2:
        overflow_risk.insert(0, _fit_text(slide.risk_bullets.pop(), risk_text_limit))
    while total_fn(slide) > threshold and len(slide.gap_bullets) > 2:
        overflow_gap.insert(0, _fit_text(slide.gap_bullets.pop(), gap_text_limit))
    while total_fn(slide) > threshold and len(slide.risk_bullets) > 1:
        overflow_risk.insert(0, _fit_text(slide.risk_bullets.pop(), risk_text_limit))
    slide.decision_message = _build_decision_message(
        slide.to_be_bullets if slide.to_be_bullets else slide.gap_bullets,
        limit=_SLIDE_TYPE_POLICY["as_is_gap"]["decision_limit"],
    )
    return overflow_gap, overflow_risk


def _split_design_first_slide_by_soft_limit(
    slide: SlideSchema,
    *,
    soft_limit: int,
) -> list[str]:
    overflow_flow_bullets: list[str] = []
    while _estimate_report_slide_char_total(slide) > soft_limit and slide.flow_bullets:
        overflow_flow_bullets.insert(0, slide.flow_bullets.pop())
    return overflow_flow_bullets


def _split_design_by_char_threshold(
    slide: SlideSchema,
    *,
    threshold: int,
    minimum_cards: int,
) -> list[SlideRuleCard]:
    overflow_cards: list[SlideRuleCard] = []
    while _estimate_slide_char_total(slide) > threshold and len(slide.rule_cards) > minimum_cards:
        overflow_cards.insert(0, slide.rule_cards.pop())
    return overflow_cards


def _reabsorb_as_is_gap_continuations(
    slides: list[SlideSchema],
    *,
    policy: dict[str, Any],
) -> list[SlideSchema]:
    if len(slides) <= 1:
        return _annotate_continuation_values(slides, slide_type="as_is_gap", policy=policy)
    absorbed: list[SlideSchema] = [slides[0]]
    for slide in slides[1:]:
        previous = absorbed[-1]
        _set_continuation_value_meta(slide, *_assess_continuation_value(slide, policy=policy))
        if slide.continuation_value != "absorb_candidate":
            absorbed.append(slide)
            continue
        summary = _summarize_as_is_gap_continuation(slide, limit=policy["risk_text_limit"])
        if not summary:
            absorbed.append(slide)
            continue
        candidate = previous.model_copy(deep=True)
        candidate.risk_bullets = candidate.risk_bullets + [summary]
        if len(candidate.risk_bullets) > policy["risk_limit"]:
            absorbed.append(slide)
            continue
        if _estimate_slide_char_total(candidate) > policy["slide_char_threshold"]:
            absorbed.append(slide)
            continue
        previous.risk_bullets = candidate.risk_bullets
        _append_absorbed_summary(previous, summary)
    resequenced = _resequence_chapter_slides(absorbed, slide_id_prefix="approach", continuation_reason="gap_risk_overflow")
    return _annotate_continuation_values(resequenced, slide_type="as_is_gap", policy=policy)


def _summarize_as_is_gap_continuation(slide: SlideSchema, *, limit: int) -> str:
    items = [item for item in slide.gap_bullets + slide.risk_bullets if item]
    if not items:
        return ""
    if len(items) == 1:
        return _fit_text(items[0], limit)
    concepts = _top_concepts(items, max_count=2)
    if concepts:
        return _fit_text(f"{concepts} 검토 포인트는 후속 정합성 확인으로 이어집니다", limit)
    return _fit_text(items[0], limit)


def _reabsorb_design_continuations(
    slides: list[SlideSchema],
    *,
    policy: dict[str, Any],
) -> list[SlideSchema]:
    if len(slides) <= 1:
        return _annotate_continuation_values(slides, slide_type="design", policy=policy)
    absorbed: list[SlideSchema] = [slides[0]]
    for slide in slides[1:]:
        previous = absorbed[-1]
        _set_continuation_value_meta(slide, *_assess_continuation_value(slide, policy=policy))
        if slide.continuation_value != "absorb_candidate":
            absorbed.append(slide)
            continue
        summary = _summarize_design_flow(previous.flow_bullets + slide.flow_bullets, limit=policy["flow_text_limit"])
        if not summary:
            absorbed.append(slide)
            continue
        candidate = previous.model_copy(deep=True)
        candidate.flow_bullets = [summary]
        if _estimate_report_slide_char_total(candidate) > policy["slide_char_threshold"]:
            absorbed.append(slide)
            continue
        previous.flow_bullets = candidate.flow_bullets
        previous.density_tier = _density_tier(
            len(previous.rule_cards) + len(previous.flow_bullets) + len(previous.entity_blocks) + len(previous.interface_points)
        )
        _append_absorbed_summary(previous, summary)
    resequenced = _resequence_chapter_slides(absorbed, slide_id_prefix="design", continuation_reason="design_rule_card_overflow")
    return _annotate_continuation_values(resequenced, slide_type="design", policy=policy)


def _summarize_design_flow(items: list[str], *, limit: int) -> str:
    tokens: list[str] = []
    joined = " ".join(items)
    checks = (
        ("lot", "lot"),
        ("환차손익", "환차손익"),
        ("전표", "전표"),
        ("gl", "GL"),
        ("기준번호", "기준번호"),
    )
    lowered = joined.lower()
    for needle, label in checks:
        if needle in lowered and label not in tokens:
            tokens.append(label)
    subject = ", ".join(tokens[:4]) if tokens else _top_concepts(items, max_count=2)
    if not subject:
        return _fit_text(items[0], limit) if items else ""
    return _fit_text(f"{subject} 흐름을 같은 계산 기준으로 정렬합니다", limit)


def _annotate_continuation_values(
    slides: list[SlideSchema],
    *,
    slide_type: str,
    policy: dict[str, Any],
) -> list[SlideSchema]:
    for slide in slides:
        value, score = _assess_continuation_value(slide, policy=policy)
        _set_continuation_value_meta(slide, value, score)
    return slides


def _assess_continuation_value(
    slide: SlideSchema,
    *,
    policy: dict[str, Any],
) -> tuple[str, int]:
    if not slide.is_continuation:
        return "not_applicable", 0
    if slide.slide_type == "as_is_gap":
        score = 0
        if len(slide.gap_bullets) >= 2:
            score += 1
        if len(slide.risk_bullets) >= 2:
            score += 1
        if _estimate_report_slide_char_total(slide) >= policy["as_is_gap_continuation_absorb_char_total"]:
            score += 1
        if slide.decision_message:
            score += 1
        return ("retain", score) if score >= 2 else ("absorb_candidate", score)
    if slide.slide_type == "design":
        score = 0
        if slide.rule_cards:
            score += 2
        if slide.rule_cards and (slide.entity_blocks or slide.interface_points):
            score += 1
        if len(slide.flow_bullets) >= 3:
            score += 1
        if _estimate_report_slide_char_total(slide) >= policy["design_continuation_absorb_char_total"]:
            score += 1
        return ("retain", score) if score >= 2 else ("absorb_candidate", score)
    if slide.slide_type == "flow":
        score = 0
        if len(slide.steps) >= 2:
            score += 2
        if slide.action_bullets:
            score += 1
        if _estimate_report_slide_char_total(slide) >= 120:
            score += 1
        return ("retain", score) if score >= 2 else ("absorb_candidate", score)
    if slide.slide_type == "vision":
        score = 0
        if len(slide.future_state_bullets) >= 2:
            score += 2
        elif len(slide.future_state_bullets) == 1:
            score += 1
        if slide.effect_bullets:
            score += 1
        if _estimate_report_slide_char_total(slide) >= 150:
            score += 1
        return ("retain", score) if score >= 2 else ("absorb_candidate", score)
    return "not_applicable", 0


def _set_continuation_value_meta(slide: SlideSchema, value: str, score: int) -> None:
    slide.continuation_value = value
    slide.continuation_value_score = score


def _append_absorbed_summary(slide: SlideSchema, summary: str) -> None:
    existing = slide.absorbed_summary_text.strip()
    slide.absorbed_summary_text = f"{existing} / {summary}".strip(" /") if existing else summary


def _resequence_chapter_slides(
    slides: list[SlideSchema],
    *,
    slide_id_prefix: str,
    continuation_reason: str,
) -> list[SlideSchema]:
    if not slides:
        return slides
    root_slide_id = f"{slide_id_prefix}_01"
    for sequence, slide in enumerate(slides, start=1):
        slide.slide_id = f"{slide_id_prefix}_{sequence:02d}"
        slide.sequence = sequence
        slide.is_continuation = sequence > 1
        slide.continuation_of = root_slide_id if sequence > 1 else ""
        slide.continuation_reason = continuation_reason if sequence > 1 else ""
    return slides


def _should_use_design_meta_sidebar(cards: list[SlideRuleCard]) -> bool:
    if not cards:
        return False
    avg_body_len = sum(len(card.body) for card in cards) / max(1, len(cards))
    if len(cards) >= 4 and avg_body_len >= 48:
        return False
    return True


def _extract_keyword_blocks(items: list[str], keywords: tuple[str, ...], *, limit: int, text_limit: int) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for item in items:
        lowered = item.lower()
        if not any(keyword in lowered for keyword in keywords):
            continue
        clipped = _keyword_block_label(item, keywords=keywords, text_limit=text_limit)
        key = _comparison_key(clipped)
        if not key or key in seen:
            continue
        seen.add(key)
        selected.append(clipped)
        if len(selected) >= limit:
            break
    return selected


def _keyword_block_label(text: str, *, keywords: tuple[str, ...], text_limit: int) -> str:
    lowered = text.lower()
    if keywords == _ENTITY_KEYWORDS:
        if "통화" in text and "계좌" in text:
            return _fit_text("통화 / 계좌 식별값", text_limit)
        if "기준번호" in text:
            return _fit_text("거래 기준번호", text_limit)
        if "lot" in lowered and ("원장" in text or "잔량" in text):
            return _fit_text("lot 원장 / 잔량", text_limit)
        if "환차손익" in text:
            return _fit_text("환차손익 계산값", text_limit)
        if "전표" in text and "gl" in lowered:
            return _fit_text("전표 / GL 반영값", text_limit)
    if keywords == _INTERFACE_KEYWORDS:
        if "전표" in text and "gl" in lowered:
            return _fit_text("전표 / GL 인터페이스", text_limit)
        if "기준번호" in text and ("연계" in text or "interface" in lowered or "gl" in lowered):
            return _fit_text("기준번호 연계", text_limit)
        if "회계" in text or "연계" in text:
            return _fit_text("회계 연계 흐름", text_limit)
    concepts = _top_concepts([text], max_count=2)
    if concepts:
        suffix = " 메타" if keywords == _ENTITY_KEYWORDS else " 연계"
        return _fit_text(f"{concepts}{suffix}", text_limit)
    return _fit_text(text, text_limit)


def _compact_direction_text(text: str, *, text_limit: int) -> str:
    lowered = text.lower()
    if "fifo" in lowered and "분리" in text:
        return _fit_text("FIFO 계산 계층 분리", text_limit)
    if "환차손익" in text and ("고정" in text or "기준" in text):
        return _fit_text("환차손익 계산 기준 고정", text_limit)
    if "전표" in text and "gl" in lowered and ("연결" in text or "기준번호" in text):
        return _fit_text("전표 / GL 기준번호 연결", text_limit)
    concepts = _top_concepts([text], max_count=2)
    if concepts:
        return _fit_text(f"{concepts} 구조 정렬", text_limit)
    return _fit_text(text, text_limit)


def _extract_effect_bullets(items: list[str], *, limit: int, text_limit: int) -> list[str]:
    action_markers = ("분리", "고정", "연결", "정렬", "설계", "구조화")
    explicit_effects = [
        _fit_text(item, text_limit)
        for item in items
        if any(keyword in item.lower() for keyword in _EFFECT_KEYWORDS)
        and not any(marker in item for marker in action_markers)
    ]
    return _dedupe_items(explicit_effects, limit=text_limit)[:limit]


def _build_headline(slide_type: str, items: list[str], *, limit: int) -> str:
    concepts = _top_concepts(items, max_count=2)
    if not concepts:
        return _DEFAULT_HEADLINES[slide_type]
    suffix_map = {
        "overview": " 개요",
        "as_is_gap": " GAP 정리",
        "flow": " 구현 흐름",
        "design": " 설계 기준",
        "vision": " 적용 방향",
    }
    return _clip_text(f"{concepts}{suffix_map[slide_type]}", limit)


def _build_decision_message(items: list[str], *, limit: int) -> str:
    if not items:
        return ""
    return _fit_text(items[0], limit)


def _build_overview_tagline(scope_items: list[str], constraint_items: list[str], *, limit: int) -> str:
    if scope_items:
        return _fit_text(scope_items[0], limit)
    if constraint_items:
        return _fit_text(constraint_items[0], limit)
    return ""


def _ensure_overview_density_balance(
    context_items: list[str],
    scope_items: list[str],
    constraint_items: list[str],
    *,
    scope_limit: int,
) -> tuple[list[str], list[str], list[str]]:
    prepared_scope = scope_items[:]
    if not prepared_scope and context_items:
        concepts = _top_concepts(context_items + constraint_items, max_count=2)
        summary = _fit_text(f"{concepts} 범위를 우선 검토합니다" if concepts else "핵심 범위를 우선 검토합니다", scope_limit)
        if summary:
            prepared_scope.append(summary)
    return context_items, _dedupe_items(prepared_scope, limit=scope_limit), constraint_items


def _build_flow_footer_note(sequence: int, total: int) -> str:
    if total <= 1:
        return ""
    if sequence < total:
        return "후속 단계는 다음 슬라이드에서 이어집니다."
    return "단계 흐름 분할을 마쳤습니다."


def _build_closing_statement(items: list[str], *, limit: int) -> str:
    if not items:
        return ""
    concepts = _top_concepts(items, max_count=2)
    if not concepts:
        return ""
    return _fit_text(f"{concepts} 기준을 같은 흐름으로 정렬합니다.", limit)


def _overview_layout_hint(scope_items: list[str], constraint_items: list[str], sequence: int) -> str:
    if sequence > 1:
        return "overview_meta_split"
    if scope_items and constraint_items:
        return "overview_context_scope_constraints"
    if scope_items or constraint_items:
        return "overview_context_scope"
    return "overview_context_only"


def _design_layout_hint(
    flow_bullets: list[str],
    entity_blocks: list[str],
    interface_points: list[str],
    *,
    continuation: bool,
) -> str:
    if continuation:
        return "design_cards_continuation"
    if entity_blocks or interface_points:
        return "rule_cards_with_meta_sidebar"
    if flow_bullets:
        return "rule_cards_with_bottom_flow"
    return "rule_cards_only"


def _vision_layout_hint(effect_bullets: list[str], *, continuation: bool, item_count: int) -> str:
    if continuation:
        return "vision_continuation"
    if effect_bullets:
        return "future_state_with_effect"
    if item_count <= 3:
        return "future_state_pillars"
    return "vision_single_panel"


def _clip_and_dedupe(items: Iterable[str], limit: int) -> list[str]:
    normalized = [_fit_text(item, limit) for item in items or []]
    return _dedupe_items(normalized, limit=limit)


def _dedupe_items(items: Iterable[str], *, limit: int) -> list[str]:
    deduped: list[str] = []
    seen_keys: list[str] = []
    for item in items:
        candidate = _clip_text(_normalize_text(item), limit)
        if not candidate:
            continue
        key = _comparison_key(candidate)
        if any(
            key == other_key
            or key in other_key
            or other_key in key
            for other_key in seen_keys
        ):
            continue
        deduped.append(candidate)
        seen_keys.append(key)
    return deduped


def _density_tier(item_count: int) -> str:
    if item_count <= 3:
        return "light"
    if item_count <= 6:
        return "balanced"
    return "dense"


def _estimate_slide_char_total(slide: SlideSchema) -> int:
    texts: list[str] = []
    if slide.headline:
        texts.append(slide.headline)
    if slide.tagline:
        texts.append(slide.tagline)
    if slide.slide_type == "as_is_gap":
        texts.extend(slide.as_is_bullets)
        texts.extend(slide.gap_bullets)
        texts.extend(slide.to_be_bullets)
        texts.extend(slide.risk_bullets)
        if slide.decision_message:
            texts.append(slide.decision_message)
    elif slide.slide_type == "design":
        texts.extend(card.title for card in slide.rule_cards)
        texts.extend(card.body for card in slide.rule_cards)
        if slide.layout_hint == "rule_cards_with_meta_sidebar":
            texts.extend(slide.entity_blocks)
            texts.extend(slide.interface_points)
        elif slide.flow_bullets:
            texts.extend(slide.flow_bullets)
    return sum(len(text) for text in texts if text)


def _estimate_report_slide_char_total(slide: SlideSchema) -> int:
    texts: list[str] = []
    for value in (slide.headline, slide.tagline, slide.decision_message, slide.footer_note, slide.closing_statement):
        if value:
            texts.append(value)
    for collection in (
        slide.context_bullets,
        slide.scope_bullets,
        slide.constraint_bullets,
        slide.as_is_bullets,
        slide.gap_bullets,
        slide.to_be_bullets,
        slide.risk_bullets,
        slide.action_bullets,
        slide.flow_bullets,
        slide.entity_blocks,
        slide.interface_points,
        slide.future_state_bullets,
        slide.effect_bullets,
    ):
        texts.extend(collection)
    texts.extend(step.step_text for step in slide.steps)
    texts.extend(card.body for card in slide.rule_cards)
    return sum(len(text) for text in texts if text)


def _top_concepts(items: list[str], *, max_count: int) -> str:
    scores: dict[str, int] = {}
    for item in items:
        lowered = item.lower()
        for concept in _DOMAIN_CONCEPTS:
            if concept in lowered:
                scores[concept] = scores.get(concept, 0) + 2
        for token in _concept_tokens(item):
            scores[token] = scores.get(token, 0) + 1
    ordered = sorted(scores.items(), key=lambda item: (-item[1], len(item[0]), item[0]))
    selected = [label.upper() if label == "gl" else label for label, _ in ordered[:max_count]]
    return ", ".join(selected)


def _concept_tokens(text: str) -> set[str]:
    lowered = re.sub(r"[^0-9a-zA-Z가-힣\s]", " ", text.lower())
    tokens = [token for token in lowered.split() if len(token) >= 2]
    normalized_tokens: set[str] = set()
    for token in tokens:
        if token in _CONCEPT_STOPWORDS:
            continue
        if token.isdigit():
            continue
        normalized_tokens.add(token)
    return normalized_tokens


def _comparison_key(text: str) -> str:
    normalized = re.sub(r"[^0-9a-zA-Z가-힣]", "", text.lower())
    return normalized[:120]


def _normalize_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").strip())
    normalized = re.sub(r"^\[[^\]]+\]\s*", "", normalized)
    replacements = (
        ("하는 것이 필요합니다", "합니다"),
        ("할 필요가 있습니다", "합니다"),
        ("하는 편이 적절합니다", "합니다"),
        ("하는 편이 안전합니다", "합니다"),
        ("해야 합니다", "합니다"),
        ("해야 한다", "합니다"),
        ("해야합니다", "합니다"),
        ("우선 보존합니다.", "우선 보존합니다"),
        ("구조로 정리합니다.", "구조로 정리합니다"),
        ("기준으로 고정합니다.", "기준으로 고정합니다"),
        ("기준으로 정리합니다.", "기준으로 정리합니다"),
    )
    for old, new in replacements:
        normalized = normalized.replace(old, new)
    for old, new in _COMPRESSION_REPLACEMENTS:
        normalized = normalized.replace(old, new)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip(" ,")


def _fit_text(text: str, limit: int) -> str:
    normalized = _normalize_text(text)
    if len(normalized) <= limit:
        return normalized
    recomposed = _recompose_statement(normalized, limit)
    if len(recomposed) <= limit:
        return recomposed
    return _clip_text(recomposed, limit)


def _recompose_statement(text: str, limit: int) -> str:
    match = re.match(r"^(.+?)(해야|해)\s+(.+)$", text)
    if match:
        action = match.group(1).strip()
        effect = match.group(3).strip()
        effect = effect.replace("유지됩니다", "유지합니다").replace("줄일 수 있습니다", "줄입니다")
        candidate = f"{action}해 {effect}"
        if len(candidate) <= limit:
            return candidate
    if ":" in text:
        title, body = text.split(":", 1)
        body = body.strip()
        if len(body) <= limit:
            return body
        if len(title) + 2 < limit:
            return f"{title.strip()}: {body}"
    return text


def _clip_text(text: str, limit: int) -> str:
    normalized = _normalize_text(text)
    if len(normalized) <= limit:
        return normalized
    trailing_number_match = re.search(r"(?:\s|^)(\d+)\D*$", normalized)
    trailing_suffix = ""
    if trailing_number_match:
        trailing_suffix = f" {trailing_number_match.group(1)}"
    clip_budget = max(1, limit - 1 - len(trailing_suffix))
    clipped = normalized[:clip_budget].rstrip(" ,.;:")
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.rstrip(" ,.;:") + "…" + trailing_suffix
