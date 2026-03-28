from __future__ import annotations

import re

from .schemas import AnonymizationAsset, IdentifierToken


class IdentifierTokenizer:
    """Rule-based tokenizer for MVP anonymization."""

    _PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("class", re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)")),
        ("function", re.compile(r"\b(?:def|function|fn)\s+([A-Za-z_][A-Za-z0-9_]*)")),
        ("table", re.compile(r"\b(?:from|join|update|into)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)),
        ("column", re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=")),
        ("api_path", re.compile(r"(/[A-Za-z0-9_./-]+)")),
    )

    def tokenize(self, asset: AnonymizationAsset) -> list[IdentifierToken]:
        tokens: list[IdentifierToken] = []
        text = asset.content_text or ""
        seen: set[tuple[str, str]] = set()
        for kind, pattern in self._PATTERNS:
            for match in pattern.findall(text):
                value = match if isinstance(match, str) else match[0]
                normalized = (kind, str(value).strip())
                if not normalized[1] or normalized in seen:
                    continue
                seen.add(normalized)
                tokens.append(IdentifierToken(kind=kind, value=normalized[1]))
        return tokens
