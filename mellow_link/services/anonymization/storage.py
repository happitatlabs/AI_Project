from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mellow_link.config.settings import get_settings

from .schemas import AnonymizationAsset, CanonicalAnonymizedSource, MaskingLevel, StructureArtifact


class AnonymizationStorage:
    """Internal-only storage abstraction for anonymization artifacts."""

    def __init__(self, root: Path | None = None) -> None:
        settings = get_settings()
        self.root = Path(root or settings.anonymization_storage_root)

    def resolve_internal_path(self, *parts: str) -> Path:
        candidate = self.root.joinpath(*[self._safe_segment(part) for part in parts]).resolve()
        resolved_root = self.root.resolve()
        if resolved_root not in candidate.parents and candidate != resolved_root:
            raise ValueError("Path escapes anonymization storage root")
        return candidate

    def store_original(self, *, project_id: str, asset: AnonymizationAsset, content: bytes) -> Path:
        path = self.resolve_internal_path("originals", project_id, asset.asset_id, "source.bin")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def store_canonical(self, *, project_id: str, canonical: CanonicalAnonymizedSource) -> Path:
        path = self.resolve_internal_path("canonical", project_id, canonical.asset_id, "canonical.txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(canonical.content, encoding="utf-8")
        return path

    def store_structure(self, *, project_id: str, structure: StructureArtifact) -> Path:
        path = self.resolve_internal_path("structures", project_id, structure.asset_id, "structure.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(structure.model_dump(by_alias=True), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def store_mapping_internal(self, *, project_id: str, asset_id: str, mapping: dict[str, dict[str, str]]) -> Path:
        path = self.resolve_internal_path("mappings", project_id, asset_id, "mapping.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def store_export(self, *, project_id: str, level: MaskingLevel, payload: dict[str, Any], name: str = "bundle") -> Path:
        path = self.resolve_internal_path("exports", project_id, level.value.lower(), f"{self._safe_segment(name)}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _safe_segment(self, value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
        return cleaned.strip("._") or "unknown"
