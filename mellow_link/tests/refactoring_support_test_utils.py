from __future__ import annotations

from pathlib import Path

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


SAMPLES_ROOT = Path(__file__).resolve().parents[1] / "modules" / "rebuild_assistant" / "samples"


def load_sample_asset_specs(sample_name: str) -> list[dict[str, str]]:
    sample_dir = SAMPLES_ROOT / sample_name
    return [
        {"name": path.name, "content": path.read_text(encoding="utf-8")}
        for path in sample_dir.iterdir()
        if path.is_file() and path.name.lower() not in {"readme.md", "goal.txt", "constraints.txt"}
    ]


def load_sample_case(sample_name: str, fallback_goal: str = "") -> dict[str, object]:
    sample_dir = SAMPLES_ROOT / sample_name
    goal_path = sample_dir / "goal.txt"
    constraints_path = sample_dir / "constraints.txt"
    asset_specs = load_sample_asset_specs(sample_name)
    goal = goal_path.read_text(encoding="utf-8").strip() if goal_path.exists() else (fallback_goal or sample_name)
    constraints = (
        [line.strip() for line in constraints_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if constraints_path.exists()
        else []
    )
    return {
        "sample_dir": sample_dir,
        "goal": goal,
        "constraints": constraints,
        "asset_specs": asset_specs,
        "safe_bundle": build_safe_bundle(asset_specs),
    }
