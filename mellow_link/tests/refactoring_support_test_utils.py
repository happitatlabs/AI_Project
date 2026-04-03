from __future__ import annotations

from mellow_link.services.anonymization.bundle_builder import SafeBundleBuilder
from mellow_link.services.anonymization.schemas import (
    AnonymizationAsset,
    CanonicalAnonymizedSource,
    MaskingLevel,
    StructureArtifact,
)


def build_safe_bundle(asset_specs):
    assets = []
    sources = []
    structures = []
    for index, spec in enumerate(asset_specs, start=1):
        asset_id = f"asset_{index:03d}"
        content = spec.get("content", "")
        assets.append(
            AnonymizationAsset(
                asset_id=asset_id,
                name=spec["name"],
                temp_file_id=f"temp_{index:03d}",
                size=len(content.encode("utf-8")),
            )
        )
        sources.append(
            CanonicalAnonymizedSource(
                asset_id=asset_id,
                level=MaskingLevel.FULL,
                language=spec.get("language", ""),
                content=content,
            )
        )
        structures.append(
            StructureArtifact(
                asset_id=asset_id,
                level=MaskingLevel.FULL,
                extracted_from="canonical",
                nodes=[],
                edges=[],
            )
        )
    return SafeBundleBuilder().build(
        project_id="proj_refactoring_support_test",
        masking_level=MaskingLevel.FULL,
        assets=assets,
        canonical_sources=sources,
        structures=structures,
    )
