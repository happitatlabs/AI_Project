from __future__ import annotations

from collections import defaultdict

from .schemas import AnonymizationAsset, CanonicalAnonymizedSource, IdentifierToken, MaskingLevel


class IdentifierMapper:
    """Builds stable token replacements and canonical anonymized sources."""

    _PREFIXES = {
        "class": "CLS",
        "function": "FUNC",
        "variable": "VAR",
        "table": "TBL",
        "column": "COL",
        "api_path": "API",
    }

    def build_mapping(self, asset: AnonymizationAsset, tokens: list[IdentifierToken]) -> dict[str, dict[str, str]]:
        counters: dict[str, int] = defaultdict(int)
        mapping: dict[str, dict[str, str]] = defaultdict(dict)
        for token in tokens:
            counters[token.kind] += 1
            prefix = self._PREFIXES.get(token.kind, token.kind.upper())
            mapping[token.kind][token.value] = f"{prefix}_{counters[token.kind]:03d}"
        return dict(mapping)

    def apply_mapping(
        self,
        *,
        asset: AnonymizationAsset,
        mapping: dict[str, dict[str, str]],
    ) -> CanonicalAnonymizedSource:
        content = asset.content_text or ""
        replacements = sorted(
            (
                (source, target)
                for values in mapping.values()
                for source, target in values.items()
            ),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        for source, target in replacements:
            content = content.replace(source, target)
        return CanonicalAnonymizedSource(
            asset_id=asset.asset_id,
            level=MaskingLevel.FULL,
            language=asset.language,
            content=content,
            replacement_stats={kind: len(values) for kind, values in mapping.items()},
        )
