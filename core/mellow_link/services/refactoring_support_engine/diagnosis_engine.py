from __future__ import annotations

import difflib
import re
from collections import defaultdict
from typing import Any

from .policies import get_detector_policy, load_engine_policy_bundle
from .schemas import (
    CoverageSummary,
    DetectorStat,
    DiagnosisArtifacts,
    DiagnosisReport,
    EvidenceLink,
    StructuralIssue,
    StructureAnalysisResult,
    make_stable_id,
    normalize_fingerprint_text,
)


class _EvidenceStore:
    def __init__(self, structure: StructureAnalysisResult) -> None:
        self.structure = structure
        self._evidence: dict[str, EvidenceLink] = {}
        self._asset_by_id = {item.asset_id: item for item in structure.analysis_input.asset_inventory}
        self._block_by_asset = {block.asset_id: block for block in structure.analysis_input.source_blocks}

    @property
    def items(self) -> list[EvidenceLink]:
        return sorted(self._evidence.values(), key=lambda item: item.evidence_id)

    def add_for_component(self, component_id: str, excerpt: str, locator: str) -> str:
        asset_id = self.structure.component_asset_map.get(component_id, "")
        block = self._block_by_asset.get(asset_id)
        asset = self._asset_by_id.get(asset_id)
        fingerprint = normalize_fingerprint_text(excerpt)
        evidence_id = make_stable_id("EVID", asset_id, locator, fingerprint)
        if evidence_id not in self._evidence:
            self._evidence[evidence_id] = EvidenceLink(
                evidence_id=evidence_id,
                asset_id=asset_id,
                asset_name=asset.name if asset else asset_id,
                asset_type=asset.asset_type if asset else "unknown",
                locator=locator,
                excerpt=(excerpt or "")[:220],
                fingerprint=fingerprint,
            )
        return evidence_id


class DiagnosisEngine:
    DETECTOR_ORDER = (
        "mixed_responsibility",
        "ui_data_access_coupling",
        "rule_scatter",
        "duplicate_logic_candidate",
        "boundary_mismatch",
        "state_transition_leak",
        "validation_guard_leak",
        "query_filter_leak",
    )

    def __init__(self, policy_bundle=None) -> None:
        self.policy_bundle = policy_bundle or load_engine_policy_bundle()

    def run(self, prepared: Any, structure: StructureAnalysisResult, legacy_service: Any) -> DiagnosisArtifacts:
        evidence_store = _EvidenceStore(structure)
        issues: list[StructuralIssue] = []
        detector_evidence_ids: dict[str, set[str]] = defaultdict(set)
        for slice_id, component_ids in structure.slice_component_map.items():
            issues.extend(self._run_scope_detectors(structure, evidence_store, component_ids, slice_id=slice_id, detector_evidence_ids=detector_evidence_ids))
        issues.extend(
            self._run_scope_detectors(
                structure,
                evidence_store,
                [item.component_id for item in structure.structure_snapshot.components],
                slice_id="global",
                detector_evidence_ids=detector_evidence_ids,
            )
        )
        merged_issues: dict[str, StructuralIssue] = {}
        for item in issues:
            if not item.evidence_ids:
                continue
            current = merged_issues.get(item.issue_id)
            if current is None:
                merged_issues[item.issue_id] = item
                continue
            affected_slice_ids = sorted(set(current.affected_slice_ids) | set(item.affected_slice_ids))
            if len(affected_slice_ids) > 1 and "global" in affected_slice_ids:
                affected_slice_ids = [slice_id for slice_id in affected_slice_ids if slice_id != "global"]
            merged_issues[item.issue_id] = current.model_copy(
                update={
                    "severity": max(current.severity, item.severity),
                    "blast_radius": max(current.blast_radius, item.blast_radius),
                    "effort": max(current.effort, item.effort),
                    "affected_component_ids": sorted(set(current.affected_component_ids) | set(item.affected_component_ids)),
                    "affected_slice_ids": affected_slice_ids,
                    "evidence_ids": sorted(set(current.evidence_ids) | set(item.evidence_ids)),
                    "confidence": round(max(current.confidence, item.confidence), 2),
                }
            )
        final_issues = sorted(merged_issues.values(), key=lambda item: (-item.severity, -item.blast_radius, item.issue_id))
        detector_stats = [
            DetectorStat(
                detector_id=detector_id,
                issue_count=sum(1 for item in final_issues if item.detector_id == detector_id),
                evidence_count=len(detector_evidence_ids.get(detector_id, set())),
            )
            for detector_id in self.DETECTOR_ORDER
        ]
        diagnosis_report = DiagnosisReport(
            issues=final_issues,
            coverage_summary=CoverageSummary.model_validate(structure.structure_snapshot.coverage_summary.model_dump()),
            detector_stats=detector_stats,
        )

        extracted_rules = legacy_service.extract_rules(prepared)
        missing_context_details = legacy_service.build_missing_context_details(prepared)
        core_business_rules = legacy_service.extract_core_business_rules(prepared)
        grounded_business_rules = legacy_service.build_grounded_business_rules(prepared, core_business_rules)
        retained_contracts = legacy_service.build_retained_contracts(prepared, grounded_business_rules)
        analysis_summary = legacy_service.analyze_assets(prepared)
        return DiagnosisArtifacts(
            diagnosis_report=diagnosis_report,
            evidence_index=evidence_store.items,
            extracted_rules=extracted_rules,
            missing_context_details=missing_context_details,
            core_business_rules=core_business_rules,
            grounded_business_rules=grounded_business_rules,
            retained_contracts=retained_contracts,
            analysis_summary=analysis_summary,
        )

    def _run_scope_detectors(
        self,
        structure: StructureAnalysisResult,
        evidence_store: _EvidenceStore,
        component_ids: list[str],
        *,
        slice_id: str,
        detector_evidence_ids: dict[str, set[str]],
    ) -> list[StructuralIssue]:
        issues: list[StructuralIssue] = []
        for detector_id in self.DETECTOR_ORDER:
            if not self._policy_for(detector_id).enabled:
                continue
            method = getattr(self, f"_detect_{detector_id}")
            detected = method(structure, evidence_store, component_ids, slice_id=slice_id)
            for item in detected:
                detector_evidence_ids[detector_id].update(item.evidence_ids)
            issues.extend(detected)
        return issues

    def _detect_mixed_responsibility(self, structure: StructureAnalysisResult, evidence_store: _EvidenceStore, component_ids: list[str], *, slice_id: str) -> list[StructuralIssue]:
        issues: list[StructuralIssue] = []
        for component_id in component_ids:
            families = structure.component_responsibility_map.get(component_id, [])
            layer = structure.component_layer_map.get(component_id, "")
            if not self._is_mixed_responsibility_candidate(layer, families):
                continue
            excerpt = self._component_excerpt(structure.component_text_map.get(component_id, ""), keywords=families)
            evidence_id = evidence_store.add_for_component(component_id, excerpt, f"{component_id}:mixed_responsibility")
            issues.append(
                self._build_issue(
                    detector_id="mixed_responsibility",
                    summary=f"{structure.component_name_map.get(component_id, component_id)} contains {', '.join(families[:3])} responsibilities",
                    component_ids=[component_id],
                    slice_ids=[slice_id],
                    evidence_ids=[evidence_id],
                    layer_map=structure.component_layer_map,
                    text=structure.component_text_map.get(component_id, ""),
                )
            )
        return issues

    def _detect_ui_data_access_coupling(self, structure: StructureAnalysisResult, evidence_store: _EvidenceStore, component_ids: list[str], *, slice_id: str) -> list[StructuralIssue]:
        issues: list[StructuralIssue] = []
        for component_id in component_ids:
            if structure.component_layer_map.get(component_id) != "ui":
                continue
            text = structure.component_text_map.get(component_id, "")
            has_sql = bool(re.search(r"\b(select\s+.+\s+from|insert\s+into|update\s+[a-z_][a-z0-9_]*\s+set|delete\s+from)\b", text, flags=re.IGNORECASE | re.DOTALL))
            has_repo_call = bool(re.search(r"\b(?:repository|repo|dao)\w*\s*(?:\.|\()|\b(?:db|session)\s*\.", text, flags=re.IGNORECASE))
            dependency_targets = [
                edge.to_component
                for edge in structure.structure_snapshot.dependencies
                if edge.from_component == component_id and structure.component_layer_map.get(edge.to_component, "") in {"repository", "data"}
            ]
            if not (has_sql or has_repo_call or dependency_targets):
                continue
            excerpt = self._component_excerpt(text, keywords=["select", "repository", "repo", "db", "session"])
            locator = f"{component_id}:ui_data_access"
            if dependency_targets:
                locator = f"{locator}:{dependency_targets[0]}"
            evidence_id = evidence_store.add_for_component(component_id, excerpt, locator)
            issues.append(
                self._build_issue(
                    detector_id="ui_data_access_coupling",
                    summary=f"{structure.component_name_map.get(component_id, component_id)} directly couples UI flow to persistence access",
                    component_ids=[component_id],
                    slice_ids=[slice_id],
                    evidence_ids=[evidence_id],
                    layer_map=structure.component_layer_map,
                    text=text,
                )
            )
        return issues

    def _detect_rule_scatter(self, structure: StructureAnalysisResult, evidence_store: _EvidenceStore, component_ids: list[str], *, slice_id: str) -> list[StructuralIssue]:
        return self._detect_repeated_predicates(
            structure,
            evidence_store,
            component_ids,
            slice_id=slice_id,
            detector_id="rule_scatter",
            summary_template="Repeated business predicate appears in multiple locations",
            extractor=self._condition_occurrences,
            minimum_tokens=4,
            require_operator=True,
        )

    def _detect_duplicate_logic_candidate(self, structure: StructureAnalysisResult, evidence_store: _EvidenceStore, component_ids: list[str], *, slice_id: str) -> list[StructuralIssue]:
        issues: list[StructuralIssue] = []
        seen_pairs: set[tuple[str, str]] = set()
        texts = {component_id: self._logic_tokens(structure.component_text_map.get(component_id, "")) for component_id in component_ids}
        for left_id in component_ids:
            for right_id in component_ids:
                if left_id >= right_id:
                    continue
                key = (left_id, right_id)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                left_text = texts.get(left_id, "")
                right_text = texts.get(right_id, "")
                if len(left_text) < 10 or len(right_text) < 10:
                    continue
                similarity = difflib.SequenceMatcher(None, left_text, right_text).ratio()
                shared_tokens = len(set(left_text) & set(right_text))
                overlap = shared_tokens / max(1, min(len(set(left_text)), len(set(right_text))))
                if similarity < 0.82 or overlap < 0.7 or shared_tokens < 6:
                    continue
                evidence_ids = [
                    evidence_store.add_for_component(left_id, self._component_excerpt(structure.component_text_map.get(left_id, "")), f"{left_id}:duplicate_logic"),
                    evidence_store.add_for_component(right_id, self._component_excerpt(structure.component_text_map.get(right_id, "")), f"{right_id}:duplicate_logic"),
                ]
                issues.append(
                    self._build_issue(
                        detector_id="duplicate_logic_candidate",
                        summary=f"{structure.component_name_map.get(left_id, left_id)} and {structure.component_name_map.get(right_id, right_id)} share highly similar logic",
                        component_ids=[left_id, right_id],
                        slice_ids=[slice_id],
                        evidence_ids=evidence_ids,
                        layer_map=structure.component_layer_map,
                        text=f"{structure.component_text_map.get(left_id, '')}\n{structure.component_text_map.get(right_id, '')}",
                    )
                )
        return issues

    def _detect_boundary_mismatch(self, structure: StructureAnalysisResult, evidence_store: _EvidenceStore, component_ids: list[str], *, slice_id: str) -> list[StructuralIssue]:
        issues: list[StructuralIssue] = []
        forbidden_edges = {
            ("service", "ui"),
            ("ui", "repository"),
            ("ui", "data"),
            ("repository", "service"),
            ("repository", "ui"),
        }
        for edge in structure.structure_snapshot.dependencies:
            if edge.from_component not in component_ids or edge.to_component not in component_ids:
                continue
            from_layer = structure.component_layer_map.get(edge.from_component, "")
            to_layer = structure.component_layer_map.get(edge.to_component, "")
            repo_business = to_layer == "repository" and "business" in structure.component_responsibility_map.get(edge.to_component, [])
            ui_business = from_layer == "ui" and {"business", "persistence"} & set(structure.component_responsibility_map.get(edge.from_component, []))
            if (from_layer, to_layer) not in forbidden_edges and not (repo_business or ui_business):
                continue
            if edge.dependency_type == "references" and not (repo_business or ui_business or (from_layer, to_layer) == ("ui", "data")):
                continue
            excerpt = self._component_excerpt(structure.component_text_map.get(edge.from_component, ""), keywords=[structure.component_name_map.get(edge.to_component, "")])
            evidence_id = evidence_store.add_for_component(edge.from_component, excerpt, f"{edge.from_component}:boundary_mismatch:{edge.to_component}")
            issues.append(
                self._build_issue(
                    detector_id="boundary_mismatch",
                    summary=f"Layer boundary mismatch detected on {from_layer}->{to_layer} dependency",
                    component_ids=[edge.from_component, edge.to_component],
                    slice_ids=[slice_id],
                    evidence_ids=[evidence_id],
                    layer_map=structure.component_layer_map,
                    text=f"{structure.component_text_map.get(edge.from_component, '')}\n{structure.component_text_map.get(edge.to_component, '')}",
                )
            )
        return issues

    def _detect_state_transition_leak(self, structure: StructureAnalysisResult, evidence_store: _EvidenceStore, component_ids: list[str], *, slice_id: str) -> list[StructuralIssue]:
        return self._detect_repeated_predicates(
            structure,
            evidence_store,
            component_ids,
            slice_id=slice_id,
            detector_id="state_transition_leak",
            summary_template="State transition logic appears in multiple locations",
            extractor=self._state_transition_occurrences,
            minimum_tokens=4,
        )

    def _detect_validation_guard_leak(self, structure: StructureAnalysisResult, evidence_store: _EvidenceStore, component_ids: list[str], *, slice_id: str) -> list[StructuralIssue]:
        return self._detect_repeated_predicates(
            structure,
            evidence_store,
            component_ids,
            slice_id=slice_id,
            detector_id="validation_guard_leak",
            summary_template="Validation guard logic is distributed across layers",
            extractor=self._validation_occurrences,
            minimum_tokens=4,
            minimum_layers=2,
        )

    def _detect_query_filter_leak(self, structure: StructureAnalysisResult, evidence_store: _EvidenceStore, component_ids: list[str], *, slice_id: str) -> list[StructuralIssue]:
        return self._detect_repeated_predicates(
            structure,
            evidence_store,
            component_ids,
            slice_id=slice_id,
            detector_id="query_filter_leak",
            summary_template="Query filter predicates repeat across multiple queries",
            extractor=self._query_occurrences,
            minimum_tokens=4,
            require_operator=True,
        )

    def _detect_repeated_predicates(
        self,
        structure: StructureAnalysisResult,
        evidence_store: _EvidenceStore,
        component_ids: list[str],
        *,
        slice_id: str,
        detector_id: str,
        summary_template: str,
        extractor,
        minimum_tokens: int = 3,
        minimum_layers: int = 1,
        require_operator: bool = False,
    ) -> list[StructuralIssue]:
        occurrences: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        issues: list[StructuralIssue] = []
        for component_id in component_ids:
            text = structure.component_text_map.get(component_id, "")
            for raw_expr, locator, excerpt in extractor(text):
                fingerprint = normalize_fingerprint_text(raw_expr)
                if not self._is_meaningful_predicate(fingerprint, minimum_tokens=minimum_tokens, require_operator=require_operator):
                    continue
                occurrences[fingerprint].append((component_id, locator, excerpt))
        for fingerprint, matches in occurrences.items():
            unique_components = list(dict.fromkeys(component_id for component_id, _, _ in matches))
            if len(unique_components) < 2:
                continue
            unique_layers = {
                structure.component_layer_map.get(component_id, "")
                for component_id in unique_components
                if structure.component_layer_map.get(component_id, "")
            }
            if len(unique_layers) < minimum_layers:
                continue
            evidence_ids = [
                evidence_store.add_for_component(component_id, excerpt, locator)
                for component_id, locator, excerpt in matches[:3]
            ]
            issues.append(
                self._build_issue(
                    detector_id=detector_id,
                    summary=summary_template,
                    component_ids=unique_components,
                    slice_ids=[slice_id],
                    evidence_ids=evidence_ids,
                    layer_map=structure.component_layer_map,
                    text="\n".join(structure.component_text_map.get(component_id, "") for component_id in unique_components),
                )
            )
        return issues

    def _condition_occurrences(self, text: str) -> list[tuple[str, str, str]]:
        occurrences: list[tuple[str, str, str]] = []
        for index, line in enumerate((text or "").splitlines(), start=1):
            stripped = line.strip()
            if stripped.lower().startswith("if ") or stripped.lower().startswith("elif "):
                occurrences.append((stripped, f"line:{index}", stripped[:180]))
        return occurrences

    def _state_transition_occurrences(self, text: str) -> list[tuple[str, str, str]]:
        occurrences: list[tuple[str, str, str]] = []
        for index, line in enumerate((text or "").splitlines(), start=1):
            stripped = line.strip()
            lowered = stripped.lower()
            if "status" not in lowered and "state" not in lowered:
                continue
            if any(token in lowered for token in ("=", "setstatus", "set_state", "update", "transition", "전이", "상태 변경")):
                occurrences.append((stripped, f"line:{index}", stripped[:180]))
        return occurrences

    def _validation_occurrences(self, text: str) -> list[tuple[str, str, str]]:
        occurrences: list[tuple[str, str, str]] = []
        for index, line in enumerate((text or "").splitlines(), start=1):
            stripped = line.strip()
            lowered = stripped.lower()
            if any(token in lowered for token in ("validate", "required", "duplicate", "invalid", "null", "blank", "필수", "중복", "검증")):
                occurrences.append((stripped, f"line:{index}", stripped[:180]))
        return occurrences

    def _query_occurrences(self, text: str) -> list[tuple[str, str, str]]:
        occurrences: list[tuple[str, str, str]] = []
        for index, line in enumerate((text or "").splitlines(), start=1):
            stripped = line.strip()
            lowered = stripped.lower()
            if re.search(r"\bwhere\b", lowered):
                parts = re.split(r"\bwhere\b", lowered, maxsplit=1)
                if len(parts) < 2:
                    continue
                predicate = parts[1]
                predicate = re.split(r"\border\s+by\b", predicate, maxsplit=1)[0]
                occurrences.append((predicate, f"line:{index}", stripped[:180]))
        return occurrences

    def _is_mixed_responsibility_candidate(self, layer: str, families: list[str]) -> bool:
        family_set = set(families)
        if len(family_set) >= 3:
            return True
        if {"validation", "business"} <= family_set:
            return True
        if "persistence" in family_set and family_set & {"validation", "business", "ui_orchestration"}:
            return True
        if layer == "ui" and "persistence" in family_set:
            return True
        if layer == "repository" and "business" in family_set:
            return True
        return False

    def _logic_tokens(self, text: str) -> list[str]:
        normalized = normalize_fingerprint_text(text)
        tokens = re.findall(r"[a-z_]+", normalized)
        stop_words = {
            "def",
            "class",
            "return",
            "self",
            "true",
            "false",
            "none",
            "str",
            "num",
            "pass",
            "public",
            "private",
            "protected",
        }
        return [token for token in tokens if len(token) >= 3 and token not in stop_words]

    def _is_meaningful_predicate(self, fingerprint: str, *, minimum_tokens: int, require_operator: bool) -> bool:
        trimmed = fingerprint.rstrip(":")
        if len(trimmed.split()) < minimum_tokens:
            return False
        if re.fullmatch(r"(if|elif)\s+not\s+[a-z_][a-z0-9_]*", trimmed):
            return False
        if re.fullmatch(r"[a-z_][a-z0-9_]*\s*(=|==)\s*(str|num)", trimmed):
            return False
        if require_operator and not re.search(r"(==|!=|<=|>=|<|>|\band\b|\bor\b|\bin\b)", trimmed):
            return False
        return True

    def _component_excerpt(self, text: str, keywords: list[str] | None = None) -> str:
        normalized_keywords = [keyword for keyword in (keywords or []) if keyword]
        for line in (text or "").splitlines():
            lowered = line.lower()
            if normalized_keywords and any(keyword.lower() in lowered for keyword in normalized_keywords):
                return line.strip()[:180]
        return (text or "").strip().splitlines()[0][:180] if (text or "").strip() else ""

    def _build_issue(
        self,
        *,
        detector_id: str,
        summary: str,
        component_ids: list[str],
        slice_ids: list[str],
        evidence_ids: list[str],
        layer_map: dict[str, str],
        text: str,
    ) -> StructuralIssue:
        policy = self._policy_for(detector_id)
        layers = {layer_map.get(component_id, "") for component_id in component_ids if layer_map.get(component_id, "")}
        severity = policy.base_severity
        if policy.allow_cross_layer_bonus and len(layers) >= 2:
            severity += 1
        lowered = (text or "").lower()
        if policy.allow_write_path_bonus and any(token in lowered for token in ("insert", "update", "delete", "approve", "reject", "status", "state", "승인", "상태")):
            severity += 1
        severity = min(5, severity)
        blast_radius = self._blast_radius(component_ids, slice_ids, layers)
        confidence = round(
            min(
                0.95,
                0.55
                + (0.08 * len(evidence_ids))
                + (0.05 if len(layers) >= 2 else 0.0)
                + (0.04 if len(set(slice_ids)) >= 2 else 0.0),
            ),
            2,
        )
        return StructuralIssue(
            issue_id=make_stable_id("ISSUE", detector_id, sorted(component_ids), summary, sorted(evidence_ids)),
            detector_id=detector_id,
            category=policy.category,
            severity=severity,
            blast_radius=blast_radius,
            effort=policy.default_effort,
            summary=summary,
            affected_component_ids=sorted(component_ids),
            affected_slice_ids=sorted(slice_ids),
            evidence_ids=sorted(dict.fromkeys(evidence_ids)),
            confidence=confidence,
        )

    def _policy_for(self, detector_id: str):
        return get_detector_policy(detector_id, self.policy_bundle)

    def _blast_radius(self, component_ids: list[str], slice_ids: list[str], layers: set[str]) -> int:
        score = len(set(component_ids)) + len(set(slice_ids)) + len(layers)
        if score <= 1:
            return 1
        if score <= 3:
            return 2
        if score <= 5:
            return 3
        if score <= 7:
            return 4
        return 5
