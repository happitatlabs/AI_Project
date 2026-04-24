from __future__ import annotations

import os
import re
from typing import Any

from mellow_link.modules.rebuild_assistant.schemas import AssetPresenceSummary, RebuildAssetsPayload

from .analysis_context_builder import AnalysisContextBuilder
from .schemas import (
    AnalysisContextBundle,
    AssetInventoryItem,
    IntentInput,
    MissingContextItem,
    PreparedRebuildInput,
    RefactoringAnalysisInput,
    SourceBlock,
    make_stable_id,
)


class InputAssembler:
    _INTENT_ASSET_NAMES = {
        "goal.txt": "goal",
        "constraints.txt": "constraints",
        "scenario.md": "scenario",
    }
    _FRAMEWORK_ASSET_NAMES = {
        "pom.xml",
        "build.gradle",
        "settings.gradle",
        "gradle.properties",
        "requirements.txt",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
    }
    _NON_ANALYSIS_ASSET_TYPES = {"doc", "framework", "intent"}

    def prepare_input(
        self,
        legacy_service: Any,
        *,
        goal: str,
        assets: RebuildAssetsPayload,
        constraints: list[str] | None = None,
        temp_context: str = "",
    ) -> PreparedRebuildInput:
        intent = self.normalize_intent_inputs(
            goal=goal,
            constraints=constraints,
            scenario=temp_context,
        )
        cleaned_assets = RebuildAssetsPayload(
            source_code=(assets.source_code or "").strip(),
            database_schema=(assets.database_schema or "").strip(),
            sql_queries=(assets.sql_queries or "").strip(),
            ui_template=(assets.ui_template or "").strip(),
            framework_info=(assets.framework_info or "").strip(),
        )
        parts = [
            legacy_service._section("Source Code", cleaned_assets.source_code),
            legacy_service._section("Database Schema", cleaned_assets.database_schema),
            legacy_service._section("SQL Queries", cleaned_assets.sql_queries),
            legacy_service._section("UI Template", cleaned_assets.ui_template),
            legacy_service._section("Framework Info", cleaned_assets.framework_info),
        ]
        prepared = PreparedRebuildInput(
            goal=intent.goal,
            assets=cleaned_assets,
            constraints=list(intent.constraints),
            intent=intent,
            asset_presence=legacy_service._build_asset_presence_from_payload(cleaned_assets),
            safe_bundle=None,
            temp_context=intent.scenario,
            legacy_bundle="\n\n".join(part for part in parts if part),
            scope_limited=legacy_service.is_scope_limited(intent.goal),
        )
        prepared.signals = legacy_service.extract_feature_signals(prepared)
        prepared.missing_context = legacy_service.detect_missing_context(prepared)
        return prepared

    def prepare_safe_bundle_input(
        self,
        legacy_service: Any,
        *,
        goal: str,
        safe_bundle,
        constraints: list[str] | None = None,
    ) -> PreparedRebuildInput:
        analysis_context = AnalysisContextBuilder().build(
            project_id=getattr(safe_bundle, "project_id", ""),
            run_id="runless",
            safe_bundle=safe_bundle,
            goal=goal,
            constraints=constraints or [],
        )
        prepared = self.prepare_analysis_context_input(
            legacy_service,
            analysis_context=analysis_context,
        )
        prepared.safe_bundle = safe_bundle
        return prepared

    def prepare_analysis_context_input(
        self,
        legacy_service: Any,
        *,
        analysis_context: AnalysisContextBundle,
    ) -> PreparedRebuildInput:
        asset_presence = self._build_asset_presence_from_context(analysis_context)
        source_code_blocks: list[str] = []
        schema_blocks: list[str] = []
        sql_blocks: list[str] = []
        ui_blocks: list[str] = []
        doc_blocks: list[str] = []
        accounting_input = None
        accounting_asset_name = ""
        accounting_input_error = ""
        for source in analysis_context.source_blocks:
            content = (source.content or source.excerpt or "").strip()
            if not content:
                continue
            asset_name = source.asset_name or source.locator or source.asset_id
            if legacy_service._looks_like_accounting_payload_asset(asset_name, content):
                if accounting_input is not None or accounting_input_error:
                    accounting_input_error = "multiple accounting payload assets found"
                    accounting_asset_name = asset_name or accounting_asset_name
                    continue
                accounting_input, accounting_input_error = legacy_service._parse_accounting_payload(content)
                accounting_asset_name = asset_name
                continue
            block = f"[SAFE SOURCE: {source.asset_id} | {asset_name or '-'}]\n{content}"
            asset_type = (source.asset_type or "").strip().lower()
            if asset_type == "schema" or legacy_service._is_schema_asset_name(asset_name, content):
                schema_blocks.append(block)
            elif asset_type == "sql" or legacy_service._is_sql_asset_name(asset_name, content):
                sql_blocks.append(block)
            elif asset_type == "ui" or legacy_service._is_ui_asset_name(asset_name):
                ui_blocks.append(block)
            elif asset_type == "doc" or legacy_service._is_doc_asset_name(asset_name):
                doc_blocks.append(block)
            elif asset_type == "framework" or legacy_service._is_framework_asset_name(asset_name):
                continue
            else:
                source_code_blocks.append(block)
        structures = "\n\n".join(
            legacy_service._render_structure_block(structure)
            for structure in analysis_context.seed_structures
            if structure.nodes or structure.edges
        )
        supporting_docs = "\n\n".join(doc_blocks)
        assets = RebuildAssetsPayload(
            source_code="\n\n".join(source_code_blocks),
            database_schema="\n\n".join(schema_blocks),
            sql_queries="\n\n".join(sql_blocks),
            ui_template="\n\n".join(part for part in [structures, "\n\n".join(ui_blocks)] if part),
            framework_info=self._build_context_framework_hint(asset_presence),
        )
        prepared = self.prepare_input(
            legacy_service,
            goal=analysis_context.intent.goal,
            assets=assets,
            constraints=analysis_context.intent.constraints,
            temp_context=analysis_context.intent.scenario,
        )
        prepared.asset_presence = asset_presence
        prepared.analysis_context = analysis_context
        prepared.intent = analysis_context.intent
        prepared.supporting_docs = supporting_docs
        if supporting_docs:
            prepared.legacy_bundle = "\n\n".join(
                part
                for part in [
                    prepared.legacy_bundle,
                    legacy_service._section("Supporting Docs", supporting_docs),
                ]
                if part
            )
        prepared.signals = legacy_service.extract_feature_signals(prepared)
        prepared.missing_context = legacy_service.detect_missing_context(prepared)
        prepared.accounting_input = accounting_input
        prepared.accounting_asset_name = accounting_asset_name
        prepared.accounting_input_error = accounting_input_error
        analysis_context.trust.missing_context = list(prepared.missing_context or [])
        analysis_context.analysis_frame.concept_signals = list(prepared.signals.concepts or [])
        analysis_context.analysis_frame.primary_feature_mode = prepared.signals.primary_feature_mode
        analysis_context.analysis_frame.scope_limited = bool(prepared.scope_limited)
        return prepared

    def normalize_intent_inputs(
        self,
        *,
        goal: str,
        constraints: list[str] | None = None,
        scenario: str = "",
        file_intents: dict[str, list[str]] | None = None,
    ) -> IntentInput:
        file_intents = file_intents or {}
        inline_goal = (goal or "").strip()
        file_goal = "\n".join(item.strip() for item in file_intents.get("goal", []) if item.strip()).strip()
        inline_scenario = (scenario or "").strip()
        file_scenario = "\n\n".join(item.strip() for item in file_intents.get("scenario", []) if item.strip()).strip()
        inline_constraints = self._parse_constraint_lines(constraints or [])
        file_constraints = self._parse_constraint_lines(file_intents.get("constraints", []) or [])
        merged_constraints = self._dedupe_preserving_order(inline_constraints + file_constraints)

        sources: dict[str, str] = {}
        if inline_goal:
            sources["goal"] = "inline"
        elif file_goal:
            sources["goal"] = "goal.txt"
        if inline_constraints and file_constraints:
            sources["constraints"] = "inline+constraints.txt"
        elif inline_constraints:
            sources["constraints"] = "inline"
        elif file_constraints:
            sources["constraints"] = "constraints.txt"
        if inline_scenario:
            sources["scenario"] = "inline"
        elif file_scenario:
            sources["scenario"] = "scenario.md"

        return IntentInput(
            goal=inline_goal or file_goal,
            constraints=merged_constraints,
            scenario=inline_scenario or file_scenario,
            sources=sources,
        )

    def assemble(self, prepared: Any) -> RefactoringAnalysisInput:
        analysis_context = getattr(prepared, "analysis_context", None)
        safe_bundle = getattr(prepared, "safe_bundle", None)
        constraints = [str(item).strip() for item in list(getattr(prepared, "constraints", []) or []) if str(item).strip()]
        intent = getattr(prepared, "intent", None)
        if intent is None:
            intent = self.normalize_intent_inputs(
                goal=str(getattr(prepared, "goal", "") or ""),
                constraints=constraints,
                scenario=str(getattr(prepared, "temp_context", "") or ""),
            )
        if analysis_context is not None:
            asset_inventory = [
                AssetInventoryItem(
                    asset_id=asset.asset_id,
                    name=asset.name,
                    asset_type=asset.asset_type,
                    size=asset.size,
                    language=asset.language,
                    kind_hint=asset.asset_type,
                )
                for asset in analysis_context.assets
                if asset.asset_type not in self._NON_ANALYSIS_ASSET_TYPES
            ]
            source_blocks = [
                SourceBlock(
                    block_id=source.block_id,
                    asset_id=source.asset_id,
                    asset_name=source.asset_name or source.locator or source.asset_id,
                    asset_type=source.asset_type,
                    locator=source.locator,
                    excerpt=source.excerpt,
                    content=source.content,
                    fingerprint=source.fingerprint,
                )
                for source in analysis_context.source_blocks
                if source.asset_type not in self._NON_ANALYSIS_ASSET_TYPES
            ]
            seed_structures = list(analysis_context.seed_structures or [])
            safe_bundle_id = analysis_context.trust.safe_bundle_id
            input_fingerprint = analysis_context.run.input_fingerprint
        elif safe_bundle is not None:
            content_by_asset_id = {source.asset_id: source.content or "" for source in safe_bundle.sources}
            asset_presence = getattr(prepared, "asset_presence", None)
            schema_asset_names = {
                str(name).strip().lower()
                for name in list(getattr(asset_presence, "schema_asset_names", []) or [])
                if str(name).strip()
            }
            sql_asset_names = {
                str(name).strip().lower()
                for name in list(getattr(asset_presence, "sql_asset_names", []) or [])
                if str(name).strip()
            }
            ui_asset_names = {
                str(name).strip().lower()
                for name in list(getattr(asset_presence, "ui_asset_names", []) or [])
                if str(name).strip()
            }
            source_asset_names = {
                str(name).strip().lower()
                for name in list(getattr(asset_presence, "source_asset_names", []) or [])
                if str(name).strip()
            }
            framework_asset_names = {
                str(name).strip().lower()
                for name in list(getattr(asset_presence, "framework_asset_names", []) or [])
                if str(name).strip()
            }
            doc_asset_names = {
                str(name).strip().lower()
                for name in list(getattr(asset_presence, "doc_asset_names", []) or [])
                if str(name).strip()
            }
            asset_inventory = []
            for asset in safe_bundle.asset_summary:
                asset_type = self._asset_type_from_presence(
                    asset.name,
                    content_by_asset_id.get(asset.asset_id, ""),
                    schema_asset_names=schema_asset_names,
                    sql_asset_names=sql_asset_names,
                    ui_asset_names=ui_asset_names,
                    source_asset_names=source_asset_names,
                    framework_asset_names=framework_asset_names,
                    doc_asset_names=doc_asset_names,
                )
                if asset_type in self._NON_ANALYSIS_ASSET_TYPES:
                    continue
                asset_inventory.append(
                    AssetInventoryItem(
                        asset_id=asset.asset_id,
                        name=asset.name,
                        asset_type=asset_type,
                        size=asset.size,
                        language=asset.language,
                        kind_hint=asset.kind_hint,
                    )
                )
            asset_name_by_id = {asset.asset_id: asset.name for asset in safe_bundle.asset_summary}
            source_blocks = []
            for index, source in enumerate(safe_bundle.sources):
                asset_name = asset_name_by_id.get(source.asset_id, source.asset_id)
                asset_type = self._asset_type_from_presence(
                    asset_name,
                    source.content or "",
                    schema_asset_names=schema_asset_names,
                    sql_asset_names=sql_asset_names,
                    ui_asset_names=ui_asset_names,
                    source_asset_names=source_asset_names,
                    framework_asset_names=framework_asset_names,
                    doc_asset_names=doc_asset_names,
                )
                if asset_type in self._NON_ANALYSIS_ASSET_TYPES:
                    continue
                source_blocks.append(
                    SourceBlock(
                        block_id=make_stable_id("SRC", source.asset_id, index, asset_name),
                        asset_id=source.asset_id,
                        asset_name=asset_name,
                        asset_type=asset_type,
                        content=source.content or "",
                    )
                )
            seed_structures = list(safe_bundle.structures or [])
            safe_bundle_id = safe_bundle.bundle_id
            input_fingerprint = ""
        else:
            asset_inventory, source_blocks = self._assemble_without_bundle(prepared)
            seed_structures = []
            safe_bundle_id = ""
            input_fingerprint = ""
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
            intent=intent,
            safe_bundle_id=safe_bundle_id,
            safe_bundle=safe_bundle,
            asset_inventory=asset_inventory,
            source_blocks=source_blocks,
            seed_structures=seed_structures,
            missing_context=missing_context,
            input_fingerprint=input_fingerprint,
        )

    def _build_asset_presence_from_context(self, analysis_context: AnalysisContextBundle) -> AssetPresenceSummary:
        source_names: list[str] = []
        ui_names: list[str] = []
        schema_names: list[str] = []
        sql_names: list[str] = []
        framework_names: list[str] = []
        doc_names: list[str] = []
        for asset in analysis_context.assets:
            asset_type = (asset.asset_type or "").strip().lower()
            if asset_type == "ui":
                ui_names.append(asset.name)
            elif asset_type == "schema":
                schema_names.append(asset.name)
            elif asset_type == "sql":
                sql_names.append(asset.name)
            elif asset_type == "framework":
                framework_names.append(asset.name)
            elif asset_type == "doc":
                doc_names.append(asset.name)
            elif asset_type != "intent":
                source_names.append(asset.name)
        return AssetPresenceSummary(
            has_source_code=bool(source_names),
            has_ui_asset=bool(ui_names),
            has_schema_asset=bool(schema_names),
            has_sql_asset=bool(sql_names),
            has_framework_hint=bool(framework_names),
            has_docs=bool(doc_names),
            framework_runtime_hints=self._framework_runtime_hints(framework_names),
            source_asset_names=source_names,
            ui_asset_names=ui_names,
            schema_asset_names=schema_names,
            sql_asset_names=sql_names,
            framework_asset_names=framework_names,
            doc_asset_names=doc_names,
        )

    def _build_context_framework_hint(self, asset_presence: AssetPresenceSummary) -> str:
        lines: list[str] = []
        if asset_presence.framework_asset_names:
            lines.append("Framework assets: " + ", ".join(asset_presence.framework_asset_names))
        if asset_presence.framework_runtime_hints:
            lines.append("Runtime hints: " + ", ".join(asset_presence.framework_runtime_hints))
        return "\n".join(lines)

    def _framework_runtime_hints(self, framework_asset_names: list[str]) -> list[str]:
        hints: list[str] = []
        joined = " ".join(name.lower() for name in framework_asset_names)
        if "pom.xml" in joined or "gradle" in joined:
            hints.append("java")
        if "package.json" in joined:
            hints.append("node")
        if "requirements.txt" in joined or "pyproject.toml" in joined:
            hints.append("python")
        return self._dedupe_preserving_order(hints)

    def _asset_type_from_presence(
        self,
        asset_name: str,
        content: str,
        *,
        schema_asset_names: set[str],
        sql_asset_names: set[str],
        ui_asset_names: set[str],
        source_asset_names: set[str],
        framework_asset_names: set[str],
        doc_asset_names: set[str],
    ) -> str:
        if self._intent_slot_for_asset_name(asset_name):
            return "intent"
        lowered = (asset_name or "").strip().lower()
        if lowered in schema_asset_names:
            return "schema"
        if lowered in sql_asset_names:
            return "sql"
        if lowered in ui_asset_names:
            return "ui"
        if lowered in source_asset_names:
            return "source"
        if lowered in framework_asset_names:
            return "framework"
        if lowered in doc_asset_names:
            return "doc"
        return self._asset_type(asset_name, content)

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
            asset_type = self._asset_type(name, text)
            if asset_type in self._NON_ANALYSIS_ASSET_TYPES:
                continue
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

    def _asset_type(self, asset_name: str, content: str = "") -> str:
        lowered = (asset_name or "").strip().lower()
        if self._intent_slot_for_asset_name(asset_name):
            return "intent"
        if lowered in self._FRAMEWORK_ASSET_NAMES:
            return "framework"
        if lowered.endswith((".html", ".jsp", ".ftl", ".vue")):
            return "ui"
        if lowered.endswith(".sql"):
            return "schema" if self._looks_like_schema_sql(content) else "sql"
        if lowered.endswith((".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".cs", ".kt", ".rb", ".php", ".go", ".scala")):
            return "source"
        if lowered.endswith(".json"):
            return "json"
        if lowered.endswith((".md", ".txt")):
            return "doc"
        return "other"

    def _looks_like_schema_sql(self, content: str) -> bool:
        lowered_content = (content or "").lower()
        ddl_patterns = (
            r"\bcreate\s+table\b",
            r"\balter\s+table\b",
            r"\bcreate\s+(?:unique\s+)?index\b",
            r"\badd\s+constraint\b",
            r"\bprimary\s+key\b",
            r"\bforeign\s+key\b",
            r"\breferences\s+[a-z_][a-z0-9_]*\b",
        )
        return any(re.search(pattern, lowered_content, flags=re.IGNORECASE) for pattern in ddl_patterns)

    def _intent_slot_for_asset_name(self, asset_name: str) -> str:
        return self._INTENT_ASSET_NAMES.get(self._normalized_asset_name(asset_name), "")

    def _normalized_asset_name(self, asset_name: str) -> str:
        normalized = (asset_name or "").replace("\\", "/")
        return os.path.basename(normalized).strip().lower()

    def _parse_constraint_lines(self, values: list[str]) -> list[str]:
        output: list[str] = []
        for value in values:
            for line in str(value or "").splitlines():
                cleaned = line.strip()
                if cleaned:
                    output.append(cleaned)
        return output

    def _dedupe_preserving_order(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for item in items:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output
