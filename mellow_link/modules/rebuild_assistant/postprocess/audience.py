from __future__ import annotations

PRIORITY_SECTION_KEYS: dict[str, set[str]] = {
    "developer": {
        "grounded_business_rules",
        "retained_contracts",
        "recomposition_draft",
        "risks",
        "execution_plan",
    },
    "manager": {
        "one_line_conclusion",
        "risks",
        "priority_split_items",
        "execution_plan",
        "recommended_option",
    },
    "client": {
        "one_line_conclusion",
        "recommended_option",
        "recommended_directions",
        "executive_summary_v2",
    },
}

AUDIENCE_PREFIXES: dict[str, tuple[str, str]] = {
    "developer": ("구현 기준", "참고 판단"),
    "manager": ("운영 판단", "보조 판단"),
    "client": ("보고 기준", "참고 설명"),
}


def build_audience_variant(section_key: str, polished_text: str, audience: str) -> str:
    primary_prefix, secondary_prefix = AUDIENCE_PREFIXES.get(audience, ("핵심 판단", "참고 판단"))
    prefix = primary_prefix if section_key in PRIORITY_SECTION_KEYS.get(audience, set()) else secondary_prefix
    if not polished_text:
        return ""
    return f"{prefix}: {polished_text}"
