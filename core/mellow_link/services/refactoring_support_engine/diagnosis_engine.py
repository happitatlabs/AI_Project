from __future__ import annotations

import difflib
import re
from collections import defaultdict
from typing import Any

from mellow_link.modules.rebuild_assistant.schemas import (
    ExtractedRulesEnvelope,
    SaveValidationRules,
    SearchFilterRules,
    StatusPermissionsRules,
)

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

        extracted_rules = self.build_extracted_rules(prepared)
        missing_context_details = legacy_service.build_missing_context_details(prepared)
        core_business_rules = legacy_service.extract_core_business_rules(prepared)
        grounded_business_rules = legacy_service.build_grounded_business_rules(prepared, core_business_rules)
        retained_contracts = legacy_service.build_retained_contracts(prepared, grounded_business_rules)
        analysis_summary = self.build_analysis_summary(prepared)
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

    def build_analysis_summary(self, prepared: Any) -> list[str]:
        findings: list[str] = []
        primary_label = self._feature_mode_label(str(getattr(getattr(prepared, "signals", None), "primary_feature_mode", "") or ""))
        if self._looks_like_jsp(prepared):
            findings.append("JSP/서버 템플릿 기반 UI로 추정되며 프레젠테이션과 서버 책임이 섞여 있습니다.")
        if self._contains_sql_in_ui(prepared):
            findings.append("SQL 또는 데이터 접근 로직이 UI/템플릿과 가깝게 결합되어 있습니다.")
        findings.append(f"대표 도메인 범위는 {self._primary_concept(prepared)} 중심으로 정리하는 편이 적절합니다.")
        status_permissions = list(getattr(getattr(prepared, "signals", None), "status_permissions", []) or [])
        search_filters = list(getattr(getattr(prepared, "signals", None), "search_filters", []) or [])
        save_validation = list(getattr(getattr(prepared, "signals", None), "save_validation", []) or [])
        if status_permissions:
            findings.append(
                "권한 및 상태 규칙 신호가 보여 역할/상태/가능 액션 표시가 화면 분기와 섞여 있으며 정책 추출이 필요합니다: "
                + ", ".join(status_permissions[:3])
            )
        if search_filters:
            findings.append(
                "조회 조건 규칙 신호가 보여 조회 조건, 검색 파라미터, 동적 쿼리 조합이 한 흐름에 묶여 있습니다: "
                + ", ".join(search_filters[:3])
            )
        if save_validation:
            findings.append(
                "저장 검증 규칙 신호가 보여 저장 전 검증, 중복 체크, 저장 가드가 화면/서비스 경계 없이 퍼져 있습니다: "
                + ", ".join(save_validation[:3])
            )
        asset_presence = getattr(prepared, "asset_presence", None)
        assets = getattr(prepared, "assets", None)
        has_schema = bool(getattr(asset_presence, "has_schema_asset", False)) or bool(getattr(assets, "database_schema", ""))
        if has_schema:
            findings.append("기존 스키마 호환성을 유지해야 하므로 API/백엔드 분리 시 DB 계약을 우선 보존해야 합니다.")
        if primary_label != "일반 기능":
            findings.append(f"우선 분해 대상은 {primary_label}이며, 나머지 규칙은 보조 흐름으로 정리하는 편이 적절합니다.")
        if not findings:
            findings.append("제공된 자산 범위에서는 단일 기능 수준의 레거시 웹 화면과 데이터 접근 계층이 함께 얽혀 있는 것으로 보입니다.")
        return findings[:6]

    def build_extracted_rules(self, prepared: Any) -> ExtractedRulesEnvelope:
        primary = str(getattr(getattr(prepared, "signals", None), "primary_feature_mode", "") or "")
        secondary = getattr(getattr(prepared, "signals", None), "secondary_feature_mode", None)
        envelope = ExtractedRulesEnvelope()
        if primary == "status_permissions":
            envelope.status_permissions = self._extract_status_permissions_rules(prepared)
        elif primary == "search_filters":
            envelope.search_filters = self._extract_search_filter_rules(prepared)
        elif primary == "save_validation":
            envelope.save_validation = self._extract_save_validation_rules(prepared)

        if secondary == "status_permissions" and primary != "status_permissions":
            envelope.status_permissions = self._extract_status_permissions_rules(prepared, supplemental=True)
        elif secondary == "search_filters" and primary != "search_filters":
            envelope.search_filters = self._extract_search_filter_rules(prepared, supplemental=True)
        elif secondary == "save_validation" and primary != "save_validation":
            envelope.save_validation = self._extract_save_validation_rules(prepared, supplemental=True)
        return envelope

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

    def _extract_status_permissions_rules(
        self,
        prepared: Any,
        supplemental: bool = False,
    ) -> StatusPermissionsRules:
        text = str(getattr(prepared, "legacy_bundle", "") or "")
        roles = [role.upper() for role in self._extract_unique_matches(text, r"\b(admin|manager|user|operator|guest|owner|reviewer|approver)\b")]
        statuses = [status.upper() for status in self._extract_unique_matches(text, r"\b(pending|approved|rejected|draft|submitted|active|inactive|closed|cancelled)\b")]
        actions = self._extract_unique_matches(text, r"\b(approve|reject|resubmit|cancel|submit|close|reopen)\b")
        entities = self._rule_entities(prepared)

        role_action_matrix: list[dict] = []
        for role in roles:
            allowed_actions = [action for action in actions if re.search(rf"{role}.*{action}|{action}.*{role}", text, flags=re.IGNORECASE)]
            if allowed_actions:
                role_action_matrix.append({"role": role, "allowed_actions": self._dedupe_list(allowed_actions)})

        status_action_matrix: list[dict] = []
        for status in statuses:
            visible_actions = [action for action in actions if re.search(rf"{status}.*{action}|{action}.*{status}", text, flags=re.IGNORECASE)]
            if visible_actions:
                status_action_matrix.append({"status": status, "visible_actions": self._dedupe_list(visible_actions)})

        transition_rules: list[dict] = []
        for status in statuses:
            for action in actions:
                if not re.search(rf"{status}.*{action}|{action}.*{status}", text, flags=re.IGNORECASE):
                    continue
                transition_rules.append(
                    {
                        "from_status": status,
                        "action": action,
                        "to_status": self._infer_target_status(action, statuses),
                        "condition": self._transition_condition_hint(text, roles, status, action),
                    }
                )

        ui_visibility_rules: list[str] = []
        if actions and statuses:
            for action in actions[:3]:
                related_statuses = [
                    status for status in statuses if re.search(rf"{status}.*{action}|{action}.*{status}", text, flags=re.IGNORECASE)
                ]
                related_roles = [
                    role for role in roles if re.search(rf"{role}.*{action}|{action}.*{role}", text, flags=re.IGNORECASE)
                ]
                if related_statuses or related_roles:
                    role_fragment = f" and role is {' or '.join(related_roles)}" if related_roles else ""
                    status_fragment = f"when status is {' or '.join(related_statuses)}" if related_statuses else "when action state is satisfied"
                    ui_visibility_rules.append(f"show {action} button only {status_fragment}{role_fragment}".strip())
        if not ui_visibility_rules and re.search(r"<c:if|<c:choose|if\s*\(", text, flags=re.IGNORECASE):
            ui_visibility_rules.append("conditional action visibility is embedded in JSP or server-side branches")

        policy_hints: list[str] = []
        if roles or actions or statuses:
            policy_hints.append("extract role/action visibility into policy service")
        if transition_rules:
            policy_hints.append("extract state transition checks into transition policy")
        if re.search(r"<c:if|<c:choose|if\s*\(", text, flags=re.IGNORECASE):
            policy_hints.append("move conditional button rendering rules out of the view layer")

        if supplemental:
            role_action_matrix = role_action_matrix[:1]
            status_action_matrix = status_action_matrix[:1]
            transition_rules = transition_rules[:1]
            ui_visibility_rules = ui_visibility_rules[:1]
            policy_hints = policy_hints[:1]

        return StatusPermissionsRules(
            entities=entities,
            roles=roles,
            statuses=statuses,
            actions=actions,
            role_action_matrix=role_action_matrix,
            status_action_matrix=status_action_matrix,
            transition_rules=self._dedupe_dicts(transition_rules),
            ui_visibility_rules=self._dedupe_list(ui_visibility_rules),
            policy_hints=self._dedupe_list(policy_hints),
        )

    def _extract_search_filter_rules(
        self,
        prepared: Any,
        supplemental: bool = False,
    ) -> SearchFilterRules:
        text = str(getattr(prepared, "legacy_bundle", "") or "")
        entities = self._rule_entities(prepared)
        query_params = self._extract_unique_matches(
            text,
            r"request\.getParameter\(\"([^\"]+)\"\)|@RequestParam\(\"([^\"]+)\"\)|\b(keyword|status|page|sort|dateFrom|dateTo|category|region|includeClosed|filter)\b",
        )

        filter_fields: list[dict] = []
        for name in query_params:
            filter_fields.append({"name": name, "type": self._infer_filter_field_type(name), "required": False})

        sort_rules: list[dict] = []
        assets = getattr(prepared, "assets", None)
        sql_text = str(getattr(assets, "sql_queries", "") or text)
        order_match = re.search(r"order\s+by\s+([a-z0-9_\.]+)(?:\s+(asc|desc))?", sql_text, flags=re.IGNORECASE)
        if order_match:
            sort_rules.append(
                {
                    "field": order_match.group(1).split(".")[-1],
                    "direction": (order_match.group(2) or "asc").lower(),
                    "default": True,
                }
            )

        paging_rules: list[dict] = []
        if re.search(r"\blimit\b", sql_text, flags=re.IGNORECASE):
            paging_rules.append({"param": "limit", "style": "limit", "default": False})
        if re.search(r"\boffset\b", sql_text, flags=re.IGNORECASE):
            paging_rules.append({"param": "offset", "style": "offset", "default": False})
        if any(param.lower() == "page" for param in query_params):
            paging_rules.append({"param": "page", "style": "page", "default": False})

        query_binding_rules: list[str] = []
        if query_params:
            query_binding_rules.append(f"use bound params for {', '.join(query_params[:4])} filters")
        if re.search(r"\bwhere\b", sql_text, flags=re.IGNORECASE):
            query_binding_rules.append("avoid string concatenation in WHERE clause")
        if re.search(r"\blike\b", sql_text, flags=re.IGNORECASE):
            query_binding_rules.append("parameterize LIKE predicates instead of inline SQL composition")

        default_filters: list[str] = []
        if any(param.lower() == "status" for param in query_params):
            default_filters.append("preserve default status filter behavior from the legacy search form")
        if re.search(r"includeClosed|closed", text, flags=re.IGNORECASE):
            default_filters.append("exclude CLOSED unless includeClosed is explicitly enabled")

        result_shape_hints: list[str] = []
        columns = self._extract_select_columns(sql_text)
        if columns:
            result_shape_hints.append(f"list result with {', '.join(columns[:4])}")
        elif re.search(r"\b(table|grid|list|results?)\b", text, flags=re.IGNORECASE):
            result_shape_hints.append("list result shape is rendered as a table/grid in the legacy view")

        if supplemental:
            filter_fields = filter_fields[:2]
            sort_rules = sort_rules[:1]
            paging_rules = paging_rules[:1]
            query_binding_rules = query_binding_rules[:1]
            default_filters = default_filters[:1]
            result_shape_hints = result_shape_hints[:1]

        return SearchFilterRules(
            entities=entities,
            filter_fields=filter_fields,
            query_params=query_params,
            sort_rules=sort_rules,
            paging_rules=paging_rules,
            query_binding_rules=self._dedupe_list(query_binding_rules),
            default_filters=self._dedupe_list(default_filters),
            result_shape_hints=self._dedupe_list(result_shape_hints),
        )

    def _extract_save_validation_rules(
        self,
        prepared: Any,
        supplemental: bool = False,
    ) -> SaveValidationRules:
        text = str(getattr(prepared, "legacy_bundle", "") or "")
        entities = self._rule_entities(prepared)
        required_fields = self._extract_unique_matches(
            text,
            r"if\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*==\s*null|([a-zA-Z_][a-zA-Z0-9_]*)\.isBlank\(\)|required\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        )
        field_validation_rules: list[str] = []
        for field in required_fields:
            field_validation_rules.append(f"{field} must not be empty")
        if re.search(r"validate|validator", text, flags=re.IGNORECASE):
            field_validation_rules.append("legacy save flow includes validator-style checks before persistence")

        duplicate_check_rules: list[str] = []
        duplicate_fields = self._extract_unique_matches(text, r"existsBy([A-Z][a-zA-Z0-9_]*)|duplicate\s+([a-zA-Z_][a-zA-Z0-9_]*)")
        for field in duplicate_fields:
            normalized = re.sub(r"([a-z])([A-Z])", r"\1 \2", field).replace("_", " ").lower()
            duplicate_check_rules.append(f"prevent duplicate records by {normalized}")
        if not duplicate_check_rules and re.search(r"\b(duplicate|exists|already exists|unique|중복)\b", text, flags=re.IGNORECASE):
            duplicate_check_rules.append("prevent duplicate records before save")

        save_guard_rules: list[str] = []
        if re.search(r"\b(forbidden|cannot save|blocked|guard)\b", text, flags=re.IGNORECASE):
            save_guard_rules.append("apply pre-save guard before persistence")
        if re.search(r"\b(save|insert|update|submit|persist)\b", text, flags=re.IGNORECASE) and (
            required_fields or duplicate_check_rules or re.search(r"throw\s+new", text, flags=re.IGNORECASE)
        ):
            save_guard_rules.append("run validation and duplicate guards before persistence")
        if re.search(r"\b(role|admin|manager)\b", text, flags=re.IGNORECASE) and re.search(r"\b(save|insert|update|submit)\b", text, flags=re.IGNORECASE):
            save_guard_rules.append("enforce role-based save restrictions before save")
        if re.search(r"\b(status|state|pending|approved|closed|draft)\b", text, flags=re.IGNORECASE) and re.search(r"\b(save|update|submit)\b", text, flags=re.IGNORECASE):
            save_guard_rules.append("enforce status-change restrictions before save")

        exception_rules = self._extract_unique_matches(
            text,
            r"throw\s+new\s+([A-Za-z]+Exception)|\b(IllegalStateException|ValidationException|SecurityException|IllegalArgumentException)\b",
        )
        exception_rules = [f"raise {rule}" for rule in exception_rules]

        command_boundary_hints: list[str] = []
        if required_fields or duplicate_check_rules or save_guard_rules:
            command_boundary_hints.append("split validation from persistence")
            command_boundary_hints.append("use command DTO and validator")
        if exception_rules:
            command_boundary_hints.append("normalize save-time exceptions into explicit validation results")

        if supplemental:
            field_validation_rules = field_validation_rules[:2]
            duplicate_check_rules = duplicate_check_rules[:1]
            save_guard_rules = save_guard_rules[:1]
            exception_rules = exception_rules[:1]
            command_boundary_hints = command_boundary_hints[:1]

        return SaveValidationRules(
            entities=entities,
            required_fields=required_fields,
            field_validation_rules=self._dedupe_list(field_validation_rules),
            duplicate_check_rules=self._dedupe_list(duplicate_check_rules),
            save_guard_rules=self._dedupe_list(save_guard_rules),
            exception_rules=self._dedupe_list(exception_rules),
            command_boundary_hints=self._dedupe_list(command_boundary_hints),
        )

    def _primary_concept(self, prepared: Any) -> str:
        concepts = list(getattr(getattr(prepared, "signals", None), "concepts", []) or [])
        if concepts:
            return str(concepts[0] or "").strip() or "legacy"
        assets = getattr(prepared, "assets", None)
        asset_presence = getattr(prepared, "asset_presence", None)
        evidence_text = " ".join(
            [
                " ".join(list(getattr(asset_presence, "source_asset_names", []) or [])),
                " ".join(list(getattr(asset_presence, "ui_asset_names", []) or [])),
                " ".join(list(getattr(asset_presence, "schema_asset_names", []) or [])),
                " ".join(list(getattr(asset_presence, "sql_asset_names", []) or [])),
                str(getattr(assets, "source_code", "") or ""),
                str(getattr(assets, "ui_template", "") or ""),
                str(getattr(assets, "sql_queries", "") or ""),
                str(getattr(assets, "database_schema", "") or ""),
                str(getattr(prepared, "supporting_docs", "") or ""),
            ]
        )
        normalized = re.sub(r"[^A-Za-z0-9가-힣\s]+", " ", evidence_text).strip()
        tokens = [token for token in normalized.split() if token.lower() not in {"modernize", "legacy", "flow", "feature", "현대화"}]
        return " ".join(tokens[:2]) or "legacy"

    def _rule_entities(self, prepared: Any) -> list[str]:
        concept = self._primary_concept(prepared)
        normalized = re.sub(r"[^a-z0-9]+", "_", concept.lower()).strip("_")
        return [normalized or "legacy_feature"]

    def _feature_mode_label(self, mode: str) -> str:
        mapping = {
            "status_permissions": "권한/상태 규칙",
            "search_filters": "조회/필터 규칙",
            "save_validation": "저장/검증 규칙",
        }
        return mapping.get((mode or "").strip(), "일반 기능")

    def _transition_condition_hint(self, text: str, roles: list[str], status: str, action: str) -> str:
        matched_roles = [role for role in roles if re.search(rf"{role}.*{action}|{action}.*{role}", text, flags=re.IGNORECASE)]
        if matched_roles:
            return " or ".join(role.lower() for role in matched_roles)
        if re.search(r"<c:if|<c:choose|if\s*\(", text, flags=re.IGNORECASE):
            return "legacy conditional branch"
        return f"status is {status}"

    def _infer_target_status(self, action: str, statuses: list[str]) -> str:
        mapping = {
            "approve": "APPROVED",
            "reject": "REJECTED",
            "resubmit": "PENDING",
            "submit": "SUBMITTED",
            "close": "CLOSED",
            "reopen": "PENDING",
            "cancel": "CANCELLED",
        }
        candidate = mapping.get(action.lower())
        if candidate and candidate in statuses:
            return candidate
        return candidate or "UNKNOWN"

    def _infer_filter_field_type(self, name: str) -> str:
        lowered = name.lower()
        if lowered in {"includeclosed", "enabled", "active", "visible"}:
            return "checkbox"
        if "date" in lowered:
            return "date"
        if lowered in {"page", "limit", "offset"}:
            return "number"
        return "text"

    def _extract_select_columns(self, sql_text: str) -> list[str]:
        if not sql_text:
            return []
        match = re.search(r"select\s+(.*?)\s+from\s", sql_text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return []
        segment = match.group(1)
        if "*" in segment:
            return []
        columns: list[str] = []
        for raw in segment.split(","):
            token = raw.strip().split()[-1].split(".")[-1]
            token = token.strip("`\"")
            if token:
                columns.append(token.lower())
        return self._dedupe_list(columns)

    def _looks_like_jsp(self, prepared: Any) -> bool:
        assets = getattr(prepared, "assets", None)
        text = "\n".join(
            [
                str(getattr(assets, "source_code", "") or ""),
                str(getattr(assets, "ui_template", "") or ""),
            ]
        ).lower()
        return "<%" in text or "<jsp:" in text or "c:foreach" in text or "c:if" in text

    def _contains_sql_in_ui(self, prepared: Any) -> bool:
        assets = getattr(prepared, "assets", None)
        text = "\n".join(
            [
                str(getattr(assets, "source_code", "") or ""),
                str(getattr(assets, "ui_template", "") or ""),
            ]
        ).lower()
        return bool(re.search(r"\b(select|insert|update|delete)\b", text))

    def _extract_unique_matches(self, text: str, pattern: str) -> list[str]:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        results: list[str] = []
        for match in matches:
            if isinstance(match, tuple):
                for item in match:
                    cleaned = (item or "").strip()
                    if cleaned:
                        results.append(cleaned)
                        break
            else:
                cleaned = (match or "").strip()
                if cleaned:
                    results.append(cleaned)
        return self._dedupe_list(results)

    def _dedupe_list(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for item in items:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output

    def _dedupe_dicts(self, items: list[dict]) -> list[dict]:
        seen: set[str] = set()
        output: list[dict] = []
        for item in items:
            key = repr(sorted(item.items()))
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output

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
