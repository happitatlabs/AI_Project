from __future__ import annotations

import re
from typing import Any

from mellow_link.modules.rebuild_assistant.schemas import StructuredRebuildResult

from .narrative_fallback import DeterministicNarrativeBuilder
from .schemas import (
    DecisionArtifacts,
    DecisionSummary,
    DiagnosisArtifacts,
    ImprovementArtifacts,
    StructureAnalysisResult,
    StructuredRefactoringResult,
)


class ResultPackager:
    def __init__(self) -> None:
        self.narrative_builder = DeterministicNarrativeBuilder()

    def package(
        self,
        prepared: Any,
        structure: StructureAnalysisResult,
        diagnosis: DiagnosisArtifacts,
        decisions: DecisionArtifacts,
        improvement: ImprovementArtifacts,
        legacy_service: Any,
    ) -> StructuredRebuildResult:
        decision_engine_guard_applied = bool(decisions.synthetic_signal_detected)
        decisions, packager_guard_applied = self._apply_decision_governance(decisions, diagnosis)
        confidence = legacy_service.estimate_confidence(prepared)
        extensions = legacy_service._build_extensions(prepared)
        feature_slices = []
        for item in structure.structure_snapshot.feature_slices:
            if item.business_rules:
                feature_slices.append(item)
            else:
                feature_slices.append(item.model_copy(update={"business_rules": diagnosis.core_business_rules[:2]}))
        authoritative = StructuredRefactoringResult(
            structure_snapshot=structure.structure_snapshot.model_copy(update={"feature_slices": feature_slices}),
            diagnosis_report=diagnosis.diagnosis_report,
            decision_summary=decisions.decision_summary,
            improvement_plan_bundle=improvement.improvement_plan_bundle,
            appendix={"evidence_index": [item.model_dump() for item in diagnosis.evidence_index]},
        )
        result = StructuredRebuildResult(
            primary_judgment=decisions.primary_judgment,
            template_judgment=decisions.template_judgment or decisions.primary_judgment,
            structural_judgment=decisions.structural_judgment,
            narrative_axis=decisions.narrative_axis or decisions.selected_narrative_judgment,
            feature_signal_mode=decisions.feature_signal_mode,
            primary_judgment_reason="",
            pattern_candidates=decisions.pattern_candidates,
            one_line_conclusion="",
            core_business_rules=list(diagnosis.core_business_rules),
            executive_summary_v2=[],
            grounded_business_rules=diagnosis.grounded_business_rules,
            decision_items=decisions.decision_items,
            retained_contracts=list(diagnosis.retained_contracts),
            priority_split_items=improvement.priority_split_items,
            verification_checkpoints=improvement.verification_checkpoints,
            design_options=improvement.design_options,
            recommended_option=improvement.recommended_option,
            execution_plan=improvement.execution_plan,
            analysis_summary=diagnosis.analysis_summary,
            rebuild_strategy=improvement.rebuild_strategy,
            layer_reconstruction=improvement.layer_reconstruction,
            recomposition_draft=improvement.recomposition_draft,
            risks=improvement.risks,
            extracted_rules=diagnosis.extracted_rules,
            recommended_directions=improvement.recommended_directions,
            confidence=confidence,
            missing_context=[item.required_material for item in diagnosis.missing_context_details],
            missing_context_details=diagnosis.missing_context_details,
            extensions=extensions,
            structure_snapshot=authoritative.structure_snapshot.model_dump(),
            diagnosis_report=authoritative.diagnosis_report.model_dump(),
            decision_summary=authoritative.decision_summary.model_dump(),
            improvement_plan_bundle=authoritative.improvement_plan_bundle.model_dump(),
            appendix=authoritative.appendix,
        )
        result = legacy_service._apply_accounting_top_narrative(prepared, result)
        narrative_bundle = self.narrative_builder.build(
            prepared=prepared,
            diagnosis=diagnosis,
            decisions=decisions,
            improvement=improvement,
            confidence=confidence,
            extensions=result.extensions,
        )
        merged_extensions = dict(result.extensions if isinstance(result.extensions, dict) else {})
        merged_extensions["narrative"] = {
            "source": "deterministic_fallback",
            "fields_rewritten": [],
            "model": "",
            "prompt_version": "phase1.8-top-narrative-v1",
            "validation_passed": True,
            "failure_reason": "",
            "axis": narrative_bundle.narrative_axis,
        }
        merged_extensions["decision_governance"] = {
            "synthetic_signal_detected": bool(decisions.synthetic_signal_detected),
            "packager_guard_applied": bool(packager_guard_applied),
        }
        merged_extensions["review_diff"] = self._build_review_diff(
            prepared=prepared,
            structure=structure,
            diagnosis=diagnosis,
            decisions=decisions,
            decision_engine_guard_applied=decision_engine_guard_applied,
            packager_guard_applied=packager_guard_applied,
        )
        result = result.model_copy(
            update={
                "report_purpose": narrative_bundle.report_purpose,
                "report_scope": narrative_bundle.report_scope,
                "report_questions": narrative_bundle.report_questions,
                "primary_judgment_reason": narrative_bundle.primary_judgment_reason or decisions.primary_judgment_reason,
                "one_line_conclusion": narrative_bundle.one_line_conclusion,
                "executive_summary_v2": narrative_bundle.executive_summary_v2,
                "core_business_rules": narrative_bundle.core_business_rules,
                "retained_contracts": narrative_bundle.retained_contracts,
                "extensions": merged_extensions,
            }
        )
        result = self._soften_supporting_sentences(result)
        result = legacy_service._apply_accounting_bottom_sections(prepared, result)
        return legacy_service._sanitize_structured_result(result)

    def _build_review_diff(
        self,
        *,
        prepared: Any,
        structure: StructureAnalysisResult,
        diagnosis: DiagnosisArtifacts,
        decisions: DecisionArtifacts,
        decision_engine_guard_applied: bool,
        packager_guard_applied: bool,
    ) -> dict[str, Any]:
        component_alias_map = {
            item.component_id: f"Component{index:02d}"
            for index, item in enumerate(
                sorted(structure.structure_snapshot.components, key=lambda current: current.component_id),
                start=1,
            )
        }
        table_names = sorted({table for item in structure.structure_snapshot.feature_slices for table in item.related_tables})
        table_alias_map = {name: f"DataStore{index:02d}" for index, name in enumerate(table_names, start=1)}
        slice_alias_map = {
            item.slice_id: f"Slice{index:02d}"
            for index, item in enumerate(
                sorted(structure.structure_snapshot.feature_slices, key=lambda current: current.slice_id),
                start=1,
            )
        }
        evidence_map = {item.evidence_id: item for item in diagnosis.evidence_index}
        issue_map = {item.issue_id: item for item in diagnosis.diagnosis_report.issues}
        fingerprint_alias_map = self._build_fingerprint_alias_map(diagnosis, evidence_map)
        structural_diff = self._build_structural_diff(
            structure=structure,
            component_alias_map=component_alias_map,
            table_alias_map=table_alias_map,
            slice_alias_map=slice_alias_map,
            issue_map=issue_map,
        )
        evidence_diff = self._build_evidence_diff(
            diagnosis=diagnosis,
            evidence_map=evidence_map,
            issue_map=issue_map,
            fingerprint_alias_map=fingerprint_alias_map,
        )
        decision_diff = self._build_decision_diff(
            decisions=decisions,
            diagnosis=diagnosis,
            decision_engine_guard_applied=decision_engine_guard_applied,
            packager_guard_applied=packager_guard_applied,
        )
        code_diff = self._build_code_diff(
            prepared=prepared,
            diagnosis=diagnosis,
            evidence_map=evidence_map,
        )
        markdown = self._render_review_diff_markdown(
            structural_diff=structural_diff,
            evidence_diff=evidence_diff,
            decision_diff=decision_diff,
            code_diff=code_diff,
        )
        return {
            "structural_diff": structural_diff,
            "evidence_diff": evidence_diff,
            "decision_diff": decision_diff,
            "code_diff": code_diff,
            "markdown": markdown,
        }

    def _build_structural_diff(
        self,
        *,
        structure: StructureAnalysisResult,
        component_alias_map: dict[str, str],
        table_alias_map: dict[str, str],
        slice_alias_map: dict[str, str],
        issue_map: dict[str, Any],
    ) -> dict[str, Any]:
        component_structure = [
            {
                "component": component_alias_map.get(item.component_id, item.component_id),
                "layer": item.layer,
                "responsibility_families": list(item.responsibility_families),
            }
            for item in sorted(structure.structure_snapshot.components, key=lambda current: current.component_id)
        ]
        dependency_flows = [
            f"{component_alias_map.get(edge.from_component, edge.from_component)} [{structure.component_layer_map.get(edge.from_component, '')}] -> "
            f"{component_alias_map.get(edge.to_component, edge.to_component)} [{structure.component_layer_map.get(edge.to_component, '')}] "
            f"({edge.dependency_type})"
            for edge in sorted(
                structure.structure_snapshot.dependencies,
                key=lambda current: (current.from_component, current.to_component, current.dependency_type),
            )
        ]
        layer_boundary_notes = []
        for issue in structure.structure_snapshot.feature_slices:
            _ = issue
        for issue in issue_map.values():
            if issue.detector_id not in {"boundary_mismatch", "ui_data_access_coupling"}:
                continue
            aliases = [component_alias_map.get(item, item) for item in issue.affected_component_ids]
            layer_boundary_notes.append(
                {
                    "detector_id": issue.detector_id,
                    "components": aliases,
                    "note": f"{issue.detector_id} on {', '.join(aliases) if aliases else 'component set'}",
                }
            )
        data_flow_notes = []
        for item in sorted(structure.structure_snapshot.feature_slices, key=lambda current: current.slice_id):
            component_aliases = [component_alias_map.get(component_id, component_id) for component_id in item.related_components]
            table_aliases = [table_alias_map.get(table_name, "DataStore") for table_name in item.related_tables]
            data_flow_notes.append(
                {
                    "slice": slice_alias_map.get(item.slice_id, item.slice_id),
                    "components": component_aliases,
                    "data_stores": table_aliases,
                    "entry_point_count": len(item.entry_points),
                }
            )
        return {
            "component_structure": component_structure,
            "dependency_flows": dependency_flows,
            "layer_boundary_notes": layer_boundary_notes,
            "data_flow_notes": data_flow_notes,
        }

    def _build_evidence_diff(
        self,
        *,
        diagnosis: DiagnosisArtifacts,
        evidence_map: dict[str, Any],
        issue_map: dict[str, Any],
        fingerprint_alias_map: dict[str, str],
    ) -> dict[str, Any]:
        grouped: dict[str, list[Any]] = {}
        for item in diagnosis.evidence_index:
            grouped.setdefault(item.fingerprint, []).append(item)
        repeated_fingerprints = []
        for fingerprint, items in sorted(grouped.items(), key=lambda current: (-len(current[1]), current[0])):
            if len(items) < 2:
                continue
            repeated_fingerprints.append(
                {
                    "fingerprint_alias": fingerprint_alias_map.get(fingerprint, "Fingerprint00"),
                    "occurrence_count": len(items),
                    "locations": [f"{item.asset_name}:{item.locator}" for item in items],
                }
            )
        detector_evidence_map = []
        scatter_traces = []
        leak_traces = []
        coupling_traces = []
        for issue in diagnosis.diagnosis_report.issues:
            locations = [f"{evidence_map[evidence_id].asset_name}:{evidence_map[evidence_id].locator}" for evidence_id in issue.evidence_ids if evidence_id in evidence_map]
            aliases = [fingerprint_alias_map.get(evidence_map[evidence_id].fingerprint, "Fingerprint00") for evidence_id in issue.evidence_ids if evidence_id in evidence_map]
            entry = {
                "issue_id": issue.issue_id,
                "detector_id": issue.detector_id,
                "fingerprint_aliases": aliases,
                "locations": locations,
            }
            detector_evidence_map.append(entry)
            if issue.detector_id in {"rule_scatter", "duplicate_logic_candidate"}:
                scatter_traces.append(entry)
            if issue.detector_id in {"validation_guard_leak", "query_filter_leak", "state_transition_leak"}:
                leak_traces.append(entry)
            if issue.detector_id in {"ui_data_access_coupling", "boundary_mismatch"}:
                coupling_traces.append(entry)
        return {
            "repeated_fingerprints": repeated_fingerprints,
            "detector_evidence_map": detector_evidence_map,
            "scatter_traces": scatter_traces,
            "leak_traces": leak_traces,
            "coupling_traces": coupling_traces,
        }

    def _build_decision_diff(
        self,
        *,
        decisions: DecisionArtifacts,
        diagnosis: DiagnosisArtifacts,
        decision_engine_guard_applied: bool,
        packager_guard_applied: bool,
    ) -> dict[str, Any]:
        allowed_decisions = [
            {
                "decision_id": item.decision_id,
                "decision_type": item.decision_type,
                "priority_score": item.priority_score,
                "issue_count": len(item.issue_ids),
                "evidence_count": len(item.evidence_ids),
            }
            for item in decisions.decision_summary.decisions
        ]
        blocked_decisions = []
        block_reasons: list[str] = []
        if decisions.synthetic_signal_detected:
            downgrade_target = "observation_only" if not diagnosis.diagnosis_report.issues else "refactor"
            blocked_decisions.append(
                {
                    "decision_type": "migration_consideration",
                    "downgraded_to": downgrade_target,
                    "block_reason": "no asset-derived migration evidence; issue_ids = []; evidence_ids = []; goal wording only (contamination)",
                }
            )
            block_reasons.extend(
                [
                    "no asset-derived migration evidence",
                    "issue_ids = []",
                    "evidence_ids = []",
                    "goal wording only (contamination)",
                ]
            )
        return {
            "allowed_decisions": allowed_decisions,
            "blocked_decisions": blocked_decisions,
            "block_reasons": block_reasons,
            "synthetic_signal_detected": bool(decisions.synthetic_signal_detected),
            "decision_engine_guard_applied": bool(decision_engine_guard_applied),
            "result_packager_guard_applied": bool(packager_guard_applied),
        }

    def _build_code_diff(
        self,
        *,
        prepared: Any,
        diagnosis: DiagnosisArtifacts,
        evidence_map: dict[str, Any],
    ) -> dict[str, Any]:
        if not diagnosis.diagnosis_report.issues or not evidence_map:
            return {"available": False, "snippets": []}
        asset_text_map = self._source_text_map(prepared)
        if not asset_text_map:
            return {"available": False, "snippets": []}

        snippets: list[dict[str, str]] = []
        allowed_detectors = {
            "query_filter_leak",
            "validation_guard_leak",
            "state_transition_leak",
            "ui_data_access_coupling",
            "boundary_mismatch",
            "rule_scatter",
            "duplicate_logic_candidate",
            "mixed_responsibility",
        }
        for issue in diagnosis.diagnosis_report.issues:
            if issue.detector_id not in allowed_detectors:
                continue
            if not issue.evidence_ids:
                continue
            snippet = self._build_code_diff_snippet(
                detector_id=issue.detector_id,
                evidence_ids=issue.evidence_ids,
                evidence_map=evidence_map,
                asset_text_map=asset_text_map,
            )
            if not snippet:
                continue
            snippets.append(snippet)
            if len(snippets) >= 3:
                break
        return {
            "available": bool(snippets),
            "snippets": snippets,
        }

    def _build_code_diff_snippet(
        self,
        *,
        detector_id: str,
        evidence_ids: list[str],
        evidence_map: dict[str, Any],
        asset_text_map: dict[str, str],
    ) -> dict[str, str] | None:
        for evidence_id in evidence_ids:
            evidence = evidence_map.get(evidence_id)
            if not evidence:
                continue
            if not str(evidence.locator or "").strip():
                continue
            if not str(evidence.excerpt or "").strip():
                continue
            evidence_asset_id = str(evidence.asset_id or "").strip()
            evidence_asset_name = str(evidence.asset_name or "").strip()
            source_text = str(
                asset_text_map.get(evidence_asset_id)
                or asset_text_map.get(evidence_asset_name)
                or asset_text_map.get(evidence_asset_name.lower())
                or ""
            ).strip()
            if not source_text:
                continue
            observed = self._extract_observed_pattern_snippet(source_text, str(evidence.excerpt or ""))
            expected_pattern = self._expected_pattern_template(
                detector_id=detector_id,
                asset_type=str(evidence.asset_type or ""),
            )
            if not self._is_meaningful_pattern_comparison(observed, expected_pattern):
                continue
            return {
                "type": "before_after",
                "file": str(evidence.asset_name or evidence.asset_id or "-"),
                "observed": observed,
                "expected_pattern": expected_pattern,
            }
        return None

    def _source_text_map(self, prepared: Any) -> dict[str, str]:
        safe_bundle = getattr(prepared, "safe_bundle", None)
        if safe_bundle is None:
            return {}
        result: dict[str, str] = {}
        for source in getattr(safe_bundle, "sources", []) or []:
            asset_id = str(getattr(source, "asset_id", "") or "").strip()
            asset_name = str(
                getattr(source, "name", "")
                or getattr(source, "asset_name", "")
                or getattr(source, "original_filename", "")
                or ""
            ).strip()
            content = str(getattr(source, "content", "") or "")
            if not content.strip():
                continue
            if asset_id:
                result[asset_id] = content
            if asset_name:
                result[asset_name] = content
                result[asset_name.lower()] = content
        return result

    def _extract_observed_pattern_snippet(self, source_text: str, excerpt: str) -> str:
        normalized_lines = [line.rstrip() for line in str(source_text or "").replace("\r\n", "\n").split("\n")]
        excerpt_lines = [line.strip() for line in str(excerpt or "").replace("\r\n", "\n").split("\n") if line.strip()]
        if not normalized_lines:
            return ""
        anchor = excerpt_lines[0] if excerpt_lines else ""
        index = -1
        if anchor:
            lowered_anchor = anchor.lower()
            for current_index, line in enumerate(normalized_lines):
                if lowered_anchor in line.lower():
                    index = current_index
                    break
        if index < 0:
            compact_excerpt = " ".join(excerpt_lines).strip()
            if compact_excerpt:
                return "\n".join(excerpt_lines[:6]).strip()
            return "\n".join(normalized_lines[:6]).strip()
        start = max(0, index - 2)
        end = min(len(normalized_lines), index + 4)
        snippet_lines = normalized_lines[start:end]
        trimmed_lines = [line for line in snippet_lines if line.strip()]
        return "\n".join(trimmed_lines[:6]).strip()

    def _expected_pattern_template(self, *, detector_id: str, asset_type: str) -> str:
        lowered_asset_type = (asset_type or "").strip().lower()
        if detector_id == "query_filter_leak":
            if lowered_asset_type == "sql":
                return "\n".join(
                    [
                        "WITH FilterInput AS (",
                        "    SELECT :status AS status, :from_date AS from_date",
                        ")",
                        "SELECT *",
                        "FROM ReportQuery01",
                        "WHERE status = FilterInput.status",
                    ]
                )
            return "\n".join(
                [
                    "filters = QueryFragment01.normalize(params)",
                    "query = Repository01.base_query()",
                    "query = QueryFragment01.apply(query, filters)",
                    "return Repository01.search(query)",
                ]
            )
        if detector_id == "validation_guard_leak":
            return "\n".join(
                [
                    "ValidationRule01.check(command)",
                    "if command.has_errors():",
                    "    return command.errors",
                    "return Service01.save(command)",
                ]
            )
        if detector_id == "state_transition_leak":
            return "\n".join(
                [
                    "next_state = TransitionPolicy01.resolve(current_state, action)",
                    "if not next_state:",
                    "    raise TransitionBlocked()",
                    "return StateStore01.save(next_state)",
                ]
            )
        if detector_id == "ui_data_access_coupling":
            return "\n".join(
                [
                    "result = Service01.load(view_model)",
                    "render(result)",
                    "submitButton.onclick = () => Service01.submit(command)",
                ]
            )
        if detector_id == "boundary_mismatch":
            return "\n".join(
                [
                    "policy_result = BoundaryPolicy01.evaluate(command)",
                    "if not policy_result.allowed:",
                    "    return policy_result",
                    "return Repository01.save(policy_result.payload)",
                ]
            )
        if detector_id == "rule_scatter":
            return "\n".join(
                [
                    "rule_result = RuleSet01.evaluate(context)",
                    "if not rule_result.allowed:",
                    "    return rule_result",
                    "return Service01.execute(rule_result.payload)",
                ]
            )
        if detector_id == "duplicate_logic_candidate":
            return "\n".join(
                [
                    "normalized = RuleFragment01.normalize(input_data)",
                    "if not normalized.valid:",
                    "    return normalized.errors",
                    "return Service01.apply(normalized.payload)",
                ]
            )
        return "\n".join(
            [
                "command = Component01.prepare(input_data)",
                "result = Service01.execute(command)",
                "return Presenter01.render(result)",
            ]
        )

    def _is_meaningful_pattern_comparison(self, observed: str, expected_pattern: str) -> bool:
        if not observed.strip() or not expected_pattern.strip():
            return False
        observed_lines = [line.strip() for line in observed.splitlines() if line.strip()]
        expected_lines = [line.strip() for line in expected_pattern.splitlines() if line.strip()]
        if len(observed_lines) < 2 or len(expected_lines) < 2:
            return False
        normalized_observed = re.sub(r"\s+", "", observed)
        normalized_expected = re.sub(r"\s+", "", expected_pattern)
        return normalized_observed != normalized_expected

    def _render_review_diff_markdown(
        self,
        *,
        structural_diff: dict[str, Any],
        evidence_diff: dict[str, Any],
        decision_diff: dict[str, Any],
        code_diff: dict[str, Any],
    ) -> str:
        lines = ["## Decision Result", ""]
        if decision_diff["allowed_decisions"]:
            for item in decision_diff["allowed_decisions"][:5]:
                lines.append(
                    f"✔ allowed: {item['decision_type']} ({item['decision_id']}) "
                    f"priority={item['priority_score']} issue_count={item['issue_count']} evidence_count={item['evidence_count']}"
                )
        else:
            lines.append("✔ allowed: none")
        if decision_diff["blocked_decisions"]:
            lines.append("")
            for item in decision_diff["blocked_decisions"]:
                lines.append(
                    f"✖ blocked: {item['decision_type']} -> {item['downgraded_to']}"
                )
            lines.append("")
            lines.append("Reason:")
            for item in decision_diff["block_reasons"]:
                lines.append(f"- {item}")
        else:
            lines.append("")
            lines.append("✖ blocked: none")
        lines.extend(
            [
                "",
                f"- synthetic_signal_detected: {decision_diff['synthetic_signal_detected']}",
                f"- decision_engine_guard_applied: {decision_diff['decision_engine_guard_applied']}",
                f"- result_packager_guard_applied: {decision_diff['result_packager_guard_applied']}",
            ]
        )

        lines.extend(["", "## Why this decision?", "", "### Evidence"])
        positive_evidence = self._review_diff_positive_evidence_lines(evidence_diff)
        if positive_evidence:
            for item in positive_evidence[:8]:
                lines.append(f"- {item}")
        else:
            lines.append("- no repeated fingerprint or detector evidence summary")

        negative_evidence = self._review_diff_negative_evidence_lines(decision_diff)
        lines.extend(["", "### No migration signals"])
        if negative_evidence:
            for item in negative_evidence:
                lines.append(f"- {item}")
        else:
            lines.append("- no blocked migration signal")

        if code_diff.get("available"):
            lines.extend(
                [
                    "",
                    "## 현재 구조 vs 권장 구조 비교",
                    "",
                    "이 비교는 실제 패치가 아니라, 현재 구조와 권장 패턴의 차이를 검토하기 위한 근거 예시입니다.",
                ]
            )
            for item in code_diff.get("snippets", [])[:3]:
                lines.extend(
                    [
                        "",
                        f"### {item.get('file') or '-'}",
                        "",
                        "#### observed",
                        "",
                        "```diff",
                    ]
                )
                for line in str(item.get("observed") or "").splitlines():
                    lines.append(f"- {line}")
                lines.extend(["```", "", "#### expected_pattern", "", "```diff"])
                for line in str(item.get("expected_pattern") or "").splitlines():
                    lines.append(f"+ {line}")
                lines.append("```")

        lines.extend(["", "## Structural Difference", "", "### Observed"])
        observed_lines = self._review_diff_structural_observed_lines(structural_diff)
        if observed_lines:
            for item in observed_lines[:10]:
                lines.append(f"- {item}")
        else:
            lines.append("- no structural difference summary")

        expected_lines = self._review_diff_structural_expected_lines(structural_diff)
        lines.extend(["", "### Expected Pattern"])
        if expected_lines:
            for item in expected_lines[:6]:
                lines.append(f"- {item}")
        else:
            lines.append("- review expected service/repository separation and normalized data flow")
        return "\n".join(lines).strip()

    def _review_diff_positive_evidence_lines(self, evidence_diff: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        for item in evidence_diff["repeated_fingerprints"][:5]:
            lines.append(
                f"{item['fingerprint_alias']} appears in {item['occurrence_count']} locations"
            )
        for item in evidence_diff["leak_traces"][:5]:
            lines.append(
                f"{item['detector_id']} detected at {', '.join(item['locations'][:3]) or '-'}"
            )
        for item in evidence_diff["scatter_traces"][:5]:
            lines.append(
                f"{item['detector_id']} detected at {', '.join(item['locations'][:3]) or '-'}"
            )
        for item in evidence_diff["coupling_traces"][:5]:
            lines.append(
                f"{item['detector_id']} detected at {', '.join(item['locations'][:3]) or '-'}"
            )
        if not lines:
            for item in evidence_diff["detector_evidence_map"][:5]:
                lines.append(
                    f"{item['detector_id']} linked to {', '.join(item['locations'][:3]) or '-'}"
                )
        return lines

    def _review_diff_negative_evidence_lines(self, decision_diff: dict[str, Any]) -> list[str]:
        if decision_diff["blocked_decisions"]:
            return list(decision_diff["block_reasons"])
        return []

    def _review_diff_structural_observed_lines(self, structural_diff: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        for item in structural_diff["dependency_flows"][:5]:
            lines.append(item)
        for item in structural_diff["data_flow_notes"][:5]:
            lines.append(
                f"{item['slice']} -> components={', '.join(item['components']) or '-'} -> data_stores={', '.join(item['data_stores']) or '-'}"
            )
        for item in structural_diff["component_structure"][:4]:
            lines.append(
                f"{item['component']} [{item['layer']}] responsibilities={', '.join(item['responsibility_families']) or '-'}"
            )
        return lines

    def _review_diff_structural_expected_lines(self, structural_diff: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        for item in structural_diff["layer_boundary_notes"][:5]:
            lines.append(item["note"])
        if structural_diff["data_flow_notes"]:
            lines.append("normalize repeated query and validation flow behind stable component boundaries")
        if structural_diff["dependency_flows"]:
            lines.append("reduce direct cross-layer dependencies in the observed flow")
        return lines

    def _build_fingerprint_alias_map(self, diagnosis: DiagnosisArtifacts, evidence_map: dict[str, Any]) -> dict[str, str]:
        alias_map: dict[str, str] = {}
        counters: dict[str, int] = {}
        issue_map = {item.issue_id: item for item in diagnosis.diagnosis_report.issues}
        for issue in diagnosis.diagnosis_report.issues:
            prefix = self._fingerprint_prefix(issue.detector_id)
            for evidence_id in issue.evidence_ids:
                if evidence_id not in evidence_map:
                    continue
                fingerprint = evidence_map[evidence_id].fingerprint
                if fingerprint in alias_map:
                    continue
                counters[prefix] = counters.get(prefix, 0) + 1
                alias_map[fingerprint] = f"{prefix}{counters[prefix]:02d}"
        for fingerprint in sorted({item.fingerprint for item in diagnosis.evidence_index}):
            if fingerprint in alias_map:
                continue
            prefix = self._fingerprint_prefix("")
            counters[prefix] = counters.get(prefix, 0) + 1
            alias_map[fingerprint] = f"{prefix}{counters[prefix]:02d}"
        return alias_map

    def _fingerprint_prefix(self, detector_id: str) -> str:
        if detector_id == "query_filter_leak":
            return "QueryFragment"
        if detector_id == "validation_guard_leak":
            return "ValidationRule"
        if detector_id == "state_transition_leak":
            return "StateTransition"
        if detector_id in {"ui_data_access_coupling", "boundary_mismatch"}:
            return "CouplingTrace"
        return "RuleFragment"

    def _apply_decision_governance(
        self,
        decisions: DecisionArtifacts,
        diagnosis: DiagnosisArtifacts,
    ) -> tuple[DecisionArtifacts, bool]:
        guarded = []
        guard_applied = False
        has_structural_issues = bool(diagnosis.diagnosis_report.issues)
        for item in decisions.decision_summary.decisions:
            if item.decision_type != "migration_consideration" or item.issue_ids or item.evidence_ids:
                guarded.append(item)
                continue
            guard_applied = True
            if not has_structural_issues:
                continue
            guarded.append(
                item.model_copy(
                    update={
                        "decision_type": "refactor",
                        "rationale": "전환 신호가 있었지만 구조 근거가 부족해 일반 리팩터링 후보로 낮춰 검토하는 편이 적절합니다.",
                        "explainability": item.explainability.model_copy(
                            update={
                                "decision_rule": "result packager migration hard guard -> refactor",
                                "score_summary": f"{item.explainability.score_summary}; packager hard guard downgraded to refactor",
                            }
                        ),
                    }
                )
            )
        if not guard_applied:
            return decisions, False
        guarded.sort(key=lambda item: (-item.priority_score, -item.confidence, item.decision_id))
        summary = self._rebuild_decision_summary(guarded)
        return (
            decisions.model_copy(
                update={
                    "decision_summary": summary,
                    "structural_judgment": self._structural_judgment(summary),
                    "synthetic_signal_detected": True,
                }
            ),
            True,
        )

    def _rebuild_decision_summary(self, decisions) -> DecisionSummary:
        if not decisions:
            return DecisionSummary(recommended_strategy="리팩터링 우선", priority_queue=[])
        redesign_count = sum(1 for item in decisions if item.decision_type == "redesign")
        migration_count = sum(1 for item in decisions if item.decision_type == "migration_consideration")
        if migration_count and decisions[0].decision_type == "migration_consideration":
            strategy = "마이그레이션 고려"
        elif redesign_count:
            strategy = "재설계 우선"
        else:
            strategy = "리팩터링 우선"
        return DecisionSummary(
            decisions=list(decisions),
            recommended_strategy=strategy,
            priority_queue=[item.decision_id for item in decisions],
        )

    def _structural_judgment(self, decision_summary: DecisionSummary) -> str:
        decisions = list(decision_summary.decisions or [])
        strategy = str(decision_summary.recommended_strategy or "").strip()
        if not decisions:
            return "observation_only"
        if strategy == "마이그레이션 고려" or decisions[0].decision_type == "migration_consideration":
            return "migration_consideration"
        if strategy == "재설계 우선" or decisions[0].decision_type == "redesign":
            return "redesign"
        return "refactor"

    def _soften_supporting_sentences(self, result: StructuredRebuildResult) -> StructuredRebuildResult:
        top_decision_rationale = ""
        decisions = result.decision_summary.get("decisions", []) if isinstance(result.decision_summary, dict) else []
        if decisions:
            top_decision_rationale = str(decisions[0].get("rationale", "") or "")
        decision_items = [
            item.model_copy(update={"rationale": self._soften_sentence(item.rationale)})
            for item in result.decision_items
        ]
        design_options = [
            item.model_copy(update={"selection_reason": self._soften_sentence(item.selection_reason)})
            for item in result.design_options
        ]
        recommended_option = result.recommended_option
        if recommended_option is not None:
            recommended_option = recommended_option.model_copy(
                update={
                    "selection_reason": self._soften_sentence(recommended_option.selection_reason),
                    "expected_outcomes": [self._soften_sentence(text) for text in recommended_option.expected_outcomes],
                }
            )
        executive_summary = [
            line if index == 0 else self._soften_sentence(line)
            for index, line in enumerate(result.executive_summary_v2)
        ]
        return result.model_copy(
            update={
                "primary_judgment_reason": self._soften_sentence(result.primary_judgment_reason or top_decision_rationale),
                "executive_summary_v2": executive_summary,
                "decision_items": decision_items,
                "design_options": design_options,
                "recommended_option": recommended_option,
            }
        )

    def _soften_sentence(self, text: str) -> str:
        softened = str(text or "").strip()
        if not softened:
            return softened
        replacements = (
            (r"확정하는 것이 필요합니다\.?", "우선 기준안으로 두는 편이 적절합니다."),
            (r"확정해야 합니다\.?", "우선 기준안으로 두는 편이 적절합니다."),
            (r"완료해야 합니다\.?", "먼저 정리하는 편이 적절합니다."),
            (r"고정해야 합니다\.?", "먼저 정리하는 편이 안전합니다."),
            (r"고정해야 하므로", "먼저 정리하는 편이 안전하므로"),
            (r"우선 적용해야 합니다\.?", "우선 적용하는 편이 적절합니다."),
            (r"적용해야 합니다\.?", "적용하는 편이 적절합니다."),
            (r"후속 검증하는 것이 필요합니다\.?", "후속 검증 대상으로 두는 편이 적절합니다."),
            (r"후속 마이그레이션 검토가 필요합니다\.?", "후속 마이그레이션 검토를 함께 두는 편이 적절합니다."),
        )
        for pattern, replacement in replacements:
            softened = re.sub(pattern, replacement, softened)
        return softened
