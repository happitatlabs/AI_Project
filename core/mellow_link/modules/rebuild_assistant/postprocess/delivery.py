from __future__ import annotations


def _ensure_period(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped:
        return ""
    if stripped.endswith((".", "!", "?")):
        return stripped
    return stripped + "."


def build_delivery_variant(section_key: str, polished_text: str, delivery_mode: str) -> str:
    if not polished_text:
        return ""
    base = polished_text.strip()
    if delivery_mode == "internal_review":
        return _ensure_period(base)
    if delivery_mode == "client_report":
        if section_key in {"one_line_conclusion", "recommended_option", "executive_summary_v2"}:
            if not base.endswith(("필요합니다.", "권장됩니다.", "유지해야 합니다.")):
                base = base.rstrip(".") + " 필요합니다."
        return _ensure_period(base)
    if delivery_mode == "proposal_appendix":
        return _ensure_period(f"부록 기준: {base}")
    return _ensure_period(base)
