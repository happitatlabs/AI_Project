from __future__ import annotations

from mellow_link.services.refactoring_support_engine.surface_access import (
    can_export_review_artifacts,
    can_view_block_reasons,
    can_view_code_diff,
    can_view_detector_locator,
    can_view_fingerprint_alias,
    can_view_governance_trace,
    can_view_review_diff,
    filter_review_diff_for_access,
    policy_for_surface_mode,
    resolve_access_profile,
)


def _sample_review_diff() -> dict:
    return {
        "structural_diff": {
            "component_structure": [{"component": "Component01", "layer": "backend", "responsibility_families": ["policy"]}],
            "dependency_flows": ["Component01 [backend] -> Component02 [data_access] (calls)"],
            "layer_boundary_notes": [{"detector_id": "boundary_mismatch", "components": ["Component01"], "note": "boundary_mismatch on Component01"}],
            "data_flow_notes": [{"slice": "Slice01", "components": ["Component01"], "data_stores": ["DataStore01"], "entry_point_count": 1}],
        },
        "evidence_diff": {
            "repeated_fingerprints": [
                {
                    "fingerprint_alias": "QueryFragment01",
                    "occurrence_count": 3,
                    "locations": ["claim_policy.py:line:12", "claim_service.py:line:31"],
                }
            ],
            "detector_evidence_map": [
                {
                    "issue_id": "ISS-01",
                    "detector_id": "query_filter_leak",
                    "fingerprint_aliases": ["QueryFragment01"],
                    "locations": ["claim_policy.py:line:12"],
                }
            ],
            "scatter_traces": [],
            "leak_traces": [
                {
                    "issue_id": "ISS-01",
                    "detector_id": "query_filter_leak",
                    "fingerprint_aliases": ["QueryFragment01"],
                    "locations": ["claim_policy.py:line:12"],
                }
            ],
            "coupling_traces": [],
        },
        "decision_diff": {
            "allowed_decisions": [{"decision_id": "DEC-01", "decision_type": "refactor", "priority_score": 8, "issue_count": 1, "evidence_count": 2}],
            "blocked_decisions": [{"decision_type": "migration_consideration", "downgraded_to": "refactor", "block_reason": "goal wording only (contamination)"}],
            "block_reasons": ["goal wording only (contamination)"],
            "synthetic_signal_detected": True,
            "decision_engine_guard_applied": True,
            "result_packager_guard_applied": False,
        },
        "code_diff": {
            "available": True,
            "snippets": [
                {
                    "type": "before_after",
                    "file": "claim_policy.py",
                    "observed": "if claim.status == 'REQUESTED': raise PermissionError()",
                    "expected_pattern": "rule_result = RuleSet01.evaluate(context)",
                }
            ],
        },
        "markdown": "## Decision Result\n",
    }


def test_surface_access_profiles_use_view_based_capability_names():
    assert resolve_access_profile("internal") == "internal_full"
    assert resolve_access_profile("external") == "external_basic"

    internal_policy = policy_for_surface_mode("internal")
    external_policy = policy_for_surface_mode("external")

    assert internal_policy.access_profile == "internal_full"
    assert internal_policy.capabilities.can_view_review_diff is True
    assert internal_policy.capabilities.can_view_code_diff is True
    assert internal_policy.capabilities.can_view_block_reasons is True
    assert internal_policy.capabilities.can_view_governance_trace is True
    assert internal_policy.capabilities.can_view_detector_locator is True
    assert internal_policy.capabilities.can_export_review_artifacts is True

    assert external_policy.access_profile == "external_basic"
    assert external_policy.capabilities.can_view_review_diff is False
    assert external_policy.capabilities.can_view_code_diff is False
    assert external_policy.capabilities.can_view_block_reasons is False
    assert external_policy.capabilities.can_view_governance_trace is False
    assert external_policy.capabilities.can_view_detector_locator is False
    assert external_policy.capabilities.can_export_review_artifacts is False


def test_surface_access_filters_review_diff_as_hidden_by_policy_for_external_basic():
    filtered = filter_review_diff_for_access(_sample_review_diff(), access_profile="external_basic")

    assert filtered.filtered is None
    assert filtered.review_diff_surface_policy == "hidden_by_policy"
    assert filtered.field_visibility["review_diff"] == "hidden_by_policy"
    assert filtered.field_visibility["code_diff"] == "absent"
    assert filtered.field_visibility["blocked_decisions"] == "absent"


def test_surface_access_supports_internal_limited_profile_with_field_level_gating():
    filtered = filter_review_diff_for_access(_sample_review_diff(), access_profile="internal_limited")

    assert filtered.filtered is not None
    assert filtered.review_diff_surface_policy == "visible"
    assert filtered.field_visibility["review_diff"] == "visible"
    assert filtered.field_visibility["code_diff"] == "hidden_by_policy"
    assert filtered.field_visibility["detector_locator"] == "hidden_by_policy"
    assert filtered.field_visibility["fingerprint_alias"] == "hidden_by_policy"
    assert filtered.field_visibility["blocked_decisions"] == "visible"
    assert filtered.field_visibility["block_reasons"] == "visible"
    assert filtered.field_visibility["synthetic_signal_detected"] == "visible"
    assert filtered.filtered["code_diff"]["available"] is False
    assert filtered.filtered["code_diff"]["snippets"] == []
    assert filtered.filtered["decision_diff"]["blocked_decisions"]
    repeated = filtered.filtered["evidence_diff"]["repeated_fingerprints"][0]
    detector = filtered.filtered["evidence_diff"]["detector_evidence_map"][0]
    assert repeated["fingerprint_alias"] == ""
    assert repeated["locations"] == []
    assert detector["fingerprint_aliases"] == []
    assert detector["locations"] == []
    assert filtered.filtered["markdown"] == ""


def test_surface_access_policy_helpers_match_internal_limited_expectations():
    assert can_view_review_diff("internal_limited") is True
    assert can_view_code_diff("internal_limited") is False
    assert can_view_block_reasons("internal_limited") is True
    assert can_view_governance_trace("internal_limited") is True
    assert can_view_detector_locator("internal_limited") is False
    assert can_view_fingerprint_alias("internal_limited") is False
    assert can_export_review_artifacts("internal_limited") is False
