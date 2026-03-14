"""
Sensitive text masking utilities.

Goal:
- Prevent accidentally speaking/logging secrets (API keys, claim URLs, tokens).
- If any sensitive pattern is detected, replace the entire text with a safe placeholder.
"""

from __future__ import annotations

import re

MASKED_TEXT = "[민감 정보 마스킹됨]"

# NOTE:
# - Keep this module dependency-free (stdlib only) so it can be imported from anywhere
#   (websocket handler, conversation pipeline, TTS manager, etc.).
_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Generic API key patterns (example from request)
    re.compile(r"\bsk-[a-zA-Z0-9]{20,}\b"),
    # Moltbook API key (observed in this repo: moltbook_sk_...)
    re.compile(r"\bmoltbook_sk_[a-zA-Z0-9_-]{20,}\b"),
    # Claim URL patterns
    re.compile(r"https?://[^\s\"']*/claim/[^\s\"']+"),
    re.compile(r"\b(?:www\.)?moltbook\.com/claim/[^\s\"']+"),
    # Claim token sometimes appears without full URL
    re.compile(r"\bmoltbook_claim_[a-zA-Z0-9_-]{10,}\b"),
)


def mask_sensitive_text(text: str) -> str:
    """
    If `text` contains sensitive tokens/URLs, return MASKED_TEXT, else return original.
    """
    if not isinstance(text, str) or not text:
        return text
    for pat in _SENSITIVE_PATTERNS:
        if pat.search(text):
            return MASKED_TEXT
    return text

