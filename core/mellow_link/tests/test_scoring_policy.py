from types import SimpleNamespace

from mellow_link.services.refactoring_support_engine.decision_engine import DecisionEngine
from mellow_link.services.refactoring_support_engine.policies import (
    DetectorPolicyEntry,
    EnginePolicyBundle,
    ScoringPolicy,
)


def _issue(**overrides):
    defaults = {
        "detector_id": "mixed_responsibility",
        "severity": 4,
        "blast_radius": 3,
        "effort": 2,
        "confidence": 0.8,
        "affected_component_ids": ["cmp-a"],
        "affected_slice_ids": ["slice-a"],
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_scoring_policy_is_deterministic_for_same_input():
    policy_bundle = EnginePolicyBundle(
        detector_policies={
            "mixed_responsibility": DetectorPolicyEntry(
                detector_id="mixed_responsibility",
                category="structure",
                enabled=True,
                base_severity=3,
                default_effort=3,
                detector_weight=1,
            )
        },
        scoring_policy=ScoringPolicy(),
    )
    engine = DecisionEngine(policy_bundle=policy_bundle)
    issue = _issue()

    first = engine._priority_score(issue, "refactor", {"cmp-a": 2}, policy_bundle.scoring_policy)
    second = engine._priority_score(issue, "refactor", {"cmp-a": 2}, policy_bundle.scoring_policy)
    breakdown = engine._score_breakdown(issue, "refactor", {"cmp-a": 2}, policy_bundle.scoring_policy)

    assert first == second
    assert breakdown["final_score"] == first


def test_scoring_policy_applies_detector_weight():
    weighted_bundle = EnginePolicyBundle(
        detector_policies={
            "mixed_responsibility": DetectorPolicyEntry(
                detector_id="mixed_responsibility",
                category="structure",
                enabled=True,
                base_severity=3,
                default_effort=3,
                detector_weight=3,
            )
        },
        scoring_policy=ScoringPolicy(),
    )
    base_bundle = EnginePolicyBundle(
        detector_policies={
            "mixed_responsibility": DetectorPolicyEntry(
                detector_id="mixed_responsibility",
                category="structure",
                enabled=True,
                base_severity=3,
                default_effort=3,
                detector_weight=0,
            )
        },
        scoring_policy=ScoringPolicy(),
    )
    issue = _issue()

    weighted = DecisionEngine(policy_bundle=weighted_bundle)._priority_score(issue, "refactor", {"cmp-a": 0}, weighted_bundle.scoring_policy)
    base = DecisionEngine(policy_bundle=base_bundle)._priority_score(issue, "refactor", {"cmp-a": 0}, base_bundle.scoring_policy)

    assert weighted == base + 3


def test_scoring_policy_applies_hotspot_multi_slice_and_redesign_bonus():
    policy_bundle = EnginePolicyBundle(
        detector_policies={
            "boundary_mismatch": DetectorPolicyEntry(
                detector_id="boundary_mismatch",
                category="boundary",
                enabled=True,
                base_severity=4,
                default_effort=5,
                detector_weight=2,
                allow_hotspot_bonus=True,
            )
        },
        scoring_policy=ScoringPolicy(
            severity_multiplier=2,
            blast_radius_multiplier=1,
            effort_multiplier=1,
            confidence_bonus_threshold=0.75,
            confidence_bonus_value=1,
            hotspot_bonus=2,
            multi_slice_bonus=3,
            redesign_bonus=4,
        ),
    )
    engine = DecisionEngine(policy_bundle=policy_bundle)
    issue = _issue(
        detector_id="boundary_mismatch",
        affected_component_ids=["cmp-a", "cmp-b"],
        affected_slice_ids=["slice-a", "slice-b"],
    )

    breakdown = engine._score_breakdown(issue, "redesign", {"cmp-a": 2}, policy_bundle.scoring_policy)
    score = breakdown["final_score"]

    assert score == 21
    assert breakdown == {
        "severity_component": 8,
        "blast_radius_component": 3,
        "effort_component": 2,
        "confidence_bonus": 1,
        "detector_weight": 2,
        "hotspot_bonus": 2,
        "multi_slice_bonus": 3,
        "redesign_bonus": 4,
        "final_score": 21,
    }
