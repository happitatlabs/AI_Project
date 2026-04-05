from __future__ import annotations

from typing import Any

from .schemas import (
    AssetInventoryItem,
    MissingContextItem,
    RefactoringAnalysisInput,
    SourceBlock,
    make_stable_id,
)


class InputAssembler:
    def assemble(self, prepared: Any) -> RefactoringAnalysisInput:
        safe_bundle = getattr(prepared, "safe_bundle", None)
        constraints = [str(item).strip() for item in list(getattr(prepared, "constraints", []) or []) if str(item).strip()]
        if safe_bundle is not None:
            asset_inventory = [
                AssetInventoryItem(
                    asset_id=asset.asset_id,
                    name=asset.name,
                    asset_type=self._asset_type(asset.name),
                    size=asset.size,
                    language=asset.language,
                    kind_hint=asset.kind_hint,
                )
                for asset in safe_bundle.asset_summary
            ]
            asset_name_by_id = {asset.asset_id: asset.name for asset in safe_bundle.asset_summary}
            source_blocks = [
                SourceBlock(
                    block_id=make_stable_id("SRC", source.asset_id, index, asset_name_by_id.get(source.asset_id, "")),
                    asset_id=source.asset_id,
                    asset_name=asset_name_by_id.get(source.asset_id, source.asset_id),
                    asset_type=self._asset_type(asset_name_by_id.get(source.asset_id, "")),
                    content=source.content or "",
                )
                for index, source in enumerate(safe_bundle.sources)
            ]
            seed_structures = list(safe_bundle.structures or [])
            safe_bundle_id = safe_bundle.bundle_id
        else:
            asset_inventory, source_blocks = self._assemble_without_bundle(prepared)
            seed_structures = []
            safe_bundle_id = ""
        missing_context = list(getattr(prepared, "missing_context_details", []) or [])
        if not missing_context:
            missing_context = [
                MissingContextItem(required_material=item, reason="추가 구조 근거가 필요합니다.")
                for item in list(getattr(prepared, "missing_context", []) or [])
                if str(item).strip()
            ]

        return RefactoringAnalysisInput(
            goal=str(getattr(prepared, "goal", "") or "").strip(),
            constraints=constraints,
            safe_bundle_id=safe_bundle_id,
            safe_bundle=safe_bundle,
            asset_inventory=asset_inventory,
            source_blocks=source_blocks,
            seed_structures=seed_structures,
            missing_context=missing_context,
        )

    def _assemble_without_bundle(self, prepared: Any) -> tuple[list[AssetInventoryItem], list[SourceBlock]]:
        asset_specs = [
            ("source_code", "legacy_source.py", getattr(getattr(prepared, "assets", None), "source_code", "")),
            ("database_schema", "schema.sql", getattr(getattr(prepared, "assets", None), "database_schema", "")),
            ("sql_queries", "query.sql", getattr(getattr(prepared, "assets", None), "sql_queries", "")),
            ("ui_template", "screen.html", getattr(getattr(prepared, "assets", None), "ui_template", "")),
            ("framework_info", "framework.txt", getattr(getattr(prepared, "assets", None), "framework_info", "")),
        ]
        asset_inventory: list[AssetInventoryItem] = []
        source_blocks: list[SourceBlock] = []
        for slot, name, content in asset_specs:
            text = str(content or "").strip()
            if not text:
                continue
            asset_id = make_stable_id("ASSET", slot, name)
            asset_type = self._asset_type(name)
            asset_inventory.append(
                AssetInventoryItem(
                    asset_id=asset_id,
                    name=name,
                    asset_type=asset_type,
                    size=len(text.encode("utf-8")),
                )
            )
            source_blocks.append(
                SourceBlock(
                    block_id=make_stable_id("SRC", asset_id, slot),
                    asset_id=asset_id,
                    asset_name=name,
                    asset_type=asset_type,
                    content=text,
                )
            )
        return asset_inventory, source_blocks

    def _asset_type(self, asset_name: str) -> str:
        lowered = (asset_name or "").strip().lower()
        if lowered.endswith((".html", ".jsp", ".ftl", ".vue")):
            return "ui"
        if lowered.endswith(".sql"):
            return "schema" if lowered == "schema.sql" or "schema" in lowered else "sql"
        if lowered.endswith((".py", ".java", ".js", ".ts", ".cs")):
            return "source"
        if lowered.endswith(".json"):
            return "json"
        if lowered.endswith((".md", ".txt")):
            return "doc"
        return "other"
