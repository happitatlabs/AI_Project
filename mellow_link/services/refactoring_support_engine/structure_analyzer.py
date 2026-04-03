from __future__ import annotations

import os
import re
from collections import defaultdict

from .schemas import (
    ComponentNode,
    CoverageSummary,
    DependencyEdge,
    FunctionSlice,
    LayerAssignment,
    RefactoringAnalysisInput,
    StructuralHotspot,
    StructureAnalysisResult,
    StructureSnapshot,
    make_stable_id,
    normalize_fingerprint_text,
)


class ComponentCollector:
    _CLASS_PATTERNS = (
        re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)"),
        re.compile(r"\binterface\s+([A-Za-z_][A-Za-z0-9_]*)"),
    )
    _FUNCTION_PATTERNS = (
        (re.compile(r"\basync\s+def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("), "async"),
        (re.compile(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("), None),
        (re.compile(r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("), None),
        (re.compile(r"\bconst\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\("), None),
    )
    _TABLE_PATTERNS = (
        re.compile(r"\bcreate\s+table\s+([A-Za-z_][A-Za-z0-9_]*)", flags=re.IGNORECASE),
        re.compile(r"\bfrom\s+([A-Za-z_][A-Za-z0-9_]*)", flags=re.IGNORECASE),
        re.compile(r"\bjoin\s+([A-Za-z_][A-Za-z0-9_]*)", flags=re.IGNORECASE),
        re.compile(r"\bupdate\s+([A-Za-z_][A-Za-z0-9_]*)", flags=re.IGNORECASE),
        re.compile(r"\binsert\s+into\s+([A-Za-z_][A-Za-z0-9_]*)", flags=re.IGNORECASE),
    )

    def collect(self, analysis_input: RefactoringAnalysisInput) -> tuple[list[ComponentNode], dict[str, str], dict[str, str], dict[str, list[str]], dict[str, list[str]]]:
        components: list[ComponentNode] = []
        component_text_map: dict[str, str] = {}
        component_asset_map: dict[str, str] = {}
        component_name_map: dict[str, str] = {}
        component_responsibility_map: dict[str, list[str]] = {}

        for block in analysis_input.source_blocks:
            names = self._collect_component_names(block.asset_name, block.asset_type, block.content)
            if not names:
                continue
            for name, component_type in names:
                layer = self._infer_layer(name, component_type, block.asset_type)
                component_id = make_stable_id("CMP", name, block.asset_id, layer)
                responsibilities = self._responsibility_families(block.content, component_type, block.asset_type)
                components.append(
                    ComponentNode(
                        component_id=component_id,
                        name=name,
                        component_type=component_type,
                        layer=layer,
                        asset_ids=[block.asset_id],
                        responsibility_families=responsibilities,
                    )
                )
                component_text_map[component_id] = block.content
                component_asset_map[component_id] = block.asset_id
                component_name_map[component_id] = name
                component_responsibility_map[component_id] = responsibilities

        deduped: dict[str, ComponentNode] = {}
        for component in components:
            current = deduped.get(component.component_id)
            if current is None:
                deduped[component.component_id] = component
                continue
            merged_assets = list(dict.fromkeys(current.asset_ids + component.asset_ids))
            merged_responsibilities = list(dict.fromkeys(current.responsibility_families + component.responsibility_families))
            deduped[component.component_id] = current.model_copy(
                update={"asset_ids": merged_assets, "responsibility_families": merged_responsibilities}
            )
        return list(deduped.values()), component_text_map, component_asset_map, component_name_map, component_responsibility_map

    def _collect_component_names(self, asset_name: str, asset_type: str, content: str) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        stem = os.path.splitext(os.path.basename(asset_name or "component"))[0] or "Component"
        if asset_type == "ui":
            results.append((self._screen_name(stem), "screen"))
        for pattern in self._CLASS_PATTERNS:
            for match in pattern.findall(content or ""):
                results.append((match, self._component_type_for_name(match)))
        for pattern, forced_type in self._FUNCTION_PATTERNS:
            for match in pattern.findall(content or ""):
                results.append((self._titleize(match), forced_type or self._component_type_for_name(match)))
        for pattern in self._TABLE_PATTERNS:
            for match in pattern.findall(content or ""):
                results.append((match, "table"))
        if asset_type == "source" and not results:
            results.append((self._titleize(stem), self._component_type_for_name(stem)))
        if asset_type in {"sql", "schema"} and not any(kind == "table" for _, kind in results):
            results.append((self._titleize(stem), "query"))
        output: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for name, component_type in results:
            cleaned = re.sub(r"[^A-Za-z0-9_]+", "", name or "").strip()
            if not cleaned:
                continue
            key = (cleaned.lower(), component_type)
            if key in seen:
                continue
            seen.add(key)
            output.append((cleaned, component_type))
        return output

    def _screen_name(self, stem: str) -> str:
        titled = self._titleize(stem)
        return titled if titled.endswith("Page") else f"{titled}Page"

    def _titleize(self, value: str) -> str:
        chunks = re.split(r"[^A-Za-z0-9]+", value or "")
        return "".join(chunk[:1].upper() + chunk[1:] for chunk in chunks if chunk) or "Component"

    def _component_type_for_name(self, name: str) -> str:
        lowered = (name or "").lower()
        if any(token in lowered for token in ("controller", "handler", "endpoint", "route", "api")):
            return "api"
        if any(token in lowered for token in ("service", "manager", "usecase", "processor")):
            return "service"
        if any(token in lowered for token in ("repository", "repo", "dao", "mapper")):
            return "repository"
        if any(token in lowered for token in ("job", "task", "worker", "queue", "listener")):
            return "async"
        return "component"

    def _infer_layer(self, name: str, component_type: str, asset_type: str) -> str:
        if component_type == "table":
            return "data"
        if component_type == "query":
            return "repository"
        if asset_type == "ui":
            return "ui"
        if component_type == "api":
            return "api"
        if component_type == "service":
            return "service"
        if component_type == "repository":
            return "repository"
        if component_type == "async":
            return "async"
        if asset_type == "sql":
            return "repository"
        if asset_type == "schema":
            return "data"
        return "service"

    def _responsibility_families(self, content: str, component_type: str, asset_type: str) -> list[str]:
        text = (content or "").lower()
        families: list[str] = []
        if any(token in text for token in ("validate", "required", "duplicate", "invalid", "검증", "필수", "중복")):
            families.append("validation")
        if any(token in text for token in ("approve", "reject", "submit", "adjust", "close", "calculate", "정산", "승인", "반려", "마감", "조정")):
            families.append("business")
        if any(token in text for token in ("select ", "insert ", "update ", "delete ", "repository", "session.", "db.", "dao", "query(", "commit(")):
            families.append("persistence")
        if asset_type == "ui" or any(token in text for token in ("render", "<form", "<button", "onclick", "request.getparameter", "템플릿")):
            families.append("ui_orchestration")
        if component_type == "async" or any(token in text for token in ("async ", "await ", "background", "queue", "celery", "job", "worker")):
            families.append("async_orchestration")
        if not families:
            families.append("business")
        return list(dict.fromkeys(families))


class DependencyResolver:
    def resolve(
        self,
        analysis_input: RefactoringAnalysisInput,
        components: list[ComponentNode],
        component_name_map: dict[str, str],
        component_asset_map: dict[str, str],
    ) -> tuple[list[DependencyEdge], dict[str, list[str]]]:
        edges: list[DependencyEdge] = []
        table_usage_map: dict[str, list[str]] = defaultdict(list)
        names_by_asset: dict[str, list[ComponentNode]] = defaultdict(list)
        table_components = {item.component_id: item for item in components if item.layer == "data"}
        for component in components:
            for asset_id in component.asset_ids:
                names_by_asset[asset_id].append(component)

        for block in analysis_input.source_blocks:
            block_components = names_by_asset.get(block.asset_id, [])
            if not block_components:
                continue
            api_ids = [item.component_id for item in block_components if item.layer == "api"]
            service_ids = [item.component_id for item in block_components if item.layer == "service"]
            repo_ids = [item.component_id for item in block_components if item.layer == "repository"]
            async_ids = [item.component_id for item in block_components if item.layer == "async"]
            table_ids = [item.component_id for item in block_components if item.layer == "data"]
            for api_id in api_ids:
                for service_id in service_ids or repo_ids:
                    edges.append(DependencyEdge(from_component=api_id, to_component=service_id, dependency_type="calls"))
            for service_id in service_ids:
                for repo_id in repo_ids:
                    edges.append(DependencyEdge(from_component=service_id, to_component=repo_id, dependency_type="calls"))
            for repo_id in repo_ids:
                for table_id in table_ids:
                    dependency_type = "writes" if re.search(r"\b(insert|update|delete)\b", block.content, flags=re.IGNORECASE) else "reads"
                    edges.append(DependencyEdge(from_component=repo_id, to_component=table_id, dependency_type=dependency_type))
                    table_usage_map[table_id].append(repo_id)
            for service_id in service_ids or api_ids:
                for table_id in table_ids:
                    if service_id not in table_usage_map[table_id]:
                        table_usage_map[table_id].append(service_id)
            for async_id in async_ids:
                for service_id in service_ids or api_ids:
                    edges.append(DependencyEdge(from_component=service_id, to_component=async_id, dependency_type="dispatches"))

        # Cross-asset name-based dependency inference.
        lookup = {component_id: name.lower() for component_id, name in component_name_map.items()}
        block_by_asset = {block.asset_id: block for block in analysis_input.source_blocks}
        for component_id, asset_id in component_asset_map.items():
            block = block_by_asset.get(asset_id)
            if block is None:
                continue
            content = normalize_fingerprint_text(block.content)
            for target_id, lowered_name in lookup.items():
                if target_id == component_id or component_asset_map.get(target_id) == asset_id:
                    continue
                if lowered_name and lowered_name.lower() in content:
                    edges.append(DependencyEdge(from_component=component_id, to_component=target_id, dependency_type="references"))
                    if target_id in table_components and component_id not in table_usage_map[target_id]:
                        table_usage_map[target_id].append(component_id)

        deduped: list[DependencyEdge] = []
        seen: set[tuple[str, str, str]] = set()
        for edge in edges:
            key = (edge.from_component, edge.to_component, edge.dependency_type)
            if edge.from_component == edge.to_component or key in seen:
                continue
            seen.add(key)
            deduped.append(edge)
        deduped.sort(key=lambda item: (item.from_component, item.to_component, item.dependency_type))
        for table_id, users in table_usage_map.items():
            table_usage_map[table_id] = list(dict.fromkeys(users))
        return deduped, dict(table_usage_map)


class FeatureSliceExtractor:
    _API_PATTERNS = (
        re.compile(r"@router\.(get|post|put|delete|patch)\(\s*[\"']([^\"']+)[\"']"),
        re.compile(r"@app\.(get|post|put|delete|patch)\(\s*[\"']([^\"']+)[\"']"),
        re.compile(r"@(Get|Post|Put|Delete|Patch)Mapping\(\s*[\"']([^\"']+)[\"']"),
    )
    _API_HANDLER_PATTERNS = (
        re.compile(r"\basync\s+def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
        re.compile(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
        re.compile(r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
    )
    _UI_ACTION_PATTERNS = (
        re.compile(r"onclick\s*=\s*[\"'][^\"']*?([A-Za-z_][A-Za-z0-9_]*)\("),
        re.compile(r"\b(?:def|function)\s+(submit[A-Za-z0-9_]*|save[A-Za-z0-9_]*|approve[A-Za-z0-9_]*|reject[A-Za-z0-9_]*)\s*\("),
    )

    def extract(
        self,
        analysis_input: RefactoringAnalysisInput,
        components: list[ComponentNode],
        dependencies: list[DependencyEdge],
        component_asset_map: dict[str, str],
        component_responsibility_map: dict[str, list[str]],
        table_usage_map: dict[str, list[str]],
    ) -> tuple[list[FunctionSlice], dict[str, list[str]]]:
        seeds = self._seed_entries(analysis_input)
        if not seeds:
            seeds = [self._usecase_seed(analysis_input.goal, analysis_input.asset_inventory)]
        seeds = sorted(seeds, key=lambda item: (item["priority"], item["asset_id"], item["entry_point"]))
        components_by_asset: dict[str, list[str]] = defaultdict(list)
        layer_by_component = {component.component_id: component.layer for component in components}
        component_name_by_id = {component.component_id: component.name for component in components}
        table_ids = {component.component_id for component in components if component.layer == "data"}
        for component_id, asset_id in component_asset_map.items():
            components_by_asset[asset_id].append(component_id)

        adjacency: dict[str, list[str]] = defaultdict(list)
        outgoing: dict[str, list[DependencyEdge]] = defaultdict(list)
        for edge in dependencies:
            adjacency[edge.from_component].append(edge.to_component)
            adjacency[edge.to_component].append(edge.from_component)
            outgoing[edge.from_component].append(edge)

        seed_anchor_map: dict[str, list[str]] = {}
        peer_entry_component_ids: set[str] = set()
        for seed in seeds:
            anchor_ids = self._seed_anchor_components(
                seed,
                components_by_asset.get(seed["asset_id"], []),
                component_name_by_id,
                layer_by_component,
            )
            seed_anchor_map[self._seed_key(seed)] = anchor_ids
            peer_entry_component_ids.update(anchor_ids)

        slices: list[FunctionSlice] = []
        slice_component_map: dict[str, list[str]] = {}
        for seed in seeds:
            asset_component_ids = components_by_asset.get(seed["asset_id"], [])
            seed_anchor_ids = seed_anchor_map.get(self._seed_key(seed), [])
            related_components = self._initial_components_for_seed(
                seed,
                asset_component_ids,
                seed_anchor_ids,
                peer_entry_component_ids,
                layer_by_component,
            )
            frontier = list(related_components)
            visited = set(related_components)
            seed_write_tables = self._seed_write_tables(seed_anchor_ids or related_components, outgoing, table_ids)
            while frontier:
                current = frontier.pop(0)
                for neighbor in adjacency.get(current, []):
                    if neighbor in visited:
                        continue
                    if self._should_stop_expansion(
                        current=current,
                        neighbor=neighbor,
                        layer_by_component=layer_by_component,
                        component_responsibility_map=component_responsibility_map,
                        table_ids=table_ids,
                        seed_write_tables=seed_write_tables,
                        seed_anchor_ids=set(seed_anchor_ids),
                        peer_entry_component_ids=peer_entry_component_ids,
                    ):
                        continue
                    visited.add(neighbor)
                    frontier.append(neighbor)
                    related_components.append(neighbor)
            related_components = list(dict.fromkeys(related_components))
            related_tables = [component_id for component_id in related_components if component_id in table_ids]
            dependencies_view = [
                f"{edge.from_component}->{edge.to_component}"
                for edge in dependencies
                if edge.from_component in related_components and edge.to_component in related_components
            ]
            business_rules = [constraint for constraint in analysis_input.constraints[:2]]
            slices.append(
                FunctionSlice(
                    slice_id=make_stable_id("SLICE", seed["name"], seed["asset_id"]),
                    name=seed["name"],
                    entry_points=[seed["entry_point"]],
                    related_components=related_components,
                    related_tables=related_tables,
                    business_rules=business_rules,
                    dependencies=list(dict.fromkeys(dependencies_view)),
                )
            )
            slice_component_map[slices[-1].slice_id] = related_components

        # Async boundary split fallback.
        async_components = [component for component in components if component.layer == "async"]
        for component in async_components:
            if any(component.component_id in item.related_components for item in slices):
                continue
            slice_id = make_stable_id("SLICE", "usecase", component.name)
            slices.append(
                FunctionSlice(
                    slice_id=slice_id,
                    name=f"usecase:{self._normalize_usecase(component.name)}",
                    entry_points=[f"usecase:{self._normalize_usecase(component.name)}"],
                    related_components=[component.component_id],
                    related_tables=[],
                    business_rules=[],
                    dependencies=[],
                )
            )
            slice_component_map[slice_id] = [component.component_id]

        slices.sort(key=lambda item: (item.entry_points[0] if item.entry_points else item.name, item.slice_id))
        return slices, {slice_id: slice_component_map[slice_id] for slice_id in sorted(slice_component_map)}

    def _seed_entries(self, analysis_input: RefactoringAnalysisInput) -> list[dict[str, str]]:
        seeds: list[dict[str, str]] = []
        for block in analysis_input.source_blocks:
            for pattern in self._API_PATTERNS:
                for match in pattern.finditer(block.content or ""):
                    method, path = match.groups()
                    normalized_method = method.upper()
                    if len(normalized_method) > 6 and normalized_method.endswith("MAPPING"):
                        normalized_method = normalized_method.replace("MAPPING", "").upper()
                    seeds.append(
                        {
                            "name": f"api:{normalized_method} {path}",
                            "entry_point": f"api:{normalized_method} {path}",
                            "asset_id": block.asset_id,
                            "anchor": self._api_anchor_name(block.content or "", match.end(), path),
                            "kind": "api",
                            "priority": 1,
                        }
                    )
            if any(seed["asset_id"] == block.asset_id for seed in seeds):
                continue
            if block.asset_type != "ui":
                continue
            action = self._ui_action_name(block.content or "")
            if not action:
                continue
            screen = os.path.splitext(os.path.basename(block.asset_name))[0] or "screen"
            seeds.append(
                {
                    "name": f"ui:{self._screen_name(screen)}#{action}",
                    "entry_point": f"ui:{self._screen_name(screen)}#{action}",
                    "asset_id": block.asset_id,
                    "anchor": action,
                    "kind": "ui",
                    "priority": 2,
                }
            )
        deduped: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in seeds:
            key = f"{item['entry_point']}::{item['asset_id']}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _usecase_seed(self, goal: str, assets) -> dict[str, str]:
        usecase = self._normalize_usecase(goal or (assets[0].name if assets else "legacy_flow"))
        asset_id = assets[0].asset_id if assets else "legacy"
        return {
            "name": f"usecase:{usecase}",
            "entry_point": f"usecase:{usecase}",
            "asset_id": asset_id,
            "anchor": usecase,
            "kind": "usecase",
            "priority": 3,
        }

    def _normalize_usecase(self, text: str) -> str:
        lowered = re.sub(r"[^A-Za-z0-9가-힣]+", " ", text or "").strip().lower()
        tokens = [token for token in lowered.split() if token not in {"modernize", "legacy", "feature", "flow", "기능", "현대화"}]
        if not tokens:
            return "legacy_flow"
        return "_".join(tokens[:3])

    def _seed_key(self, seed: dict[str, str]) -> str:
        return f"{seed['asset_id']}::{seed['entry_point']}"

    def _normalize_name(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", (text or "").lower())

    def _api_anchor_name(self, text: str, start_index: int, path: str) -> str:
        snippet = (text or "")[start_index:start_index + 240]
        for pattern in self._API_HANDLER_PATTERNS:
            match = pattern.search(snippet)
            if match:
                return match.group(1)
        path_tokens = [token for token in re.split(r"[^A-Za-z0-9]+", path or "") if token]
        return path_tokens[-1] if path_tokens else "handler"

    def _seed_anchor_components(
        self,
        seed: dict[str, str],
        asset_component_ids: list[str],
        component_name_by_id: dict[str, str],
        layer_by_component: dict[str, str],
    ) -> list[str]:
        normalized_anchor = self._normalize_name(seed.get("anchor", ""))
        kind = seed.get("kind", "usecase")
        if kind == "api":
            preferred_layers = {"api", "service"}
        elif kind == "ui":
            preferred_layers = {"ui"}
        else:
            preferred_layers = {"api", "service", "repository"}
        matching = [
            component_id
            for component_id in asset_component_ids
            if layer_by_component.get(component_id) in preferred_layers
            and normalized_anchor
            and self._normalize_name(component_name_by_id.get(component_id, "")) == normalized_anchor
        ]
        if matching:
            return matching
        matching = [
            component_id
            for component_id in asset_component_ids
            if layer_by_component.get(component_id) in preferred_layers
        ]
        if matching:
            return matching
        return list(asset_component_ids)

    def _initial_components_for_seed(
        self,
        seed: dict[str, str],
        asset_component_ids: list[str],
        seed_anchor_ids: list[str],
        peer_entry_component_ids: set[str],
        layer_by_component: dict[str, str],
    ) -> list[str]:
        related_components = list(seed_anchor_ids)
        for component_id in asset_component_ids:
            if component_id in related_components:
                continue
            if component_id in peer_entry_component_ids:
                continue
            layer = layer_by_component.get(component_id, "")
            if seed["kind"] in {"api", "ui"} and layer == "async":
                continue
            if layer in {"service", "repository", "data"}:
                related_components.append(component_id)
                continue
            if seed["kind"] == "api" and layer == "api":
                related_components.append(component_id)
                continue
            if seed["kind"] == "ui" and layer == "ui":
                related_components.append(component_id)
        if not related_components:
            related_components = [
                component_id
                for component_id in asset_component_ids
                if component_id not in peer_entry_component_ids
                and not (seed["kind"] in {"api", "ui"} and layer_by_component.get(component_id) == "async")
            ]
        if not related_components:
            related_components = list(asset_component_ids)
        return list(dict.fromkeys(related_components))

    def _seed_write_tables(
        self,
        seed_component_ids: list[str],
        outgoing: dict[str, list[DependencyEdge]],
        table_ids: set[str],
    ) -> set[str]:
        visited = set(seed_component_ids)
        frontier = list(seed_component_ids)
        write_tables: set[str] = set()
        while frontier:
            current = frontier.pop(0)
            for edge in outgoing.get(current, []):
                if edge.to_component in table_ids and edge.dependency_type == "writes":
                    write_tables.add(edge.to_component)
                if edge.to_component in visited or edge.to_component in table_ids:
                    continue
                if edge.dependency_type not in {"calls", "dispatches", "references"}:
                    continue
                visited.add(edge.to_component)
                frontier.append(edge.to_component)
        return write_tables

    def _ui_action_name(self, text: str) -> str:
        for pattern in self._UI_ACTION_PATTERNS:
            match = pattern.search(text or "")
            if match:
                return re.sub(r"[^A-Za-z0-9_]+", "", match.group(1)).lower()
        lowered = (text or "").lower()
        for token in ("submit", "save", "approve", "reject"):
            if token in lowered:
                return token
        return ""

    def _screen_name(self, stem: str) -> str:
        titled = "".join(part[:1].upper() + part[1:] for part in re.split(r"[^A-Za-z0-9]+", stem) if part) or "Screen"
        return titled if titled.endswith("Page") else f"{titled}Page"

    def _should_stop_expansion(
        self,
        *,
        current: str,
        neighbor: str,
        layer_by_component: dict[str, str],
        component_responsibility_map: dict[str, list[str]],
        table_ids: set[str],
        seed_write_tables: set[str],
        seed_anchor_ids: set[str],
        peer_entry_component_ids: set[str],
    ) -> bool:
        if neighbor in peer_entry_component_ids and neighbor not in seed_anchor_ids:
            return True
        if neighbor in table_ids and seed_write_tables and neighbor not in seed_write_tables:
            return True
        current_layer = layer_by_component.get(current, "")
        neighbor_layer = layer_by_component.get(neighbor, "")
        if "async" in {current_layer, neighbor_layer} and current_layer != neighbor_layer:
            return True
        current_families = set(component_responsibility_map.get(current, []))
        neighbor_families = set(component_responsibility_map.get(neighbor, []))
        if current_families and neighbor_families and current_families.isdisjoint(neighbor_families) and neighbor_layer not in {"repository", "data"}:
            return True
        if current in table_ids and neighbor in table_ids:
            return True
        return False


class HotspotScorer:
    def score(
        self,
        components: list[ComponentNode],
        dependencies: list[DependencyEdge],
        slice_component_map: dict[str, list[str]],
    ) -> list[StructuralHotspot]:
        degree_map: dict[str, int] = defaultdict(int)
        for edge in dependencies:
            degree_map[edge.from_component] += 1
            degree_map[edge.to_component] += 1
        slice_count: dict[str, int] = defaultdict(int)
        for component_ids in slice_component_map.values():
            for component_id in component_ids:
                slice_count[component_id] += 1
        hotspots: list[StructuralHotspot] = []
        for component in components:
            reasons: list[str] = []
            score = 0
            if len(component.responsibility_families) >= 2:
                reasons.append("multiple responsibility families")
                score += 2
            if degree_map.get(component.component_id, 0) >= 3:
                reasons.append("high dependency degree")
                score += 1
            if slice_count.get(component.component_id, 0) >= 2:
                reasons.append("shared across slices")
                score += 1
            if reasons:
                hotspots.append(StructuralHotspot(component_id=component.component_id, reasons=reasons, score=score))
        hotspots.sort(key=lambda item: (-item.score, item.component_id))
        return hotspots


class StructureAnalyzer:
    def __init__(self) -> None:
        self.component_collector = ComponentCollector()
        self.dependency_resolver = DependencyResolver()
        self.feature_slice_extractor = FeatureSliceExtractor()
        self.hotspot_scorer = HotspotScorer()

    def analyze(self, analysis_input: RefactoringAnalysisInput) -> StructureAnalysisResult:
        seed_structures = list(analysis_input.seed_structures or [])
        components, component_text_map, component_asset_map, component_name_map, component_responsibility_map = self.component_collector.collect(analysis_input)
        dependencies, table_usage_map = self.dependency_resolver.resolve(
            analysis_input,
            components,
            component_name_map,
            component_asset_map,
        )
        feature_slices, slice_component_map = self.feature_slice_extractor.extract(
            analysis_input,
            components,
            dependencies,
            component_asset_map,
            component_responsibility_map,
            table_usage_map,
        )
        hotspots = self.hotspot_scorer.score(components, dependencies, slice_component_map)
        layer_map = [LayerAssignment(component_id=item.component_id, layer=item.layer) for item in components]
        coverage_summary = CoverageSummary(
            asset_count=len(analysis_input.asset_inventory),
            source_block_count=len(analysis_input.source_blocks),
            component_count=len(components),
            slice_count=len(feature_slices),
            missing_context_count=len(analysis_input.missing_context),
        )
        snapshot = StructureSnapshot(
            feature_slices=feature_slices,
            components=components,
            dependencies=dependencies,
            hotspots=hotspots,
            layer_map=layer_map,
            coverage_summary=coverage_summary,
        )
        return StructureAnalysisResult(
            analysis_input=analysis_input,
            structure_snapshot=snapshot,
            seed_structures=seed_structures,
            component_text_map=component_text_map,
            component_asset_map=component_asset_map,
            component_layer_map={item.component_id: item.layer for item in components},
            component_responsibility_map=component_responsibility_map,
            component_name_map=component_name_map,
            slice_component_map=slice_component_map,
            table_usage_map=table_usage_map,
        )
