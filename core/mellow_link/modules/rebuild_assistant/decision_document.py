from __future__ import annotations

import re
from typing import Iterable


_ACTION_ENDING_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\s*하는 것이 필요합니다[.]?$", ""),
    (r"\s*해야 합니다[.]?$", ""),
    (r"\s*할 필요가 있습니다[.]?$", ""),
    (r"\s*가 필요합니다[.]?$", ""),
    (r"\s*이 필요합니다[.]?$", ""),
    (r"\s*입니다[.]?$", ""),
)

_RATIONALE_BANNED_TOKENS = (
    "필요합니다",
    "해야 합니다",
    "할 필요가 있습니다",
    "권장합니다",
)


def build_decision_brief(
    *,
    summary: str,
    rationale_candidates: Iterable[str],
    action_candidates: Iterable[str],
    rationale_limit: int = 3,
    action_limit: int = 3,
) -> dict[str, object]:
    decision_summary = _clean_summary(summary)
    rationale_lines = _collect_rationales(
        rationale_candidates,
        limit=rationale_limit,
        exclude=(decision_summary,),
    )
    action_lines = _collect_actions(
        action_candidates,
        limit=action_limit,
        exclude=(decision_summary, *rationale_lines),
    )
    return {
        "decision_summary": decision_summary,
        "rationale_lines": rationale_lines,
        "action_lines": action_lines,
    }


def render_decision_brief_markdown(brief: dict[str, object]) -> list[str]:
    summary = str(brief.get("decision_summary") or "").strip() or "-"
    rationales = [str(item).strip() for item in (brief.get("rationale_lines") or []) if str(item).strip()]
    actions = [str(item).strip() for item in (brief.get("action_lines") or []) if str(item).strip()]
    return [
        "## 결정 요약",
        summary,
        "",
        "## 판단 근거",
        *(f"- {item}" for item in (rationales or ["해당 없음"])),
        "",
        "## 실행 조치",
        *(f"- {item}" for item in (actions or ["해당 없음"])),
    ]


def _collect_rationales(candidates: Iterable[str], *, limit: int, exclude: Iterable[str]) -> list[str]:
    preferred: list[str] = []
    fallback: list[str] = []
    excluded = {_normalize_semantic_key(item) for item in exclude if str(item).strip()}
    for raw in candidates:
        cleaned = _clean_text(raw)
        if not cleaned:
            continue
        key = _normalize_semantic_key(cleaned)
        if not key or key in excluded:
            continue
        if _looks_like_action(cleaned):
            softened = _soften_as_observation(cleaned)
            if softened:
                fallback.append(softened)
            continue
        preferred.append(_ensure_sentence(_replace_report_tone(cleaned)))
    return _unique_lines([*preferred, *fallback], limit=limit)


def _collect_actions(candidates: Iterable[str], *, limit: int, exclude: Iterable[str]) -> list[str]:
    selected: list[str] = []
    excluded = {_normalize_semantic_key(item) for item in exclude if str(item).strip()}
    for raw in candidates:
        cleaned = _to_action_phrase(raw)
        key = _normalize_semantic_key(cleaned)
        if not cleaned or not key or key in excluded:
            continue
        selected.append(cleaned)
    return _unique_lines(selected, limit=limit)


def _clean_summary(value: str) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        return "-"
    return _ensure_sentence(_replace_report_tone(cleaned))


def _soften_as_observation(value: str) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        return ""
    if "자료" in cleaned and ("확보" in cleaned or "보완" in cleaned):
        softened = cleaned.replace("확보", "부족").replace("보완", "누락")
        softened = re.sub(r"\s*하는 것이 필요합니다[.]?$", "", softened)
        softened = re.sub(r"\s*가 필요합니다[.]?$", "", softened)
        softened = re.sub(r"\s*이 필요합니다[.]?$", "", softened)
        return _ensure_sentence(f"{softened} 상태임")
    if "검토" in cleaned:
        stem = _to_action_phrase(cleaned)
        if stem:
            return _ensure_sentence(f"{stem} 지점이 남아 있음")
    return ""


def _to_action_phrase(value: str) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        return ""
    cleaned = _replace_report_tone(cleaned)
    for pattern, replacement in _ACTION_ENDING_PATTERNS:
        cleaned = re.sub(pattern, replacement, cleaned)
    cleaned = cleaned.strip(" .")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _clean_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^\s*[-*]\s*", "", text)
    text = " ".join(text.split())
    return text


def _replace_report_tone(value: str) -> str:
    text = value
    replacements = (
        ("확인되었습니다.", "드러남."),
        ("확인되었습니다", "드러남"),
        ("확인됩니다.", "드러남."),
        ("확인됩니다", "드러남"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _ensure_sentence(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    if cleaned.endswith((".", "!", "?")):
        return cleaned
    return f"{cleaned}."


def _looks_like_action(value: str) -> bool:
    return any(token in value for token in _RATIONALE_BANNED_TOKENS)


def _unique_lines(items: Iterable[str], *, limit: int) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        cleaned = str(item or "").strip()
        key = _normalize_semantic_key(cleaned)
        if not cleaned or not key or key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
        if len(output) >= max(limit, 0):
            break
    return output


def _normalize_semantic_key(value: str) -> str:
    cleaned = re.sub(r"[\s\-_./,:;(){}\[\]<>]+", "", str(value or "").lower())
    return cleaned
