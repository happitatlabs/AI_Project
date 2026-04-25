from __future__ import annotations

import json
import re
from hashlib import sha1
from typing import Iterable

from mellow_link.services.anonymization.schemas import SafeAnalysisBundle
from mellow_link.services.refactoring_support_engine.schemas import (
    AnalysisContextAsset,
    AnalysisContextBundle,
    AnalysisContextEvidenceItem,
    AnalysisContextProject,
    AnalysisContextSourceBlock,
    AnalysisFrame,
    AnalysisRun,
    AnalysisTrust,
    IntentInput,
    make_stable_id,
    normalize_fingerprint_text,
    stable_hash,
)

SCHEMA_VERSION = "analysis_context_v1"

_INTENT_FILENAMES = {"goal.txt", "constraints.txt", "scenario.md"}
_FRAMEWORK_FILENAMES = {
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "composer.json",
    "go.mod",
}
_SOURCE_EXTENSIONS = {
    ".java",
    ".kt",
    ".kts",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".cs",
    ".go",
    ".rb",
    ".php",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
}
_UI_EXTENSIONS = {".html", ".htm", ".jsp", ".jspx", ".ftl", ".vue", ".svelte"}
_DOC_EXTENSIONS = {".md", ".txt", ".rst", ".adoc", ".ppt", ".pptx"}


class AnalysisContextBuilder:
    """Build the run-pinned canonical analysis context from a safe bundle."""

    def build(
        self,
        *,
        project_id: str,
        run_id: str,
        safe_bundle: SafeAnalysisBundle,
        goal: str = "",
        constraints: Iterable[str] | None = None,
        project_name: str = "",
        client_name: str = "",
        template_key: str = "",
        warnings: Iterable[str] | None = None,
        policy_versions: dict[str, str] | None = None,
    ) -> AnalysisContextBundle:
        project_id = (project_id or safe_bundle.project_id or "").strip()
        run_id = (run_id or "runless").strip()
        summaries_by_asset = {item.asset_id: item for item in safe_bundle.asset_summary}
        sources_by_asset = {source.asset_id: source for source in safe_bundle.sources}

        intent_file_contents: dict[str, str] = {}
        for source in safe_bundle.sources:
            summary = summaries_by_asset.get(source.asset_id)
            name = (summary.name if summary else source.asset_id).strip()
            lower_name = name.lower()
            if lower_name in _INTENT_FILENAMES:
                intent_file_contents[lower_name] = source.content or ""

        intent = self._build_intent(
            goal=goal,
            constraints=list(constraints or []),
            intent_file_contents=intent_file_contents,
        )

        source_blocks: list[AnalysisContextSourceBlock] = []
        assets: list[AnalysisContextAsset] = []
        for summary in sorted(safe_bundle.asset_summary, key=lambda item: (item.name.lower(), item.asset_id)):
            asset_name = summary.name or summary.asset_id
            asset_type = self._classify_asset(asset_name, summary.kind_hint, sources_by_asset.get(summary.asset_id))
            if asset_type == "intent":
                continue

            source = sources_by_asset.get(summary.asset_id)
            content = source.content if source else ""
            content_fingerprint = stable_hash(normalize_fingerprint_text(content))
            masking_level = self._masking_level(source.level if source else safe_bundle.masking_level)
            assets.append(
                AnalysisContextAsset(
                    asset_id=summary.asset_id,
                    name=asset_name,
                    asset_type=asset_type,
                    language=summary.language or (source.language if source else ""),
                    size=summary.size or len(content.encode("utf-8")),
                    content_fingerprint=content_fingerprint,
                    masking_level=masking_level,
                )
            )

            if source is None:
                continue
            block_fingerprint = stable_hash(normalize_fingerprint_text(content))
            block = AnalysisContextSourceBlock(
                block_id=make_stable_id("SRC", summary.asset_id, asset_name, block_fingerprint),
                asset_id=summary.asset_id,
                asset_name=asset_name,
                asset_type=asset_type,
                locator=asset_name,
                excerpt=self._excerpt(content),
                fingerprint=block_fingerprint,
                content=content,
            )
            source_blocks.append(block)

        source_blocks.sort(key=lambda item: (item.asset_name.lower(), item.asset_id, item.block_id))
        analysis_frame = self._estimate_analysis_frame(intent, source_blocks)
        evidence_index = self._build_evidence_index(source_blocks)
        input_fingerprint = self._input_fingerprint(
            project=AnalysisContextProject(
                project_id=project_id,
                project_name=project_name or "",
                client_name=client_name or "",
                template_key=template_key or "",
            ),
            intent=intent,
            assets=assets,
            source_blocks=source_blocks,
        )

        return AnalysisContextBundle(
            context_id=f"ctx_{project_id}_{run_id}",
            schema_version=SCHEMA_VERSION,
            project=AnalysisContextProject(
                project_id=project_id,
                project_name=project_name or "",
                client_name=client_name or "",
                template_key=template_key or "",
            ),
            intent=intent,
            assets=assets,
            source_blocks=source_blocks,
            analysis_frame=analysis_frame,
            evidence_index=evidence_index,
            trust=AnalysisTrust(
                safe_bundle_id=safe_bundle.bundle_id,
                masking_level=self._masking_level(safe_bundle.masking_level),
                missing_context=[],
                warnings=list(warnings or []),
            ),
            run=AnalysisRun(
                run_id=run_id,
                input_fingerprint=input_fingerprint,
                policy_versions=dict(policy_versions or {}),
            ),
            seed_structures=list(safe_bundle.structures or []),
        )

    def _build_intent(
        self,
        *,
        goal: str,
        constraints: list[str],
        intent_file_contents: dict[str, str],
    ) -> IntentInput:
        sources: dict[str, str] = {}
        normalized_goal = (goal or "").strip()
        if normalized_goal:
            sources["goal"] = "inline"
        if not normalized_goal and intent_file_contents.get("goal.txt"):
            normalized_goal = intent_file_contents["goal.txt"].strip()
            sources["goal"] = "goal.txt"
        elif intent_file_contents.get("goal.txt"):
            sources["goal"] = "inline|goal.txt"

        normalized_constraints = self._dedupe_preserve_order(
            [item.strip() for item in constraints if str(item or "").strip()]
        )
        if normalized_constraints:
            sources["constraints"] = "inline"
        file_constraints = self._split_constraints(intent_file_contents.get("constraints.txt", ""))
        if file_constraints:
            normalized_constraints = self._dedupe_preserve_order(normalized_constraints + file_constraints)
            sources["constraints"] = (
                "inline|constraints.txt" if sources.get("constraints") == "inline" else "constraints.txt"
            )

        scenario = intent_file_contents.get("scenario.md", "").strip()
        if scenario:
            sources["scenario"] = "scenario.md"

        return IntentInput(
            goal=normalized_goal,
            constraints=normalized_constraints,
            scenario=scenario,
            sources=sources,
        )

    def _input_fingerprint(
        self,
        *,
        project: AnalysisContextProject,
        intent: IntentInput,
        assets: list[AnalysisContextAsset],
        source_blocks: list[AnalysisContextSourceBlock],
    ) -> str:
        # input_fingerprint is calculated from normalized intent, stable asset identities,
        # ordered source block fingerprints, and schema_version via canonical serialization;
        # nondeterministic values such as created_at are excluded.
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project": {
                "project_id": project.project_id,
                "project_name": self._normalize_scalar(project.project_name),
                "client_name": self._normalize_scalar(project.client_name),
                "template_key": self._normalize_scalar(project.template_key),
            },
            "intent": {
                "goal": self._normalize_scalar(intent.goal),
                "constraints": sorted({self._normalize_scalar(item) for item in intent.constraints if item}),
                "scenario": self._normalize_scalar(intent.scenario),
            },
            "assets": [
                {
                    "asset_id": item.asset_id,
                    "name": self._normalize_scalar(item.name),
                    "asset_type": item.asset_type,
                    "language": self._normalize_scalar(item.language),
                    "size": item.size,
                    "content_fingerprint": item.content_fingerprint,
                    "masking_level": item.masking_level,
                }
                for item in sorted(assets, key=lambda asset: (asset.name.lower(), asset.asset_id))
            ],
            "source_block_fingerprints": [
                {
                    "block_id": item.block_id,
                    "asset_id": item.asset_id,
                    "locator": self._normalize_scalar(item.locator),
                    "fingerprint": item.fingerprint,
                }
                for item in sorted(source_blocks, key=lambda block: (block.asset_name.lower(), block.asset_id, block.block_id))
            ],
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha1(canonical.encode("utf-8")).hexdigest()

    def _build_evidence_index(
        self,
        source_blocks: list[AnalysisContextSourceBlock],
    ) -> list[AnalysisContextEvidenceItem]:
        evidence_items: list[AnalysisContextEvidenceItem] = []
        for block in source_blocks:
            if not block.excerpt:
                continue
            evidence_items.append(
                AnalysisContextEvidenceItem(
                    evidence_id=make_stable_id("EVID", block.block_id, block.fingerprint),
                    source_block_id=block.block_id,
                    asset_id=block.asset_id,
                    locator=block.locator,
                    excerpt=block.excerpt,
                    claim=f"Canonical source block observed for {block.asset_name or block.asset_id}",
                    claim_type="observed",
                )
            )
        return evidence_items

    def _estimate_analysis_frame(
        self,
        intent: IntentInput,
        source_blocks: list[AnalysisContextSourceBlock],
    ) -> AnalysisFrame:
        haystack = " ".join(
            [intent.goal, " ".join(intent.constraints), intent.scenario]
            + [block.excerpt for block in source_blocks[:8]]
        ).lower()
        mode_scores = {
            "save_validation": self._keyword_score(haystack, ["save", "validate", "validation", "required", "저장", "검증"]),
            "search_filters": self._keyword_score(haystack, ["search", "filter", "query", "where", "검색", "조회", "조건"]),
            "status_permissions": self._keyword_score(
                haystack,
                ["status", "approve", "reject", "permission", "role", "권한", "승인", "상태"],
            ),
        }
        primary_mode, score = max(mode_scores.items(), key=lambda item: item[1])
        if score <= 0:
            primary_mode = "general"
        concept_signals = [
            keyword
            for keyword in ["account", "order", "invoice", "approval", "search", "validation", "정산", "주문", "승인"]
            if keyword in haystack
        ]
        return AnalysisFrame(
            family="feature_modernization" if source_blocks else "",
            family_confidence=0.25 if source_blocks else 0.0,
            question_axis="implementation_evidence" if source_blocks else "",
            question_axis_confidence=0.25 if source_blocks else 0.0,
            primary_feature_mode=primary_mode,
            primary_feature_mode_confidence=min(0.55, score / 5) if score else 0.0,
            concept_signals=concept_signals,
            scope_limited=False,
        )

    def _classify_asset(self, name: str, kind_hint: str, source: object | None) -> str:
        lower_name = (name or "").lower()
        suffix = self._suffix(lower_name)
        hint = (kind_hint or "").lower()
        content = getattr(source, "content", "") or ""
        if lower_name in _INTENT_FILENAMES:
            return "intent"
        if lower_name in _FRAMEWORK_FILENAMES or any(token in lower_name for token in ["pom.xml", "gradle", "package.json"]):
            return "framework"
        if suffix in _UI_EXTENSIONS:
            return "ui"
        if suffix == ".sql":
            if "schema" in lower_name or re.search(r"\bcreate\s+table\b|\balter\s+table\b", content, flags=re.IGNORECASE):
                return "schema"
            return "sql"
        if "schema" in hint:
            return "schema"
        if "sql" in hint:
            return "sql"
        if suffix in _SOURCE_EXTENSIONS:
            return "source"
        if suffix == ".json":
            return "json"
        if any(token in hint for token in ("presentation", "slide", "deck")):
            return "doc"
        if suffix in _DOC_EXTENSIONS:
            return "doc"
        return hint or "other"

    @staticmethod
    def _suffix(name: str) -> str:
        if "." not in name:
            return ""
        return "." + name.rsplit(".", 1)[-1]

    @staticmethod
    def _excerpt(content: str, limit: int = 500) -> str:
        normalized = re.sub(r"\s+", " ", (content or "").strip())
        return normalized[:limit]

    @staticmethod
    def _split_constraints(content: str) -> list[str]:
        lines = [line.strip(" -\t") for line in (content or "").splitlines()]
        return [line for line in lines if line]

    @staticmethod
    def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for item in items:
            key = re.sub(r"\s+", " ", item.strip()).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item.strip())
        return deduped

    @staticmethod
    def _normalize_scalar(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip()).lower()

    @staticmethod
    def _keyword_score(text: str, keywords: Iterable[str]) -> int:
        return sum(1 for keyword in keywords if keyword in text)

    @staticmethod
    def _masking_level(value: object) -> str:
        if hasattr(value, "value"):
            return str(getattr(value, "value"))
        return str(value or "FULL")
