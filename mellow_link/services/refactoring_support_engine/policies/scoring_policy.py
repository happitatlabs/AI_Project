from __future__ import annotations

from dataclasses import dataclass, field

from .detector_policy import DetectorPolicyEntry


@dataclass(frozen=True)
class ScoringPolicy:
    severity_multiplier: int = 2
    blast_radius_multiplier: int = 1
    effort_multiplier: int = 1
    confidence_bonus_threshold: float = 0.75
    confidence_bonus_value: int = 1
    hotspot_bonus: int = 1
    multi_slice_bonus: int = 1
    redesign_bonus: int = 1


@dataclass(frozen=True)
class EnginePolicyBundle:
    detector_policies: dict[str, DetectorPolicyEntry] = field(default_factory=dict)
    scoring_policy: ScoringPolicy = field(default_factory=ScoringPolicy)
