from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .document_tokenizer import DocumentEntityTokenizer
from .exposure import build_preview_masked_text
from .schemas import (
    AnonymizationAsset,
    AnonymizationReviewReport,
    CanonicalAnonymizedSource,
    ReviewAssetPreview,
    ReviewDebugCandidateEvidence,
    ReviewDetectedType,
    ReviewEntityCandidate,
    ReviewRoleTokenSummary,
    ReviewStructureCheck,
    SafeAnalysisBundle,
)

_ROLE_META: dict[str, tuple[str, str]] = {
    "client_name": ("CLIENT", "고객사명"),
    "company_name": ("COMPANY", "회사명"),
    "organization_name": ("ORG", "기관명"),
    "department_name": ("DEPT", "부서명"),
    "person_name": ("PERSON", "인명"),
    "project_name": ("PROJECT", "프로젝트명"),
    "business_name": ("BUSINESS", "사업명"),
    "contract_name": ("CONTRACT", "계약명"),
    "email": ("EMAIL", "이메일"),
    "phone": ("PHONE", "전화번호"),
    "address": ("ADDRESS", "주소"),
}
_NON_ROLE_CANDIDATE_META: dict[str, tuple[str, str]] = {
    "low_conf_term": ("LOW_CONF_TERM", "저신뢰 용어 후보"),
}
_ROLE_KIND_SET = set(_ROLE_META.keys())
_CANDIDATE_KIND_SET = _ROLE_KIND_SET | set(_NON_ROLE_CANDIDATE_META.keys())
_RISK_KIND_SET = {
    "client_name",
    "company_name",
    "organization_name",
    "department_name",
    "person_name",
    "email",
    "phone",
    "address",
}
_WARNING_KIND_SET = {
    "project_name",
    "business_name",
    "contract_name",
    "low_conf_term",
}
_TOKEN_ONLY_PATTERN = re.compile(
    r"^\s*(?:[-*]\s*)?(?:title\s*:\s*)?(?:[A-Z]+_\d{3}|\[[A-Z_]+\])(?:\s+(?:[A-Z]+_\d{3}|\[[A-Z_]+\]))*\s*$"
)
_SLIDE_HEADER_PATTERN = re.compile(r"^\[SLIDE\s+(?P<slide>\d+)\]\s*$", re.IGNORECASE)
_TITLE_PATTERN = re.compile(r"^title\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE)
_LABELLED_LINE_PATTERN = re.compile(r"^(?:[-*]\s*)?[^:：]{1,24}\s*[:：]\s*.+$")
_SECTION_PATTERN = re.compile(r"^(texts|tables|charts|notes|visual_elements)\s*:\s*$", re.IGNORECASE)
_CONTEXTUAL_ORG_DEBUG_PATTERN = re.compile(
    r"^(?:title\s*:\s*)?(?P<value>[가-힣A-Za-z0-9&().\-/]{2,20})"
    r"(?:(?:의)\s*(?:비전|전략|배경|필요성|개요)"
    r"|\s+(?:컨설팅(?:\s+개요)?|기초설계서|원가\s*시스템(?:\s+개선)?|시스템(?:\s+개선)?|개요|비전|전략|현황|프로젝트(?:\s+개요)?|구축(?:\s+방안)?|개선(?:\s+방안)?))\s*$",
    re.IGNORECASE,
)
_MASKED_ORG_TOKEN_PATTERN = re.compile(r"(?<![A-Za-z0-9_])(?:CLIENT|COMPANY|ORG)_\d+(?!\d)")


@dataclass(slots=True)
class _Candidate:
    severity: str
    entity_type_guess: str
    label: str
    asset_id: str
    asset_name: str
    slide: str
    line_index: int
    locator: str
    reason: str
    raw_value: str
    source_line: str
    replace_in_text: bool


@dataclass(slots=True)
class AnonymizationReviewArtifacts:
    review_report: AnonymizationReviewReport | None
    llm_safe_sources: list[CanonicalAnonymizedSource]


def build_anonymization_review_artifacts(
    *,
    assets: list[AnonymizationAsset],
    safe_bundle: SafeAnalysisBundle,
    canonical_sources: list[CanonicalAnonymizedSource],
    tokens_by_asset: dict[str, list],
    document_tokenizer: DocumentEntityTokenizer | None = None,
) -> AnonymizationReviewArtifacts:
    tokenizer = document_tokenizer or DocumentEntityTokenizer()
    target_assets = [asset for asset in assets if tokenizer.supports_asset(asset)]
    if not target_assets:
        return AnonymizationReviewArtifacts(
            review_report=None,
            llm_safe_sources=[source.model_copy(deep=True) for source in canonical_sources],
        )

    canonical_map = {source.asset_id: source for source in canonical_sources}
    role_counter: Counter[str] = Counter()
    target_tokens_by_asset: dict[str, list] = {}
    candidates_by_asset: dict[str, list[_Candidate]] = {}
    for asset in target_assets:
        asset_tokens = [
            token
            for token in (tokens_by_asset.get(asset.asset_id) or [])
            if str(getattr(token, "kind", "") or "") in _ROLE_KIND_SET
        ]
        target_tokens_by_asset[asset.asset_id] = asset_tokens
        role_counter.update(str(token.kind) for token in asset_tokens)

    role_token_summary = [
        ReviewRoleTokenSummary(
            role_kind=kind,
            token_prefix=_ROLE_META[kind][0],
            label=_ROLE_META[kind][1],
            generated_count=role_counter[kind],
        )
        for kind in _ROLE_META
        if role_counter[kind] > 0
    ]
    detected_original_types = [
        ReviewDetectedType(
            type_key=kind,
            label=_ROLE_META[kind][1],
            count=role_counter[kind],
        )
        for kind in _ROLE_META
        if role_counter[kind] > 0
    ]

    risks: list[ReviewEntityCandidate] = []
    warnings: list[ReviewEntityCandidate] = []
    structure_checks: list[ReviewStructureCheck] = []
    asset_previews: list[ReviewAssetPreview] = []
    debug_candidate_evidence: list[ReviewDebugCandidateEvidence] = []
    preview_safe = True

    for asset in target_assets:
        canonical = canonical_map.get(asset.asset_id)
        confirmed_values = {
            str(getattr(token, "value", "") or "").strip()
            for token in target_tokens_by_asset.get(asset.asset_id, [])
        }
        candidates = _find_label_less_candidates(asset, tokenizer, confirmed_values)
        candidates_by_asset[asset.asset_id] = list(candidates)
        risk_candidates = [candidate for candidate in candidates if candidate.severity == "risk"]
        warning_candidates = [candidate for candidate in candidates if candidate.severity == "warning"]
        risks.extend(_to_review_candidates(candidate) for candidate in risk_candidates)
        warnings.extend(_to_review_candidates(candidate) for candidate in warning_candidates)
        debug_candidate_evidence.extend(_to_debug_candidate_evidence(candidate) for candidate in candidates if _needs_debug_evidence(candidate))
        debug_candidate_evidence.extend(_collect_contextual_org_debug_evidence(asset, canonical, tokenizer))

        preview_text = _build_asset_preview_text(asset, canonical, candidates)
        if not _preview_is_safe(preview_text, candidates, tokenizer):
            preview_safe = False

        asset_previews.append(
            ReviewAssetPreview(
                asset_id=asset.asset_id,
                asset_name=asset.name,
                preview_text=preview_text,
                role_token_count=len(target_tokens_by_asset.get(asset.asset_id, [])),
                risk_count=len(risk_candidates),
                warning_count=len(warning_candidates),
            )
        )
        structure_checks.extend(_check_structure_integrity(asset, canonical))

    preview_quality = _evaluate_preview_quality(asset_previews, candidates_by_asset)
    has_structure_risk = any(check.severity == "risk" for check in structure_checks)
    if not preview_safe or risks or has_structure_risk:
        status = "blocked"
        llm_send_allowed = False
    elif warnings:
        status = "review_required"
        llm_send_allowed = True
    else:
        status = "ready"
        llm_send_allowed = True

    return AnonymizationReviewArtifacts(
        review_report=AnonymizationReviewReport(
            applied=True,
            status=status,
            llm_send_allowed=llm_send_allowed,
            masking_level=safe_bundle.masking_level,
            target_asset_count=len(target_assets),
            role_token_summary=role_token_summary,
            detected_original_types=detected_original_types,
            label_less_risks=risks,
            label_less_warnings=warnings,
            structure_checks=structure_checks,
            asset_previews=asset_previews,
            preview_quality_status=preview_quality["status"],
            replacement_ratio=preview_quality["replacement_ratio"],
            candidate_density=preview_quality["candidate_density"],
            hidden_line_ratio=preview_quality["hidden_line_ratio"],
            overredaction_warnings=preview_quality["warnings"],
            low_conf_replacements_blocked=preview_quality["low_conf_replacements_blocked"],
            debug_candidate_evidence=debug_candidate_evidence,
        ),
        llm_safe_sources=_build_llm_safe_sources(
            canonical_sources=canonical_sources,
            candidates_by_asset=candidates_by_asset,
        ),
    )


def build_anonymization_review_report(
    *,
    assets: list[AnonymizationAsset],
    safe_bundle: SafeAnalysisBundle,
    canonical_sources: list[CanonicalAnonymizedSource],
    tokens_by_asset: dict[str, list],
    document_tokenizer: DocumentEntityTokenizer | None = None,
) -> AnonymizationReviewReport | None:
    return build_anonymization_review_artifacts(
        assets=assets,
        safe_bundle=safe_bundle,
        canonical_sources=canonical_sources,
        tokens_by_asset=tokens_by_asset,
        document_tokenizer=document_tokenizer,
    ).review_report


def _build_llm_safe_sources(
    *,
    canonical_sources: list[CanonicalAnonymizedSource],
    candidates_by_asset: dict[str, list[_Candidate]],
) -> list[CanonicalAnonymizedSource]:
    llm_safe_sources: list[CanonicalAnonymizedSource] = []
    for source in canonical_sources:
        llm_safe_sources.append(
            _mask_label_less_candidates_in_source(
                source,
                candidates_by_asset.get(source.asset_id, []),
            )
        )
    return llm_safe_sources


def _mask_label_less_candidates_in_source(
    source: CanonicalAnonymizedSource,
    candidates: list[_Candidate],
) -> CanonicalAnonymizedSource:
    if not candidates:
        return source.model_copy(deep=True)
    masked_content = _apply_candidate_markers_to_text(source.content or "", candidates)
    if masked_content == (source.content or ""):
        return source.model_copy(deep=True)
    return source.model_copy(update={"content": masked_content})


def _find_label_less_candidates(
    asset: AnonymizationAsset,
    tokenizer: DocumentEntityTokenizer,
    confirmed_values: set[str],
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    seen_keys: set[tuple[str, str, str]] = set()
    current_slide = "unknown"
    current_section = "body"
    section_index = 0

    for line_index, raw_line in enumerate((asset.content_text or "").splitlines()):
        stripped = raw_line.strip()
        if not stripped:
            continue

        slide_match = _SLIDE_HEADER_PATTERN.match(stripped)
        if slide_match:
            current_slide = slide_match.group("slide")
            current_section = "body"
            section_index = 0
            continue

        section_match = _SECTION_PATTERN.match(stripped)
        if section_match:
            current_section = section_match.group(1).lower()
            section_index = 0
            continue

        title_match = _TITLE_PATTERN.match(stripped)
        if title_match:
            current_section = "title"
            section_index += 1
            title_value = tokenizer._normalize_value(title_match.group("value"))
            if title_value and title_value not in confirmed_values:
                for kind, value in tokenizer._classify_title(title_value, existing_kinds=set()):
                    _add_candidate(
                        candidates=candidates,
                        seen_keys=seen_keys,
                        asset=asset,
                        current_slide=current_slide,
                        current_section=current_section,
                        section_index=section_index,
                        kind=kind,
                        raw_value=value,
                        source_line=stripped,
                        line_index=line_index,
                        reason="label-less title phrase requires manual review",
                        tokenizer=tokenizer,
                    )
            continue

        if tokenizer.has_supported_entity_label(stripped):
            continue

        section_index += 1
        for kind, value, reason in _guess_label_less_candidates(tokenizer, stripped, current_section=current_section):
            normalized = tokenizer._normalize_value(value)
            if not normalized or normalized in confirmed_values:
                continue
            _add_candidate(
                candidates=candidates,
                seen_keys=seen_keys,
                asset=asset,
                current_slide=current_slide,
                current_section=current_section,
                section_index=section_index,
                kind=kind,
                raw_value=normalized,
                source_line=stripped,
                line_index=line_index,
                reason=reason,
                tokenizer=tokenizer,
            )

    return candidates


def _guess_label_less_candidates(
    tokenizer: DocumentEntityTokenizer,
    line: str,
    *,
    current_section: str = "body",
) -> list[tuple[str, str, str]]:
    guesses: list[tuple[str, str, str]] = []
    normalized_line = tokenizer._normalize_bullet_content(line)
    compact_line = tokenizer._normalize_value(normalized_line)
    lowered = compact_line.lower()
    person_candidates = set(tokenizer.iter_label_less_person_candidates(compact_line, section=current_section))
    low_conf_candidates = set(
        tokenizer.iter_low_conf_term_candidates(
            compact_line,
            section=current_section,
            exclude=person_candidates,
        )
    )
    candidate_exclusions = person_candidates | low_conf_candidates

    for match in tokenizer._EMAIL_PATTERN.finditer(compact_line):
        guesses.append(("email", tokenizer._normalize_value(match.group("value")), "label-less email in content"))
    for match in tokenizer._PHONE_PATTERN.finditer(compact_line):
        guesses.append(("phone", tokenizer._normalize_phone(match.group("value")), "label-less phone number in content"))
    for match in tokenizer._ADDRESS_INLINE_PATTERN.finditer(compact_line):
        guesses.append(("address", tokenizer._normalize_value(match.group("value")), "label-less address in content"))
    for match in tokenizer._KOREAN_COMPANY_PATTERN.finditer(compact_line):
        value = tokenizer._normalize_value(match.group("value"))
        if tokenizer._is_valid_candidate("organization_name", value) and not tokenizer.is_generic_document_phrase(
            value,
            ignore_tokens=candidate_exclusions,
        ):
            guesses.append(("organization_name", value, "label-less organization-like phrase in content"))
    for match in tokenizer._ENGLISH_ORG_PATTERN.finditer(compact_line):
        value = tokenizer._normalize_value(match.group("value"))
        if tokenizer._is_valid_candidate("organization_name", value) and not tokenizer.is_generic_document_phrase(
            value,
            ignore_tokens=candidate_exclusions,
        ):
            guesses.append(("organization_name", value, "label-less organization-like phrase in content"))

    dept_match = re.search(
        r"([가-힣A-Za-z0-9&().\-/ ]{2,}?(?:본부|센터|부서|팀|실|처|국|랩|Lab|Team|Division|Office|부))\b",
        compact_line,
    )
    if dept_match:
        value = tokenizer._normalize_value(dept_match.group(1))
        if tokenizer._is_valid_candidate("department_name", value) and tokenizer._looks_like_department(value):
            guesses.append(("department_name", value, "label-less department-like phrase in content"))

    for person_value in person_candidates:
        guesses.append(("person_name", person_value, "label-less person-like token in content"))
    for candidate_value in low_conf_candidates:
        guesses.append(("low_conf_term", candidate_value, "ambiguous name-like token requires manual review"))

    business_match = re.search(r"([가-힣A-Za-z0-9&().\-/ ]{2,}(?:사업|과제|프로그램))\b", compact_line)
    if business_match:
        value = tokenizer._normalize_value(business_match.group(1))
        if tokenizer._is_valid_candidate("business_name", value) and not tokenizer.is_generic_document_phrase(
            value,
            ignore_tokens=candidate_exclusions,
        ):
            guesses.append(("business_name", value, "label-less business-like phrase in content"))

    project_match = re.search(
        r"([가-힣A-Za-z0-9&().\-/ ]{2,}(?:프로젝트|구축|고도화|개편|전환|도입|Modernization|Project))\b",
        compact_line,
        re.IGNORECASE,
    )
    if project_match:
        value = tokenizer._normalize_value(project_match.group(1))
        if tokenizer._is_valid_candidate("project_name", value) and not tokenizer.is_generic_document_phrase(
            value,
            ignore_tokens=candidate_exclusions,
        ):
            guesses.append(("project_name", value, "label-less project-like phrase in content"))

    contract_match = re.search(r"([가-힣A-Za-z0-9&().\-/ ]{2,}(?:계약|용역|contract))\b", compact_line, re.IGNORECASE)
    if contract_match:
        value = tokenizer._normalize_value(contract_match.group(1))
        if tokenizer._is_valid_candidate("contract_name", value) and not tokenizer.is_generic_document_phrase(
            value,
            ignore_tokens=candidate_exclusions,
        ):
            guesses.append(("contract_name", value, "label-less contract-like phrase in content"))

    if compact_line and not any(kind == "business_name" for kind, _, _ in guesses):
        if (
            any(keyword in lowered for keyword in ("initiative", "program"))
            and tokenizer._is_valid_candidate("business_name", compact_line)
            and not tokenizer.is_generic_document_phrase(compact_line, ignore_tokens=candidate_exclusions)
        ):
            guesses.append(("business_name", compact_line, "label-less business-like phrase in content"))

    return guesses


def _add_candidate(
    *,
    candidates: list[_Candidate],
    seen_keys: set[tuple[str, str, str]],
    asset: AnonymizationAsset,
    current_slide: str,
    current_section: str,
    section_index: int,
    kind: str,
    raw_value: str,
    source_line: str,
    line_index: int,
    reason: str,
    tokenizer: DocumentEntityTokenizer,
) -> None:
    if kind not in _CANDIDATE_KIND_SET:
        return
    label = (_ROLE_META.get(kind) or _NON_ROLE_CANDIDATE_META.get(kind) or (kind.upper(), kind))[1]
    severity = "risk" if kind in _RISK_KIND_SET else "warning"
    locator = f"slide {current_slide} / {current_section} / line {section_index}"
    dedupe_key = (kind, raw_value, locator)
    if dedupe_key in seen_keys:
        return
    seen_keys.add(dedupe_key)
    candidates.append(
        _Candidate(
            severity=severity,
            entity_type_guess=kind,
            label=label,
            asset_id=asset.asset_id,
            asset_name=asset.name,
            slide=current_slide,
            line_index=line_index,
            locator=locator,
            reason=reason,
            raw_value=raw_value,
            source_line=source_line,
            replace_in_text=kind != "low_conf_term"
            and tokenizer.should_replace_label_less_candidate(kind, raw_value),
        )
    )


def _to_review_candidates(candidate: _Candidate) -> ReviewEntityCandidate:
    return ReviewEntityCandidate(
        severity=candidate.severity,  # type: ignore[arg-type]
        entity_type_guess=candidate.entity_type_guess,
        label=candidate.label,
        asset_id=candidate.asset_id,
        asset_name=candidate.asset_name,
        locator=candidate.locator,
        reason=candidate.reason,
        masked_preview=_mask_candidate_line_preview(candidate),
    )


def _needs_debug_evidence(candidate: _Candidate) -> bool:
    return candidate.entity_type_guess in {"organization_name", "project_name", "business_name", "contract_name"} and not candidate.replace_in_text


def _to_debug_candidate_evidence(candidate: _Candidate) -> ReviewDebugCandidateEvidence:
    return ReviewDebugCandidateEvidence(
        severity=candidate.severity,  # type: ignore[arg-type]
        entity_type_guess=candidate.entity_type_guess,
        asset_id=candidate.asset_id,
        asset_name=candidate.asset_name,
        locator=candidate.locator,
        reason=candidate.reason,
        raw_value=candidate.raw_value,
        source_line=candidate.source_line,
    )


def _collect_contextual_org_debug_evidence(
    asset: AnonymizationAsset,
    canonical: CanonicalAnonymizedSource | None,
    tokenizer: DocumentEntityTokenizer,
) -> list[ReviewDebugCandidateEvidence]:
    evidences: list[ReviewDebugCandidateEvidence] = []
    canonical_lines = (canonical.content if canonical is not None else "").splitlines()
    current_slide = "unknown"
    current_section = "body"
    section_index = 0
    seen: set[tuple[str, str, str]] = set()

    for line_index, raw_line in enumerate((asset.content_text or "").splitlines()):
        stripped = raw_line.strip()
        if not stripped:
            continue

        slide_match = _SLIDE_HEADER_PATTERN.match(stripped)
        if slide_match:
            current_slide = slide_match.group("slide")
            current_section = "body"
            section_index = 0
            continue

        section_match = _SECTION_PATTERN.match(stripped)
        if section_match:
            current_section = section_match.group(1).lower()
            section_index = 0
            continue

        if tokenizer.has_supported_entity_label(stripped):
            continue

        section_index += 1
        normalized_line = tokenizer._normalize_bullet_content(stripped)
        match = _CONTEXTUAL_ORG_DEBUG_PATTERN.match(normalized_line)
        if not match:
            continue
        raw_value = tokenizer._trim_korean_postposition(tokenizer._normalize_value(match.group("value")))
        canonical_line = canonical_lines[line_index].strip() if line_index < len(canonical_lines) else ""
        if not raw_value or raw_value in canonical_line or not _MASKED_ORG_TOKEN_PATTERN.search(canonical_line):
            continue
        locator = f"slide {current_slide} / {current_section} / line {section_index}"
        dedupe_key = (raw_value, locator, stripped)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        evidences.append(
            ReviewDebugCandidateEvidence(
                severity="risk",
                entity_type_guess="organization_name",
                asset_id=asset.asset_id,
                asset_name=asset.name,
                locator=locator,
                reason="contextual organization alias masked before preview; paired with a generic heading phrase",
                raw_value=raw_value,
                source_line=stripped,
            )
        )
    return evidences


def _mask_candidate_line_preview(candidate: _Candidate) -> str:
    marker = _candidate_marker(candidate.severity, candidate.entity_type_guess)
    masked_line = candidate.source_line.replace(candidate.raw_value, marker)
    return build_preview_masked_text(masked_line)


def _build_asset_preview_text(
    asset: AnonymizationAsset,
    canonical: CanonicalAnonymizedSource | None,
    candidates: list[_Candidate],
) -> str:
    preview_source = canonical.content if canonical is not None else (asset.content_text or "")
    preview_source = _apply_candidate_markers_to_text(preview_source, candidates)
    preview_lines = _select_preview_lines(preview_source, candidates)
    if not preview_lines:
        preview_lines = [_mask_candidate_line_preview(candidate) for candidate in candidates[:3]]
    return "\n".join(build_preview_masked_text(line) for line in preview_lines)


def _apply_candidate_markers_to_text(text: str, candidates: list[_Candidate]) -> str:
    if not text or not candidates:
        return text
    lines = text.splitlines()
    candidates_by_line: dict[int, list[_Candidate]] = {}
    for candidate in candidates:
        if not candidate.replace_in_text:
            continue
        candidates_by_line.setdefault(candidate.line_index, []).append(candidate)
    for line_index, line_candidates in candidates_by_line.items():
        if line_index >= len(lines):
            continue
        updated_line = lines[line_index]
        for candidate in sorted(line_candidates, key=lambda item: len(item.raw_value), reverse=True):
            if candidate.raw_value and candidate.raw_value in updated_line:
                updated_line = updated_line.replace(
                    candidate.raw_value,
                    _candidate_marker(candidate.severity, candidate.entity_type_guess),
                )
        lines[line_index] = updated_line
    return "\n".join(lines)


def _select_preview_lines(text: str, candidates: list[_Candidate]) -> list[str]:
    hidden_line_indexes = {candidate.line_index for candidate in candidates if not candidate.replace_in_text}
    selected_lines: list[str] = []
    for line_index, raw_line in enumerate(text.splitlines()):
        stripped = raw_line.strip()
        if not stripped:
            continue
        if line_index in hidden_line_indexes:
            continue
        lowered = stripped.lower()
        if lowered.startswith(("presentation_file:", "slide_count:", "layout:", "texts:", "tables:", "charts:", "notes:", "visual_elements:")):
            continue
        selected_lines.append(stripped)
        if len(selected_lines) >= 12:
            break
    return selected_lines[:12]


def _preview_is_safe(
    preview_text: str,
    candidates: list[_Candidate],
    tokenizer: DocumentEntityTokenizer,
) -> bool:
    if not preview_text:
        return False
    for candidate in candidates:
        if candidate.raw_value and candidate.raw_value in preview_text:
            return False
    if tokenizer._EMAIL_PATTERN.search(preview_text):
        return False
    if tokenizer._PHONE_PATTERN.search(preview_text):
        return False
    return True


def _evaluate_preview_quality(
    asset_previews: list[ReviewAssetPreview],
    candidates_by_asset: dict[str, list[_Candidate]],
) -> dict[str, object]:
    preview_lines: list[str] = []
    total_replaceable_candidates = 0
    total_candidates = 0
    total_hidden_lines = 0
    low_conf_replacements_blocked = 0
    for preview in asset_previews:
        preview_lines.extend([line.strip() for line in preview.preview_text.splitlines() if line.strip()])
        hidden_line_indexes = set()
        for candidate in candidates_by_asset.get(preview.asset_id, []):
            total_candidates += 1
            if candidate.entity_type_guess == "low_conf_term" and not candidate.replace_in_text:
                low_conf_replacements_blocked += 1
            if candidate.replace_in_text:
                total_replaceable_candidates += 1
            else:
                hidden_line_indexes.add(candidate.line_index)
        total_hidden_lines += len(hidden_line_indexes)

    replacement_ratio = round(total_replaceable_candidates / max(len(preview_lines), 1), 4)
    candidate_density = round(total_candidates / max(len(preview_lines) + total_hidden_lines, 1), 4)
    hidden_line_ratio = round(total_hidden_lines / max(len(preview_lines) + total_hidden_lines, 1), 4)
    bullet_lines = [line for line in preview_lines if line.startswith("-")]
    tagged_bullet_count = sum(1 for line in bullet_lines[:8] if re.match(r"^-\s*\[[A-Z_]+\]", line))
    warnings: list[str] = []

    if replacement_ratio > 0.25:
        warnings.append(f"replacement_ratio_exceeded:{replacement_ratio:.4f}")
    if tagged_bullet_count >= 4:
        warnings.append(f"tag_prefixed_bullets_high:{tagged_bullet_count}")
    if candidate_density > 0.75:
        warnings.append(f"candidate_density_high:{candidate_density:.4f}")
    if hidden_line_ratio > 0.30:
        warnings.append(f"hidden_line_ratio_high:{hidden_line_ratio:.4f}")

    return {
        "status": "warning" if warnings else "pass",
        "replacement_ratio": replacement_ratio,
        "candidate_density": candidate_density,
        "hidden_line_ratio": hidden_line_ratio,
        "warnings": warnings,
        "low_conf_replacements_blocked": low_conf_replacements_blocked,
    }


def _check_structure_integrity(
    asset: AnonymizationAsset,
    canonical: CanonicalAnonymizedSource | None,
) -> list[ReviewStructureCheck]:
    text = canonical.content if canonical is not None else (asset.content_text or "")
    title_lines: list[str] = []
    content_lines: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.lower() in {"[sml v1]", "texts:", "tables:", "charts:", "notes:", "visual_elements:"}:
            continue
        if stripped.lower().startswith(("presentation_file:", "slide_count:", "layout:", "[slide ")):
            continue
        if _TITLE_PATTERN.match(stripped):
            title_lines.append(stripped)
            continue
        if stripped.startswith("-"):
            content_lines.append(stripped)

    checks: list[ReviewStructureCheck] = []
    if title_lines and all(_is_token_only(line) for line in title_lines):
        checks.append(
            ReviewStructureCheck(
                severity="warning",
                code="title_context_thin",
                message="title lines are fully tokenized and may need human review for lost context",
                asset_id=asset.asset_id,
                asset_name=asset.name,
            )
        )
    if len(content_lines) >= 3:
        token_only_count = sum(1 for line in content_lines if _is_token_only(line))
        if token_only_count / len(content_lines) >= 0.6:
            checks.append(
                ReviewStructureCheck(
                    severity="warning",
                    code="content_token_density_high",
                    message="content lines are heavily tokenized and may have reduced decision context",
                    asset_id=asset.asset_id,
                    asset_name=asset.name,
                )
            )
    if not checks:
        checks.append(
            ReviewStructureCheck(
                severity="ok",
                code="structure_preserved",
                message="tokenization preserved the visible SML structure",
                asset_id=asset.asset_id,
                asset_name=asset.name,
            )
        )
    return checks


def _is_token_only(value: str) -> bool:
    return bool(_TOKEN_ONLY_PATTERN.match((value or "").strip()))


def _candidate_marker(severity: str, kind: str) -> str:
    if kind == "low_conf_term":
        return "[LOW_CONF_TERM_CANDIDATE]"
    prefix = _ROLE_META.get(kind, (kind.upper(), kind))[0]
    return f"[{severity.upper()}_{prefix}_CANDIDATE]"
