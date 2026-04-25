from __future__ import annotations

import re
from typing import Any

from .schemas import AnonymizationReviewReport

_DISPLAY_MARKER_MAP: dict[str, str] = {
    "[RISK_PERSON_CANDIDATE]": "[PERSON]",
    "[RISK_ORG_CANDIDATE]": "[ORG]",
    "[WARNING_PROJECT_CANDIDATE]": "[PROJECT]",
    "[RISK_PROJECT_CANDIDATE]": "[PROJECT]",
    "[WARNING_BUSINESS_CANDIDATE]": "[BUSINESS]",
    "[RISK_BUSINESS_CANDIDATE]": "[BUSINESS]",
    "[WARNING_CONTRACT_CANDIDATE]": "[CONTRACT]",
    "[RISK_CONTRACT_CANDIDATE]": "[CONTRACT]",
    "[LOW_CONF_TERM_CANDIDATE]": "[TERM]",
}
_DISPLAY_TOKEN_PREFIX_MAP: dict[str, str] = {
    "CLIENT": "CLIENT",
    "PROJECT": "PROJECT",
    "PERSON": "PERSON",
    "ORG": "ORG",
    "EMAIL": "EMAIL",
    "PHONE": "PHONE",
    "ADDRESS": "ADDRESS",
    "BUSINESS": "BUSINESS",
    "CONTRACT": "CONTRACT",
    "COMPANY": "COMPANY",
    "DEPT": "DEPARTMENT",
}
_DISPLAY_TOKEN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (
        re.compile(rf"(?<![A-Za-z0-9_]){prefix}_\d+(?!\d)"),
        f"[{label}]",
    )
    for prefix, label in _DISPLAY_TOKEN_PREFIX_MAP.items()
)
_DISPLAY_NOTICE_TEXT = "표시 안내: [PERSON], [ORG], [PROJECT], [TERM] 등은 익명 처리된 민감정보입니다."


def to_display_text(value: Any) -> str:
    text = str(value if value is not None else "")
    for source, target in _DISPLAY_MARKER_MAP.items():
        text = text.replace(source, target)
    for pattern, replacement in _DISPLAY_TOKEN_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def transform_display_value(value: Any) -> Any:
    if isinstance(value, str):
        return to_display_text(value)
    if isinstance(value, list):
        return [transform_display_value(item) for item in value]
    if isinstance(value, dict):
        return {key: transform_display_value(item) for key, item in value.items()}
    return value


def build_display_review_report(review_report: AnonymizationReviewReport | None) -> dict[str, Any] | None:
    if review_report is None:
        return None
    return transform_display_value(review_report.model_dump(mode="json"))


def display_notice_text() -> str:
    return _DISPLAY_NOTICE_TEXT
