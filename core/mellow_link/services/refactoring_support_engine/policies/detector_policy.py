from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DetectorPolicyEntry:
    detector_id: str
    category: str
    enabled: bool
    base_severity: int
    default_effort: int
    detector_weight: int = 0
    allow_cross_layer_bonus: bool = True
    allow_write_path_bonus: bool = True
    allow_hotspot_bonus: bool = True
