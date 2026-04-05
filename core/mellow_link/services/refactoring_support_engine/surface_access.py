from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Literal


SurfaceMode = Literal["internal", "external"]
AccessProfile = Literal["internal_full", "internal_limited", "external_basic", "external_advanced"]
VisibilityState = Literal["visible", "absent", "hidden_by_policy"]


@dataclass(frozen=True)
class AccessProfileCapabilities:
    can_view_review_diff: bool
    can_view_review_diff_preview: bool
    can_view_code_diff: bool
    can_view_blocked_decisions: bool
    can_view_block_reasons: bool
    can_view_governance_trace: bool
    can_view_detector_locator: bool
    can_view_fingerprint_alias: bool
    can_export_review_artifacts: bool


@dataclass(frozen=True)
class AccessProfilePolicy:
    access_profile: AccessProfile
    surface_variant: Literal["internal_review", "external_presentation"]
    capabilities: AccessProfileCapabilities


@dataclass(frozen=True)
class FilteredReviewDiffArtifact:
    filtered: dict[str, Any] | None
    field_visibility: dict[str, VisibilityState]
    review_diff_surface_policy: Literal["visible", "hidden_by_policy", "absent"]


_PROFILE_BY_SURFACE_MODE: dict[SurfaceMode, AccessProfile] = {
    "internal": "internal_full",
    "external": "external_basic",
}

_ACCESS_POLICIES: dict[AccessProfile, AccessProfilePolicy] = {
    "internal_full": AccessProfilePolicy(
        access_profile="internal_full",
        surface_variant="internal_review",
        capabilities=AccessProfileCapabilities(
            can_view_review_diff=True,
            can_view_review_diff_preview=True,
            can_view_code_diff=True,
            can_view_blocked_decisions=True,
            can_view_block_reasons=True,
            can_view_governance_trace=True,
            can_view_detector_locator=True,
            can_view_fingerprint_alias=True,
            can_export_review_artifacts=True,
        ),
    ),
    "internal_limited": AccessProfilePolicy(
        access_profile="internal_limited",
        surface_variant="internal_review",
        capabilities=AccessProfileCapabilities(
            can_view_review_diff=True,
            can_view_review_diff_preview=True,
            can_view_code_diff=False,
            can_view_blocked_decisions=True,
            can_view_block_reasons=True,
            can_view_governance_trace=True,
            can_view_detector_locator=False,
            can_view_fingerprint_alias=False,
            can_export_review_artifacts=False,
        ),
    ),
    "external_basic": AccessProfilePolicy(
        access_profile="external_basic",
        surface_variant="external_presentation",
        capabilities=AccessProfileCapabilities(
            can_view_review_diff=False,
            can_view_review_diff_preview=False,
            can_view_code_diff=False,
            can_view_blocked_decisions=False,
            can_view_block_reasons=False,
            can_view_governance_trace=False,
            can_view_detector_locator=False,
            can_view_fingerprint_alias=False,
            can_export_review_artifacts=False,
        ),
    ),
    "external_advanced": AccessProfilePolicy(
        access_profile="external_advanced",
        surface_variant="external_presentation",
        capabilities=AccessProfileCapabilities(
            can_view_review_diff=False,
            can_view_review_diff_preview=False,
            can_view_code_diff=False,
            can_view_blocked_decisions=False,
            can_view_block_reasons=False,
            can_view_governance_trace=False,
            can_view_detector_locator=False,
            can_view_fingerprint_alias=False,
            can_export_review_artifacts=False,
        ),
    ),
}


def normalize_surface_mode(surface_mode: str | None) -> SurfaceMode:
    return "external" if surface_mode == "external" else "internal"


def resolve_access_profile(surface_mode: str | None) -> AccessProfile:
    return _PROFILE_BY_SURFACE_MODE[normalize_surface_mode(surface_mode)]


def policy_for_surface_mode(surface_mode: str | None) -> AccessProfilePolicy:
    return policy_for_access_profile(resolve_access_profile(surface_mode))


def policy_for_access_profile(access_profile: str | None) -> AccessProfilePolicy:
    normalized = str(access_profile or "").strip() or "external_basic"
    return _ACCESS_POLICIES.get(normalized, _ACCESS_POLICIES["external_basic"])


def access_profile_capabilities(access_profile: str | None) -> AccessProfileCapabilities:
    return policy_for_access_profile(access_profile).capabilities


def capabilities_dict(access_profile: str | None) -> dict[str, bool]:
    return asdict(access_profile_capabilities(access_profile))


def can_view_review_diff(access_profile: str | None) -> bool:
    return access_profile_capabilities(access_profile).can_view_review_diff


def can_view_review_diff_preview(access_profile: str | None) -> bool:
    return access_profile_capabilities(access_profile).can_view_review_diff_preview


def can_view_code_diff(access_profile: str | None) -> bool:
    return access_profile_capabilities(access_profile).can_view_code_diff


def can_view_blocked_decisions(access_profile: str | None) -> bool:
    return access_profile_capabilities(access_profile).can_view_blocked_decisions


def can_view_block_reasons(access_profile: str | None) -> bool:
    return access_profile_capabilities(access_profile).can_view_block_reasons


def can_view_governance_trace(access_profile: str | None) -> bool:
    return access_profile_capabilities(access_profile).can_view_governance_trace


def can_view_detector_locator(access_profile: str | None) -> bool:
    return access_profile_capabilities(access_profile).can_view_detector_locator


def can_view_fingerprint_alias(access_profile: str | None) -> bool:
    return access_profile_capabilities(access_profile).can_view_fingerprint_alias


def can_export_review_artifacts(access_profile: str | None) -> bool:
    return access_profile_capabilities(access_profile).can_export_review_artifacts


def filter_review_diff_for_access(
    review_diff: dict[str, Any] | None,
    *,
    access_profile: str | None,
) -> FilteredReviewDiffArtifact:
    capabilities = access_profile_capabilities(access_profile)
    field_visibility: dict[str, VisibilityState] = {
        "review_diff": "absent",
        "code_diff": "absent",
        "blocked_decisions": "absent",
        "block_reasons": "absent",
        "synthetic_signal_detected": "absent",
        "detector_locator": "absent",
        "fingerprint_alias": "absent",
    }
    if not isinstance(review_diff, dict) or not review_diff:
        return FilteredReviewDiffArtifact(
            filtered=None,
            field_visibility=field_visibility,
            review_diff_surface_policy="absent",
        )

    if not capabilities.can_view_review_diff:
        field_visibility = {
            key: "hidden_by_policy" if key == "review_diff" else "absent"
            for key in field_visibility
        }
        return FilteredReviewDiffArtifact(
            filtered=None,
            field_visibility=field_visibility,
            review_diff_surface_policy="hidden_by_policy",
        )

    filtered = deepcopy(review_diff)
    field_visibility["review_diff"] = "visible"

    decision_diff = filtered.get("decision_diff")
    if isinstance(decision_diff, dict):
        if decision_diff.get("blocked_decisions"):
            if capabilities.can_view_blocked_decisions:
                field_visibility["blocked_decisions"] = "visible"
            else:
                field_visibility["blocked_decisions"] = "hidden_by_policy"
                decision_diff["blocked_decisions"] = []
        else:
            field_visibility["blocked_decisions"] = "absent"

        if decision_diff.get("block_reasons"):
            if capabilities.can_view_block_reasons:
                field_visibility["block_reasons"] = "visible"
            else:
                field_visibility["block_reasons"] = "hidden_by_policy"
                decision_diff["block_reasons"] = []
        else:
            field_visibility["block_reasons"] = "absent"

        governance_keys = (
            "synthetic_signal_detected",
            "decision_engine_guard_applied",
            "result_packager_guard_applied",
        )
        governance_present = any(key in decision_diff for key in governance_keys)
        if governance_present:
            if capabilities.can_view_governance_trace:
                field_visibility["synthetic_signal_detected"] = "visible"
            else:
                field_visibility["synthetic_signal_detected"] = "hidden_by_policy"
                decision_diff["synthetic_signal_detected"] = False
                decision_diff["decision_engine_guard_applied"] = False
                decision_diff["result_packager_guard_applied"] = False
        else:
            field_visibility["synthetic_signal_detected"] = "absent"

    evidence_diff = filtered.get("evidence_diff")
    if isinstance(evidence_diff, dict):
        field_visibility["detector_locator"] = "absent"
        field_visibility["fingerprint_alias"] = "absent"
        fingerprint_collections = []
        for collection_name in ("repeated_fingerprints", "detector_evidence_map", "scatter_traces", "leak_traces", "coupling_traces"):
            collection = evidence_diff.get(collection_name)
            if not isinstance(collection, list):
                continue
            for entry in collection:
                if not isinstance(entry, dict):
                    continue
                fingerprint_collections.append(entry)
                if "locations" in entry:
                    if entry.get("locations"):
                        if capabilities.can_view_detector_locator:
                            field_visibility["detector_locator"] = "visible"
                        else:
                            field_visibility["detector_locator"] = "hidden_by_policy"
                            entry["locations"] = []
                    elif field_visibility["detector_locator"] == "absent":
                        field_visibility["detector_locator"] = "absent"
                if "fingerprint_alias" in entry or "fingerprint_aliases" in entry:
                    fingerprint_values = entry.get("fingerprint_aliases") if "fingerprint_aliases" in entry else [entry.get("fingerprint_alias")]
                    has_value = any(str(value or "").strip() for value in (fingerprint_values or []))
                    if has_value:
                        if capabilities.can_view_fingerprint_alias:
                            field_visibility["fingerprint_alias"] = "visible"
                        else:
                            field_visibility["fingerprint_alias"] = "hidden_by_policy"
                            if "fingerprint_aliases" in entry:
                                entry["fingerprint_aliases"] = []
                            if "fingerprint_alias" in entry:
                                entry["fingerprint_alias"] = ""
                    elif field_visibility["fingerprint_alias"] == "absent":
                        field_visibility["fingerprint_alias"] = "absent"

    code_diff = filtered.get("code_diff")
    if isinstance(code_diff, dict):
        snippets = code_diff.get("snippets")
        has_code_diff = bool(code_diff.get("available")) and isinstance(snippets, list) and bool(snippets)
        if has_code_diff:
            if capabilities.can_view_code_diff:
                field_visibility["code_diff"] = "visible"
            else:
                field_visibility["code_diff"] = "hidden_by_policy"
                code_diff["available"] = False
                code_diff["snippets"] = []
        else:
            field_visibility["code_diff"] = "absent"

    if "markdown" in filtered:
        needs_markdown_hide = any(
            field_visibility[key] == "hidden_by_policy"
            for key in (
                "code_diff",
                "blocked_decisions",
                "block_reasons",
                "synthetic_signal_detected",
                "detector_locator",
                "fingerprint_alias",
            )
        )
        if needs_markdown_hide:
            filtered["markdown"] = ""

    if _review_diff_is_empty(filtered):
        return FilteredReviewDiffArtifact(
            filtered=None,
            field_visibility=field_visibility,
            review_diff_surface_policy="hidden_by_policy" if any(value == "hidden_by_policy" for value in field_visibility.values()) else "absent",
        )

    return FilteredReviewDiffArtifact(
        filtered=filtered,
        field_visibility=field_visibility,
        review_diff_surface_policy="visible",
    )


def filter_decision_governance_for_access(
    decision_governance: dict[str, Any] | None,
    *,
    access_profile: str | None,
) -> tuple[dict[str, Any] | None, VisibilityState]:
    if not isinstance(decision_governance, dict) or not decision_governance:
        return None, "absent"
    if not can_view_governance_trace(access_profile):
        return None, "hidden_by_policy"
    return deepcopy(decision_governance), "visible"


def review_diff_preview_surface_state(
    review_diff: dict[str, Any] | None,
    *,
    access_profile: str | None,
) -> Literal["preview_only", "hidden_by_policy", "unavailable"]:
    if not can_view_review_diff_preview(access_profile):
        return "hidden_by_policy"
    if not isinstance(review_diff, dict) or not review_diff:
        return "unavailable"
    return "preview_only"


def _review_diff_is_empty(review_diff: dict[str, Any]) -> bool:
    decision_diff = review_diff.get("decision_diff")
    evidence_diff = review_diff.get("evidence_diff")
    structural_diff = review_diff.get("structural_diff")
    code_diff = review_diff.get("code_diff")
    markdown = str(review_diff.get("markdown") or "").strip()
    has_decision = isinstance(decision_diff, dict) and any(
        bool(decision_diff.get(key))
        for key in (
            "allowed_decisions",
            "blocked_decisions",
            "block_reasons",
            "synthetic_signal_detected",
            "decision_engine_guard_applied",
            "result_packager_guard_applied",
        )
    )
    has_evidence = isinstance(evidence_diff, dict) and any(bool(evidence_diff.get(key)) for key in evidence_diff)
    has_structural = isinstance(structural_diff, dict) and any(bool(structural_diff.get(key)) for key in structural_diff)
    has_code_diff = isinstance(code_diff, dict) and bool(code_diff.get("available")) and bool(code_diff.get("snippets"))
    return not any((has_decision, has_evidence, has_structural, has_code_diff, markdown))
