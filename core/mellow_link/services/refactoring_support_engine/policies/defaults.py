from __future__ import annotations

from .detector_policy import DetectorPolicyEntry
from .scoring_policy import EnginePolicyBundle, ScoringPolicy


FALLBACK_DETECTOR_POLICY = DetectorPolicyEntry(
    detector_id="<unknown>",
    category="unknown",
    enabled=True,
    base_severity=3,
    default_effort=3,
    detector_weight=0,
)


DEFAULT_DETECTOR_POLICIES: dict[str, DetectorPolicyEntry] = {
    "mixed_responsibility": DetectorPolicyEntry(
        detector_id="mixed_responsibility",
        category="structure",
        enabled=True,
        base_severity=3,
        default_effort=3,
        detector_weight=1,
    ),
    "ui_data_access_coupling": DetectorPolicyEntry(
        detector_id="ui_data_access_coupling",
        category="boundary",
        enabled=True,
        base_severity=4,
        default_effort=3,
        detector_weight=2,
    ),
    "rule_scatter": DetectorPolicyEntry(
        detector_id="rule_scatter",
        category="rule_distribution",
        enabled=True,
        base_severity=3,
        default_effort=4,
        detector_weight=1,
    ),
    "duplicate_logic_candidate": DetectorPolicyEntry(
        detector_id="duplicate_logic_candidate",
        category="duplication",
        enabled=True,
        base_severity=2,
        default_effort=2,
        detector_weight=-1,
        allow_cross_layer_bonus=False,
        allow_write_path_bonus=False,
    ),
    "boundary_mismatch": DetectorPolicyEntry(
        detector_id="boundary_mismatch",
        category="boundary",
        enabled=True,
        base_severity=4,
        default_effort=5,
        detector_weight=2,
    ),
    "state_transition_leak": DetectorPolicyEntry(
        detector_id="state_transition_leak",
        category="workflow",
        enabled=True,
        base_severity=3,
        default_effort=3,
        detector_weight=1,
    ),
    "validation_guard_leak": DetectorPolicyEntry(
        detector_id="validation_guard_leak",
        category="validation",
        enabled=True,
        base_severity=3,
        default_effort=3,
        detector_weight=1,
    ),
    "query_filter_leak": DetectorPolicyEntry(
        detector_id="query_filter_leak",
        category="query",
        enabled=True,
        base_severity=2,
        default_effort=2,
        detector_weight=0,
        allow_write_path_bonus=False,
    ),
}


DEFAULT_SCORING_POLICY = ScoringPolicy(
    severity_multiplier=2,
    blast_radius_multiplier=1,
    effort_multiplier=1,
    confidence_bonus_threshold=0.75,
    confidence_bonus_value=1,
    hotspot_bonus=1,
    multi_slice_bonus=1,
    redesign_bonus=1,
)


def load_engine_policy_bundle() -> EnginePolicyBundle:
    return EnginePolicyBundle(
        detector_policies=dict(DEFAULT_DETECTOR_POLICIES),
        scoring_policy=DEFAULT_SCORING_POLICY,
    )


def get_detector_policy(detector_id: str, bundle: EnginePolicyBundle | None = None) -> DetectorPolicyEntry:
    policy_bundle = bundle or load_engine_policy_bundle()
    return policy_bundle.detector_policies.get(detector_id, FALLBACK_DETECTOR_POLICY)
