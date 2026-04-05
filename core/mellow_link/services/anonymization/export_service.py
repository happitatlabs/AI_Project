from __future__ import annotations

from .masking_levels import is_publicly_visible
from .schemas import (
    CanonicalAnonymizedSource,
    ExportVisibilityPolicy,
    MaskingLevel,
    PublicExportBundle,
    PublicExportSource,
    PublicExportStructure,
    StructureArtifact,
)


class ExportService:
    """Generates externally shareable anonymized artifacts using public export schemas only."""

    _FORBIDDEN_EXPORT_KEYS = {"original_bytes", "content_text", "mapping", "mapping_path", "original_path"}

    def build_public_exports(
        self,
        *,
        canonical_sources: list[CanonicalAnonymizedSource],
        structures: list[StructureArtifact],
        visibility_policy: ExportVisibilityPolicy,
        masking_policy,
    ) -> dict[MaskingLevel, PublicExportBundle]:
        exports: dict[MaskingLevel, PublicExportBundle] = {}
        for level in (MaskingLevel.FULL, MaskingLevel.PARTIAL, MaskingLevel.FULL_MASKED):
            if not is_publicly_visible(level, visibility_policy):
                continue
            exports[level] = PublicExportBundle(
                level=level,
                sources=[
                    PublicExportSource.model_validate(
                        self._sanitize_export_dict(masking_policy.apply_source(item, level).model_dump())
                    )
                    for item in canonical_sources
                ],
                structures=[
                    PublicExportStructure.model_validate(
                        self._sanitize_export_dict(masking_policy.apply_structure(item, level).model_dump(by_alias=True))
                    )
                    for item in structures
                ],
            )
        return exports

    def _sanitize_export_dict(self, payload: dict) -> dict:
        return {key: value for key, value in payload.items() if key not in self._FORBIDDEN_EXPORT_KEYS}
