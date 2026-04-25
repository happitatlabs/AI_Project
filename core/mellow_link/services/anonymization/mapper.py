from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re

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
        "company_name": "COMPANY",
        "organization_name": "ORG",
        "department_name": "DEPT",
        "person_name": "PERSON",
        "project_name": "PROJECT",
        "client_name": "CLIENT",
        "email": "EMAIL",
        "phone": "PHONE",
        "address": "ADDRESS",
        "business_name": "BUSINESS",
        "contract_name": "CONTRACT",
    }
    _HIGH_CONFIDENCE_ALIAS_KINDS = ("client_name", "company_name", "organization_name")
    _LEGAL_WRAPPER_PATTERN = re.compile(r"^(?:주식회사\s*|㈜\s*|\(주\)\s*)|(?:\s*(?:주식회사|㈜|\(주\)))$")
    _ORG_ALIAS_CONTEXT_PATTERN = re.compile(
        r"^(?:title\s*:\s*)?(?P<value>[가-힣A-Za-z0-9&().\-/]{2,20})"
        r"(?:(?:의)\s*(?:비전|전략|배경|필요성|개요)"
        r"|\s+(?:컨설팅(?:\s+개요)?|기초설계서|원가\s*시스템(?:\s+개선)?|시스템(?:\s+개선)?|개요|비전|전략|현황|프로젝트(?:\s+개요)?|구축(?:\s+방안)?|개선(?:\s+방안)?))\s*$",
        re.IGNORECASE,
    )
    _FILE_ALIAS_PATTERN = re.compile(
        r"^[0-9_\-\s]*(?P<value>[가-힣A-Za-z0-9&().\-/]{2,20})(?:컨설팅|프로젝트|개요|보고서|기초설계서).*$",
        re.IGNORECASE,
    )

    def build_mapping(self, asset: AnonymizationAsset, tokens: list[IdentifierToken]) -> dict[str, dict[str, str]]:
        counters: dict[str, int] = defaultdict(int)
        mapping: dict[str, dict[str, str]] = defaultdict(dict)
        primary_entries: list[tuple[str, str, str]] = []
        for token in tokens:
            counters[token.kind] += 1
            prefix = self._PREFIXES.get(token.kind, token.kind.upper())
            target = f"{prefix}_{counters[token.kind]:03d}"
            mapping[token.kind][token.value] = target
            primary_entries.append((token.kind, token.value, target))
        self._apply_document_alias_mapping(
            asset=asset,
            mapping=mapping,
            counters=counters,
            primary_entries=primary_entries,
        )
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
            replacement_stats={kind: len(set(values.values())) for kind, values in mapping.items()},
        )

    def _apply_document_alias_mapping(
        self,
        *,
        asset: AnonymizationAsset,
        mapping: dict[str, dict[str, str]],
        counters: dict[str, int],
        primary_entries: list[tuple[str, str, str]],
    ) -> None:
        if not (asset.content_text or ""):
            return
        from .document_tokenizer import DocumentEntityTokenizer

        tokenizer = DocumentEntityTokenizer()
        if not tokenizer.supports_asset(asset):
            return

        existing_sources = {source for values in mapping.values() for source in values.keys()}

        for kind, source, target in primary_entries:
            if kind not in self._HIGH_CONFIDENCE_ALIAS_KINDS:
                continue
            for alias in self._derive_legal_entity_aliases(source, tokenizer):
                if alias in existing_sources or alias not in (asset.content_text or ""):
                    continue
                mapping[kind][alias] = target
                existing_sources.add(alias)

        for alias in self._detect_contextual_org_aliases(asset, tokenizer):
            if alias in existing_sources or alias not in (asset.content_text or ""):
                continue
            matched_kind, matched_target = self._match_existing_org_target(alias, primary_entries, tokenizer)
            if matched_kind and matched_target:
                mapping[matched_kind][alias] = matched_target
                existing_sources.add(alias)
                continue
            counters["organization_name"] += 1
            target = f"{self._PREFIXES['organization_name']}_{counters['organization_name']:03d}"
            mapping["organization_name"][alias] = target
            existing_sources.add(alias)

    def _derive_legal_entity_aliases(self, value: str, tokenizer) -> list[str]:
        normalized = tokenizer._normalize_value(value)
        stripped = self._strip_legal_wrapper(normalized, tokenizer)
        aliases: list[str] = []
        if stripped and stripped != normalized and self._is_viable_contextual_org_alias(stripped, tokenizer):
            aliases.append(stripped)
        return aliases

    def _detect_contextual_org_aliases(self, asset: AnonymizationAsset, tokenizer) -> list[str]:
        evidence_by_alias: dict[str, set[str]] = defaultdict(set)
        for line_index, raw_line in enumerate((asset.content_text or "").splitlines()):
            stripped = raw_line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if lowered in {"[sml v1]", "texts:", "tables:", "charts:", "notes:", "visual_elements:"}:
                continue
            if lowered.startswith(("presentation_file:", "slide_count:", "layout:", "[slide ")):
                continue
            normalized_line = tokenizer._normalize_bullet_content(stripped)
            match = self._ORG_ALIAS_CONTEXT_PATTERN.match(normalized_line)
            if not match:
                continue
            alias = tokenizer._normalize_value(match.group("value"))
            if not self._is_viable_contextual_org_alias(alias, tokenizer):
                continue
            evidence_by_alias[alias].add(f"line:{line_index}")

        stem = Path(asset.name or "").stem
        if stem:
            file_match = self._FILE_ALIAS_PATTERN.match(stem)
            if file_match:
                alias = tokenizer._normalize_value(file_match.group("value"))
                if self._is_viable_contextual_org_alias(alias, tokenizer):
                    evidence_by_alias[alias].add("filename")

        return sorted(alias for alias, evidence in evidence_by_alias.items() if len(evidence) >= 2)

    def _match_existing_org_target(
        self,
        alias: str,
        primary_entries: list[tuple[str, str, str]],
        tokenizer,
    ) -> tuple[str | None, str | None]:
        normalized_alias = tokenizer._normalize_value(alias)
        for kind in self._HIGH_CONFIDENCE_ALIAS_KINDS:
            for entry_kind, source, target in primary_entries:
                if entry_kind != kind:
                    continue
                source_base = self._strip_legal_wrapper(source, tokenizer)
                if normalized_alias == source_base:
                    return kind, target
        return None, None

    def _strip_legal_wrapper(self, value: str, tokenizer) -> str:
        previous = tokenizer._normalize_value(value)
        while previous:
            updated = tokenizer._normalize_value(self._LEGAL_WRAPPER_PATTERN.sub("", previous))
            if updated == previous:
                return updated
            previous = updated
        return previous

    def _is_viable_contextual_org_alias(self, value: str, tokenizer) -> bool:
        normalized = tokenizer._normalize_value(value)
        if len(normalized) < 2 or not re.search(r"[가-힣]", normalized):
            return False
        if tokenizer.is_generic_document_phrase(normalized):
            return False
        if normalized in getattr(tokenizer, "_NON_REPLACEABLE_LABELLESS_PHRASES", set()):
            return False
        return True
