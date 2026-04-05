from __future__ import annotations

from .schemas import ExportVisibilityPolicy, MaskingLevel


def default_export_visibility_policy() -> ExportVisibilityPolicy:
    """Default policy keeps FULL internal-only."""

    return ExportVisibilityPolicy()


def is_publicly_visible(level: MaskingLevel, policy: ExportVisibilityPolicy) -> bool:
    if level == MaskingLevel.FULL:
        return bool(policy.allow_full_download)
    if level == MaskingLevel.PARTIAL:
        return bool(policy.allow_partial_download)
    if level == MaskingLevel.FULL_MASKED:
        return bool(policy.allow_full_masked_download)
    return False
