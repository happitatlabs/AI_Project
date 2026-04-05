from __future__ import annotations

import uuid

from .schemas import (
    AnonymizationAsset,
    BundleAssetSummary,
    CanonicalAnonymizedSource,
    MaskingLevel,
    SafeAnalysisBundle,
    SafeBundleGuard,
    StructureArtifact,
)


class SafeBundleBuilder:
    """Build safe analysis bundles without originals or mapping."""

    def build(
        self,
        *,
        project_id: str,
        masking_level: MaskingLevel,
        assets: list[AnonymizationAsset],
        canonical_sources: list[CanonicalAnonymizedSource],
        structures: list[StructureArtifact],
    ) -> SafeAnalysisBundle:
        asset_summary = [
            BundleAssetSummary(
                asset_id=asset.asset_id,
                name=asset.name,
                temp_file_id=asset.temp_file_id,
                size=asset.size,
                kind_hint=asset.kind_hint,
                language=asset.language,
            )
            for asset in assets
        ]
        return SafeAnalysisBundle(
            bundle_id=f"safe_bundle_{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            masking_level=masking_level,
            asset_summary=asset_summary,
            sources=canonical_sources,
            structures=structures,
            guard=SafeBundleGuard(
                contains_original=False,
                contains_mapping=False,
                canonical_only=True,
                structure_extracted_from_canonical=True,
            ),
        )
