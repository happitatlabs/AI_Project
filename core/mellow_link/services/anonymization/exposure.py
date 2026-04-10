from __future__ import annotations

import re
from typing import Any

from .schemas import SafeAnalysisBundle

# v0 exposure invariants:
# - preview is NOT canonical content. It is a stricter-masked derivative for debug convenience only.
# - validation failure MUST block preview exposure. Summary/findings may remain, but preview must be empty or omitted.
# - bundle_debug is whitelist ONLY. Do not treat it as a free-form dump for nested debug payloads.

POLICY_VERSION = "safe_bundle_exposure_v0"
MAX_SUMMARY_ASSET_COUNTS = 10
MAX_SOURCE_PREVIEWS = 8

ALLOWED_SUMMARY_KEYS = {
    "applied",
    "policy_version",
    "masking_level",
    "total_replacements",
    "canonical_source_count",
    "structure_count",
    "asset_counts",
    "omitted_asset_count",
    "validation_passed",
    "risk_flags",
}
ALLOWED_ASSET_COUNT_KEYS = {"asset_id", "asset_name", "replacement_count"}
ALLOWED_PREVIEW_KEYS = {"asset_id", "asset_name", "language", "replacement_count", "preview_text"}
ALLOWED_BUNDLE_DEBUG_KEYS = {
    "canonical_source_count",
    "structure_count",
    "total_replacements",
    "masking_level",
    "policy_version",
    "omitted_preview_count",
    "validation_passed",
}
FORBIDDEN_USER_DETAIL_KEYS = {
    "sources",
    "structures",
    "content",
    "replacement_stats",
    "source_previews",
    "preview_text",
    "bundle_debug",
    "validation",
    "mapping",
    "original",
    "exports",
    "export_payload",
}
ALLOWED_PREVIEW_KEYWORDS = {
    "and",
    "as",
    "asc",
    "async",
    "await",
    "bool",
    "boolean",
    "break",
    "by",
    "case",
    "class",
    "const",
    "create",
    "date",
    "def",
    "delete",
    "desc",
    "do",
    "else",
    "end",
    "false",
    "float",
    "for",
    "from",
    "function",
    "group",
    "if",
    "import",
    "in",
    "inner",
    "insert",
    "int",
    "into",
    "join",
    "left",
    "let",
    "limit",
    "null",
    "offset",
    "on",
    "or",
    "order",
    "outer",
    "public",
    "private",
    "protected",
    "return",
    "right",
    "select",
    "set",
    "static",
    "string",
    "table",
    "then",
    "true",
    "update",
    "values",
    "var",
    "void",
    "when",
    "where",
    "while",
}
CANONICAL_TOKEN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bCLS_\d+\b"), "[CLASS]"),
    (re.compile(r"\bFUNC_\d+\b"), "[FUNCTION]"),
    (re.compile(r"\bVAR_\d+\b"), "[VARIABLE]"),
    (re.compile(r"\bTBL_\d+\b"), "[TABLE]"),
    (re.compile(r"\bCOL_\d+\b"), "[COLUMN]"),
    (re.compile(r"\bAPI_\d+\b"), "[API]"),
)
PATH_PATTERN = re.compile(r"(https?://[^\s]+|[A-Za-z]:\\[^\s]+|/(?:[A-Za-z0-9_.-]+/?)+)")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
STRING_PATTERN = re.compile(r"('([^'\\]|\\.)*'|\"([^\"\\]|\\.)*\"|`([^`\\]|\\.)*`)")
IDENTIFIER_PATTERN = re.compile(r"(?<!\[)\b[A-Za-z_][A-Za-z0-9_]*\b(?!\])")


def _sum_replacements(stats: dict[str, int] | None) -> int:
    if not isinstance(stats, dict):
        return 0
    total = 0
    for value in stats.values():
        if isinstance(value, int) and value > 0:
            total += value
    return total


def _asset_name_map(bundle: SafeAnalysisBundle) -> dict[str, str]:
    return {asset.asset_id: asset.name for asset in bundle.asset_summary}


def _ordered_asset_ids(bundle: SafeAnalysisBundle, replacement_counts: dict[str, int]) -> list[str]:
    ordered = [asset.asset_id for asset in bundle.asset_summary]
    for asset_id in replacement_counts.keys():
        if asset_id not in ordered:
            ordered.append(asset_id)
    return ordered


def _build_asset_counts(bundle: SafeAnalysisBundle) -> tuple[list[dict[str, Any]], int]:
    replacement_counts: dict[str, int] = {}
    for source in bundle.sources:
        replacement_counts[source.asset_id] = replacement_counts.get(source.asset_id, 0) + _sum_replacements(source.replacement_stats)
    name_map = _asset_name_map(bundle)
    rows = [
        {
            "asset_id": asset_id,
            "asset_name": name_map.get(asset_id, asset_id),
            "replacement_count": replacement_counts.get(asset_id, 0),
        }
        for asset_id in _ordered_asset_ids(bundle, replacement_counts)
    ]
    return rows[:MAX_SUMMARY_ASSET_COUNTS], max(0, len(rows) - MAX_SUMMARY_ASSET_COUNTS)


def _normalize_preview_text(text: str) -> str:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    normalized = re.sub(r"[\s\n\t]+", " ", normalized).strip()
    return normalized[:160]


def _mask_identifier_for_preview(match: re.Match[str]) -> str:
    token = match.group(0)
    if token.lower() in ALLOWED_PREVIEW_KEYWORDS:
        return token
    return "[IDENT]"


def build_preview_masked_text(text: str) -> str:
    masked = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    for pattern, replacement in CANONICAL_TOKEN_PATTERNS:
        masked = pattern.sub(replacement, masked)
    masked = EMAIL_PATTERN.sub("[EMAIL]", masked)
    masked = PATH_PATTERN.sub("[PATH]", masked)
    masked = STRING_PATTERN.sub("[STRING]", masked)
    masked = IDENTIFIER_PATTERN.sub(_mask_identifier_for_preview, masked)
    return _normalize_preview_text(masked)


def _build_source_previews(bundle: SafeAnalysisBundle) -> list[dict[str, Any]]:
    name_map = _asset_name_map(bundle)
    previews: list[dict[str, Any]] = []
    for source in bundle.sources[:MAX_SOURCE_PREVIEWS]:
        previews.append(
            {
                "asset_id": source.asset_id,
                "asset_name": name_map.get(source.asset_id, source.asset_id),
                "language": source.language,
                "replacement_count": _sum_replacements(source.replacement_stats),
                "preview_text": build_preview_masked_text(source.content),
            }
        )
    return previews


def build_anonymization_summary_from_bundle(
    bundle: SafeAnalysisBundle,
    *,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    asset_counts, omitted_asset_count = _build_asset_counts(bundle)
    findings = list((validation or {}).get("findings") or [])
    risk_flags = []
    for finding in findings:
        code = str((finding or {}).get("code") or "").strip()
        if code and code not in risk_flags:
            risk_flags.append(code)
    return {
        "applied": True,
        "policy_version": POLICY_VERSION,
        "masking_level": getattr(bundle.masking_level, "value", str(bundle.masking_level)),
        "total_replacements": sum(_sum_replacements(source.replacement_stats) for source in bundle.sources),
        "canonical_source_count": len(bundle.sources),
        "structure_count": len(bundle.structures),
        "asset_counts": asset_counts,
        "omitted_asset_count": omitted_asset_count,
        "validation_passed": bool((validation or {}).get("passed", True)),
        "risk_flags": risk_flags,
    }


def _build_bundle_debug(
    bundle: SafeAnalysisBundle,
    *,
    total_replacements: int,
    omitted_preview_count: int,
    validation_passed: bool,
) -> dict[str, Any]:
    return {
        "canonical_source_count": len(bundle.sources),
        "structure_count": len(bundle.structures),
        "total_replacements": total_replacements,
        "masking_level": getattr(bundle.masking_level, "value", str(bundle.masking_level)),
        "policy_version": POLICY_VERSION,
        "omitted_preview_count": omitted_preview_count,
        "validation_passed": validation_passed,
    }


def _append_finding(findings: list[dict[str, str]], code: str, message: str) -> None:
    findings.append({"code": code, "message": message})


def _summary_has_forbidden_detail(summary: dict[str, Any]) -> bool:
    if any(key not in ALLOWED_SUMMARY_KEYS for key in summary.keys()):
        return True
    for key in FORBIDDEN_USER_DETAIL_KEYS:
        if key in summary:
            return True
    for item in summary.get("asset_counts") or []:
        if not isinstance(item, dict):
            return True
        if set(item.keys()) != ALLOWED_ASSET_COUNT_KEYS:
            return True
    return False


def _bundle_debug_is_whitelisted(bundle_debug: dict[str, Any]) -> bool:
    if set(bundle_debug.keys()) != ALLOWED_BUNDLE_DEBUG_KEYS:
        return False
    return all(not isinstance(value, (dict, list)) for value in bundle_debug.values())


def _preview_has_residual_identifier(preview_text: str) -> bool:
    if any(pattern.search(preview_text) for pattern, _ in CANONICAL_TOKEN_PATTERNS):
        return True
    if EMAIL_PATTERN.search(preview_text) or PATH_PATTERN.search(preview_text) or STRING_PATTERN.search(preview_text):
        return True
    for token in IDENTIFIER_PATTERN.findall(preview_text):
        if token.lower() not in ALLOWED_PREVIEW_KEYWORDS:
            return True
    return False


def validate_safe_bundle_exposure(
    *,
    bundle: SafeAnalysisBundle,
    user_summary: dict[str, Any],
    source_previews: list[dict[str, Any]],
    bundle_debug: dict[str, Any],
    dev_event_visible_in_user_stream: bool = False,
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    shape_preserved = True
    user_surface_safe = True

    if bundle.guard.contains_original:
        shape_preserved = False
        user_surface_safe = False
        _append_finding(findings, "guard_contains_original", "safe bundle guard allows original content")
    if bundle.guard.contains_mapping:
        shape_preserved = False
        user_surface_safe = False
        _append_finding(findings, "guard_contains_mapping", "safe bundle guard allows mapping content")
    if _summary_has_forbidden_detail(user_summary):
        shape_preserved = False
        user_surface_safe = False
        _append_finding(findings, "user_payload_contains_bundle_detail", "user anonymization summary exposes disallowed detail")
    if dev_event_visible_in_user_stream:
        user_surface_safe = False
        _append_finding(findings, "dev_event_visible_in_user_stream", "debug anonymization event is visible on a user surface")
    if not _bundle_debug_is_whitelisted(bundle_debug):
        shape_preserved = False
        _append_finding(findings, "bundle_debug_non_whitelisted_field", "bundle_debug contains non-whitelisted fields or nested data")
    for preview in source_previews:
        if not isinstance(preview, dict) or set(preview.keys()) != ALLOWED_PREVIEW_KEYS:
            shape_preserved = False
            _append_finding(findings, "preview_masking_residual_identifier", "source preview shape is invalid")
            break
        if _preview_has_residual_identifier(str(preview.get("preview_text") or "")):
            _append_finding(
                findings,
                "preview_masking_residual_identifier",
                f"preview masking left residual identifier-like content for {preview.get('asset_id') or 'unknown_asset'}",
            )
            break
    passed = shape_preserved and user_surface_safe and not findings
    return {
        "passed": passed,
        "shape_preserved": shape_preserved,
        "user_surface_safe": user_surface_safe,
        "findings": findings,
    }


def build_debug_anonymization_report_from_bundle(
    bundle: SafeAnalysisBundle,
    *,
    dev_event_visible_in_user_stream: bool = False,
) -> dict[str, Any]:
    provisional_summary = build_anonymization_summary_from_bundle(bundle)
    preview_candidates = _build_source_previews(bundle)
    provisional_debug = _build_bundle_debug(
        bundle,
        total_replacements=provisional_summary["total_replacements"],
        omitted_preview_count=max(0, len(bundle.sources) - len(preview_candidates)),
        validation_passed=True,
    )
    validation = validate_safe_bundle_exposure(
        bundle=bundle,
        user_summary=provisional_summary,
        source_previews=preview_candidates,
        bundle_debug=provisional_debug,
        dev_event_visible_in_user_stream=dev_event_visible_in_user_stream,
    )
    report_summary = build_anonymization_summary_from_bundle(bundle, validation=validation)
    source_previews = preview_candidates if validation["passed"] else []
    bundle_debug = _build_bundle_debug(
        bundle,
        total_replacements=report_summary["total_replacements"],
        omitted_preview_count=max(0, len(bundle.sources) - len(source_previews)),
        validation_passed=validation["passed"],
    )
    return {
        "policy_version": POLICY_VERSION,
        "report_summary": report_summary,
        "validation": validation,
        "source_previews": source_previews,
        "bundle_debug": bundle_debug,
    }
