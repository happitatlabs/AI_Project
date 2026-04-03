from __future__ import annotations

import re

EXACT_REPLACEMENTS = {
    "규칙 규칙": "규칙",
    "조회 조회": "조회",
    "정합성를": "정합성을",
    "분리을": "분리를",
    "여부을": "여부를",
    "조건을을": "조건을",
    "정책 정책": "정책",
    "누락로": "누락으로",
    "금지을": "금지를",
    "규칙야 합니다": "규칙이어야 합니다",
    "이동평균법로": "이동평균법으로",
    "입니다. 입니다.": "입니다.",
    "입니다. 입니다": "입니다.",
}

PATTERN_FORBIDDEN_EXPRESSIONS: dict[str, list[str]] = {
    "amount_threshold": ["상태 전이 계층", "권한 정책 중심"],
    "query_filter": ["상태 전이와 액션 노출 조건", "승인 단계 구조"],
    "workflow": ["권한 정책 중심 모듈형 구조"],
    "validation": ["핵심 조회 정책"],
}


def normalize_whitespace(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    normalized = re.sub(r"\s+([,.:])", r"\1", normalized)
    return normalized.strip()


def collapse_adjacent_duplicate_tokens(text: str) -> str:
    current = text
    while True:
        updated = re.sub(r"\b([A-Za-z가-힣_]+)(\s+\1\b)+", r"\1", current, flags=re.IGNORECASE)
        if updated == current:
            return updated
        current = updated


def dedupe_repeated_clauses(text: str) -> str:
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if part.strip()]
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = re.sub(r"\s+", " ", part).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(part)
    return " ".join(deduped).strip()


def apply_sentence_polish(text: str) -> str:
    polished = (text or "").strip()
    for before, after in EXACT_REPLACEMENTS.items():
        polished = polished.replace(before, after)
    polished = re.sub(r"([가-힣A-Za-z0-9_]+)(?<!으)로 명확하므로", r"\1으로 명확하므로", polished)
    polished = re.sub(r"([가-힣A-Za-z0-9_]+)(?<!으)로 판단되므로", r"\1으로 판단되므로", polished)
    polished = collapse_adjacent_duplicate_tokens(polished)
    polished = dedupe_repeated_clauses(polished)
    polished = normalize_whitespace(polished)
    return polished


def collect_pattern_warnings(primary_judgment: str, text: str) -> list[str]:
    warnings: list[str] = []
    for phrase in PATTERN_FORBIDDEN_EXPRESSIONS.get(primary_judgment, []):
        if phrase and phrase in (text or ""):
            warnings.append(f"{primary_judgment} 문서에 금지 표현이 남아 있습니다: {phrase}")
    return warnings
