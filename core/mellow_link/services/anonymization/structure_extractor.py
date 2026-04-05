from __future__ import annotations

import re

from .schemas import CanonicalAnonymizedSource, StructureArtifact, StructureEdge, StructureNode


class CanonicalStructureExtractor:
    """Extract structure from canonical anonymized source only."""

    _NODE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("class", re.compile(r"\b(CLS_\d{3})\b")),
        ("function", re.compile(r"\b(FUNC_\d{3})\b")),
        ("table", re.compile(r"\b(TBL_\d{3})\b")),
        ("column", re.compile(r"\b(COL_\d{3})\b")),
        ("api", re.compile(r"\b(API_\d{3})\b")),
    )

    def extract(self, canonical_source: CanonicalAnonymizedSource) -> StructureArtifact:
        if not isinstance(canonical_source, CanonicalAnonymizedSource):
            raise TypeError("Structure extraction requires CanonicalAnonymizedSource input")

        nodes: list[StructureNode] = []
        for kind, pattern in self._NODE_PATTERNS:
            for identifier in self._dedupe(pattern.findall(canonical_source.content or "")):
                nodes.append(StructureNode(kind=kind, id=identifier))

        edges: list[StructureEdge] = []
        functions = [node.id for node in nodes if node.kind == "function"]
        tables = [node.id for node in nodes if node.kind == "table"]
        if functions and tables:
            edges.append(StructureEdge(**{"from": functions[0], "to": tables[0], "type": "reads"}))

        return StructureArtifact(
            asset_id=canonical_source.asset_id,
            level=canonical_source.level,
            extracted_from="canonical",
            nodes=nodes,
            edges=edges,
        )

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result
