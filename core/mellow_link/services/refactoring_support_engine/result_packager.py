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
        grounding_profile = self._build_recommendation_grounding_profile(prepared, diagnosis, decisions, confidence)
        constraint_filters = self._constraint_filters(prepared)
        improvement = self._apply_recommendation_grounding(improvement, grounding_profile)
        governance_extension = self._build_governance_extension(
            prepared=prepared,
            diagnosis=diagnosis,
            decisions=decisions,
            improvement=improvement,
            confidence=confidence,
            synthetic_signal_detected=bool(decisions.synthetic_signal_detected),
            packager_guard_applied=bool(packager_guard_applied),
            grounding_profile=grounding_profile,
            constraint_filters=constraint_filters,
        )
        extensions = dict(legacy_service._build_extensions(prepared) or {})
        extensions["decision_governance"] = governance_extension
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
            "insufficient_grounding": bool(grounding_profile.get("insufficient_grounding")),
            "grounding_level": str(grounding_profile.get("level") or ""),
        }
        merged_extensions["decision_governance"] = governance_extension
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

    def _build_governance_extension(
        self,
        *,
        prepared: Any,
        diagnosis: DiagnosisArtifacts,
        decisions: DecisionArtifacts,
        improvement: ImprovementArtifacts,
        confidence: float,
        synthetic_signal_detected: bool,
        packager_guard_applied: bool,
        grounding_profile: dict[str, Any],
        constraint_filters: list[dict[str, str]],
    ) -> dict[str, Any]:
        return {
            "synthetic_signal_detected": synthetic_signal_detected,
            "packager_guard_applied": packager_guard_applied,
            "intent_usage_policy": self._intent_usage_policy(),
            "recommendation_grounding": grounding_profile,
            "confidence_policy": self._confidence_policy(prepared, confidence),
            "constraint_filters_applied": constraint_filters,
            "ordered_sections": ["recommended_strategy", "rationale", "evidence", "risk", "next_step"],
            "document_outline": self._document_outline(
                prepared=prepared,
                decisions=decisions,
                diagnosis=diagnosis,
                improvement=improvement,
                grounding_profile=grounding_profile,
            ),
        }

    def _intent_usage_policy(self) -> dict[str, Any]:
        return {
            "engine_definition": "레거시 시스템을 해석하여 구조와 의존성을 진단하고, 신규 환경으로 이전 가능한 구조 초안과 의사결정 근거를 생성하는 엔진",
            "intent_channel": ["goal", "constraints", "scenario"],
            "evidence_channel": ["source_code", "ui", "sql", "schema", "framework_runtime"],
            "stage_rules": {
                "structure_analyzer": "intent_forbidden",
                "diagnosis_engine": "intent_forbidden",
                "decision_engine_goal": "priority_sort_assist_only",
                "decision_engine_constraints": "exclusion_filter_only",
                "decision_engine_scenario": "explanation_only",
                "improvement_planner_goal": "recommendation_wording_or_sort_only",
                "improvement_planner_constraints": "exclusion_filter_only",
                "improvement_planner_scenario": "explanation_only",
            },
            "forbidden_effects": [
                "dependency_classification",
                "structure_snapshot_mutation",
                "issue_detection",
                "confidence_increase",
            ],
        }

    def _confidence_policy(self, prepared: Any, confidence: float) -> dict[str, Any]:
        return {
            "evidence_only": True,
            "score": confidence,
            "included_signals": self._evidence_presence(prepared),
            "excluded_signals": ["goal", "constraints", "scenario", "supporting_docs", "narrative_fallback"],
        }

    def _evidence_presence(self, prepared: Any) -> dict[str, bool]:
        asset_presence = getattr(prepared, "asset_presence", None)
        assets = getattr(prepared, "assets", None)
        return {
            "source_code": bool(getattr(asset_presence, "has_source_code", False) or str(getattr(assets, "source_code", "") or "").strip()),
            "ui": bool(getattr(asset_presence, "has_ui_asset", False) or str(getattr(assets, "ui_template", "") or "").strip()),
            "sql": bool(getattr(asset_presence, "has_sql_asset", False) or str(getattr(assets, "sql_queries", "") or "").strip()),
            "schema": bool(getattr(asset_presence, "has_schema_asset", False) or str(getattr(assets, "database_schema", "") or "").strip()),
            "framework_runtime": bool(getattr(asset_presence, "has_framework_hint", False) or str(getattr(assets, "framework_info", "") or "").strip()),
        }

    def _build_recommendation_grounding_profile(
        self,
        prepared: Any,
        diagnosis: DiagnosisArtifacts,
        decisions: DecisionArtifacts,
        confidence: float,
    ) -> dict[str, Any]:
        evidence_presence = self._evidence_presence(prepared)
        evidence_group_count = sum(1 for present in evidence_presence.values() if present)
        evidence_backed_decision_count = sum(
            1 for item in decisions.decision_summary.decisions if item.issue_ids and item.evidence_ids
        )
        missing_context_count = len(diagnosis.missing_context_details or [])
        reason_codes: list[str] = []
        if evidence_group_count == 0:
            reason_codes.append("no_structural_evidence")
        elif evidence_group_count == 1:
            reason_codes.append("narrow_evidence_coverage")
        if not diagnosis.diagnosis_report.issues:
            reason_codes.append("no_detected_issues")
        if evidence_backed_decision_count == 0:
            reason_codes.append("no_evidence_backed_decision")
        if missing_context_count >= 2:
            reason_codes.append("missing_required_evidence")
        elif missing_context_count:
            reason_codes.append("partial_missing_context")
        if confidence < 0.25:
            reason_codes.append("low_confidence")
        elif confidence < 0.45:
            reason_codes.append("limited_confidence")

        insufficient_grounding = "no_structural_evidence" in reason_codes
        if insufficient_grounding:
            level = "insufficient"
            recommendation_mode = "observation_only"
        elif reason_codes:
            level = "limited"
            recommendation_mode = "draft"
        else:
            level = "grounded"
            recommendation_mode = "actionable"
        return {
            "level": level,
            "insufficient_grounding": insufficient_grounding,
            "recommendation_mode": recommendation_mode,
            "reason_codes": reason_codes,
            "evidence_group_count": evidence_group_count,
            "evidence_backed_decision_count": evidence_backed_decision_count,
            "missing_context_count": missing_context_count,
        }

    def _apply_recommendation_grounding(
        self,
        improvement: ImprovementArtifacts,
        grounding_profile: dict[str, Any],
    ) -> ImprovementArtifacts:
        level = str(grounding_profile.get("level") or "")
        if level == "grounded":
            return improvement

        design_options = []
        for item in improvement.design_options:
            option_label = self._option_display_name(item.name)
            if level == "insufficient":
                selection_reason = (
                    f"직접 확인된 구조 근거가 부족하므로 {self._attach_topic_particle(option_label)} "
                    "확정안이 아니라 검토용 초안으로만 유지합니다."
                )
            else:
                selection_reason = (
                    f"직접 확인된 구조 근거가 제한적이므로 {self._attach_topic_particle(option_label)} 우선 검토안으로 유지합니다. "
                    f"{self._soften_sentence(item.selection_reason)}"
                ).strip()
            design_options.append(item.model_copy(update={"selection_reason": selection_reason}))

        recommended_option = improvement.recommended_option
        if recommended_option is not None and level == "limited":
            option_label = self._option_display_name(recommended_option.name)
            recommended_option = recommended_option.model_copy(
                update={
                    "selection_reason": (
                        f"직접 확인된 구조 근거가 제한적이므로 {self._attach_topic_particle(option_label)} 확정안이 아니라 우선 검토안으로 유지합니다. "
                        f"{self._soften_sentence(recommended_option.selection_reason)}"
                    ).strip(),
                    "expected_outcomes": [
                        "직접 근거가 보강되면 실행 후보로 승격할 수 있습니다.",
                        "현재 단계에서는 누락 자산 확인 전까지 판단 초안으로 유지합니다.",
                    ],
                }
            )
        elif level == "insufficient":
            recommended_option = None

        improvement_plan_bundle = improvement.improvement_plan_bundle.model_copy(
            update={
                "design_options": [item.model_dump() for item in design_options],
                "recommended_option": recommended_option.model_dump() if recommended_option else None,
            }
        )
        return improvement.model_copy(
            update={
                "design_options": design_options,
                "recommended_option": recommended_option,
                "improvement_plan_bundle": improvement_plan_bundle,
            }
        )

    def _option_display_name(self, name: str) -> str:
        return re.sub(r"^옵션\s+[A-Z]\.\s*", "", str(name or "").strip()).strip() or str(name or "").strip()

    def _attach_topic_particle(self, text: str) -> str:
        stripped = str(text or "").strip()
        if not stripped:
            return stripped
        code = ord(stripped[-1])
        if 0xAC00 <= code <= 0xD7A3:
            has_batchim = (code - 0xAC00) % 28 != 0
            return stripped + ("은" if has_batchim else "는")
        return stripped + "는"

    def _constraint_filters(self, prepared: Any) -> list[dict[str, str]]:
        constraints = list(getattr(getattr(prepared, "intent", None), "constraints", []) or getattr(prepared, "constraints", []) or [])
        blocked = list(getattr(prepared, "decision_constraint_filters", []) or [])
        filters: list[dict[str, str]] = []
        for decision_type in blocked:
            source_constraint = ""
            if decision_type == "migration_consideration":
                source_constraint = next(
                    (
                        item for item in constraints
                        if any(
                            keyword in str(item or "").lower()
                            for keyword in ("migration", "마이그레이션", "전환", "재플랫폼", "rewrite", "재작성")
                        )
                    ),
                    "",
                )
            filters.append(
                {
                    "decision_type": decision_type,
                    "effect": "exclude_from_recommendation",
                    "source_constraint": str(source_constraint or ""),
                }
            )
        return filters

    def _document_outline(
        self,
        *,
        prepared: Any,
        decisions: DecisionArtifacts,
        diagnosis: DiagnosisArtifacts,
        improvement: ImprovementArtifacts,
        grounding_profile: dict[str, Any],
    ) -> dict[str, Any]:
        top_decision = decisions.decision_summary.decisions[0] if decisions.decision_summary.decisions else None
        evidence_index = {item.evidence_id: item for item in diagnosis.evidence_index}
        issue_index = {item.issue_id: item for item in diagnosis.diagnosis_report.issues}
        evidence_items: list[Any] = []
        evidence_lines: list[str] = []
        if top_decision is not None:
            for evidence_id in top_decision.evidence_ids[:3]:
                item = evidence_index.get(evidence_id)
                if item is None:
                    continue
                evidence_items.append(item)
                evidence_lines.append(f"{item.asset_name}:{item.locator}")
        if not evidence_lines and top_decision is not None:
            evidence_lines.append(f"{top_decision.decision_type}:{top_decision.explainability.decision_rule}")
        if not evidence_lines:
            evidence_lines.append("직접 연결된 구조 근거가 충분하지 않아 추가 확인이 필요합니다.")
        top_issue = None
        if top_decision is not None:
            for issue_id in top_decision.issue_ids:
                top_issue = issue_index.get(issue_id)
                if top_issue is not None:
                    break
        if top_issue is None and diagnosis.diagnosis_report.issues:
            top_issue = diagnosis.diagnosis_report.issues[0]

        rationale = self._outline_rationale(
            top_decision=top_decision,
            top_issue=top_issue,
            decisions=decisions,
            evidence_items=evidence_items,
            grounding_profile=grounding_profile,
        )
        next_step = self._outline_next_step(
            prepared=prepared,
            decisions=decisions,
            improvement=improvement,
            grounding_profile=grounding_profile,
        )
        risk = self._outline_risk(
            decisions=decisions,
            improvement=improvement,
            grounding_profile=grounding_profile,
        )
        return {
            "recommended_strategy": str(decisions.decision_summary.recommended_strategy or "리팩터링 우선"),
            "rationale": rationale,
            "evidence": evidence_lines,
            "risk": risk,
            "next_step": next_step,
        }

    def _outline_rationale(
        self,
        *,
        top_decision: Any,
        top_issue: Any,
        decisions: DecisionArtifacts,
        evidence_items: list[Any],
        grounding_profile: dict[str, Any],
    ) -> str:
        if bool(grounding_profile.get("insufficient_grounding")):
            return "직접 연결된 코드, 화면, SQL, 스키마, 런타임 근거가 부족해 구조 이전 전략을 확정하지 않았습니다."
        rationale = self._humanize_outline_rationale(top_issue)
        if not rationale:
            if top_decision is not None:
                rationale = str(top_decision.rationale or "").strip()
        if not rationale:
            rationale = str(decisions.primary_judgment_reason or "").strip()
        if not rationale:
            rationale = "직접 확인된 구조 근거를 기준으로 판단 방향을 정리했습니다."
        if evidence_items:
            evidence_names = ", ".join(item.asset_name for item in evidence_items[:2])
            if rationale[-1] not in ".!?":
                rationale = rationale + "."
            return f"{rationale} 판단 근거는 {evidence_names}에서 직접 확인된 구조 흔적입니다."
        return rationale

    def _humanize_outline_rationale(self, top_issue: Any) -> str:
        detector_id = str(getattr(top_issue, "detector_id", "") or "").strip()
        mapping = {
            "boundary_mismatch": "화면, 서비스, 데이터 접근 경계가 한 흐름에 섞여 있어 구조 경계를 다시 정의해야 합니다.",
            "ui_data_access_coupling": "UI와 데이터 접근이 직접 결합돼 있어 책임 경계를 분리해야 합니다.",
            "duplicate_logic_candidate": "같은 업무 규칙이 여러 위치에 반복되어 있어 공통 정책으로 모아야 합니다.",
            "validation_guard_leak": "차단 조건과 저장 전 검증이 처리 흐름에 섞여 있어 검증 경계를 분리해야 합니다.",
            "query_filter_leak": "조회 조건과 필터 규칙이 화면과 SQL에 흩어져 있어 조회 모델 경계를 정리해야 합니다.",
            "state_transition_leak": "상태 전이 판단이 처리 흐름과 섞여 있어 상태 정책 경계를 분리해야 합니다.",
            "mixed_responsibility": "한 컴포넌트에 여러 책임이 섞여 있어 역할별 경계를 다시 나눠야 합니다.",
            "rule_scatter": "핵심 규칙이 여러 위치에 흩어져 있어 정책 계층으로 수렴시켜야 합니다.",
        }
        return mapping.get(detector_id, "")

    def _outline_risk(
        self,
        *,
        decisions: DecisionArtifacts,
        improvement: ImprovementArtifacts,
        grounding_profile: dict[str, Any],
    ) -> str:
        if bool(grounding_profile.get("insufficient_grounding")):
            return "직접 구조 근거 없이 전략을 확정하면 잘못된 책임 경계를 기준안으로 고정할 수 있습니다."
        axis = self._outline_axis(decisions)
        standardized = {
            "validation": "차단 조건과 저장 전 검증이 다시 섞이면 예외 누락과 저장 경로 재작업 위험이 커집니다.",
            "workflow": "승인 단계와 예외 처리 경계가 다시 섞이면 승인 누락과 운영 혼선 위험이 커집니다.",
            "state_transition": "상태 전이 판단이 처리 흐름과 다시 섞이면 예외 전이 누락과 상태 정합성 오류가 발생할 수 있습니다.",
            "access_control": "권한 판단과 처리 경로가 다시 섞이면 승인 주체와 부서 책임이 흔들릴 수 있습니다.",
            "query_filter": "조회 조건과 정렬 규칙이 다시 화면과 SQL에 흩어지면 결과 정합성이 흔들릴 수 있습니다.",
            "amount_threshold": "금액 한도와 후속 처리 경계가 다시 섞이면 한도 초과 처리 결과가 일관되지 않을 수 있습니다.",
        }.get(axis, "")
        if standardized:
            return standardized
        return str((improvement.risks or ["입력 자산이 제한적이므로 판단 초안으로 유지합니다."])[0] or "").strip()

    def _outline_next_step(
        self,
        *,
        prepared: Any,
        decisions: DecisionArtifacts,
        improvement: ImprovementArtifacts,
        grounding_profile: dict[str, Any],
    ) -> str:
        if bool(grounding_profile.get("insufficient_grounding")):
            return "누락된 레거시 코드, 화면, SQL, 스키마, 런타임 근거를 우선 확보합니다."
        concept = self._outline_concept(prepared)
        axis = self._outline_axis(decisions)
        standardized = {
            "validation": f"{concept} 관련 차단 조건, 저장 전 검증, 예외 처리 분리 후보를 식별합니다.",
            "workflow": f"{concept} 관련 승인 트리거, 승인 단계, 예외 승인 경계를 분리 후보로 정리합니다.",
            "state_transition": f"{concept} 관련 상태 전이, 처리 가능 상태, 예외 전이 규칙을 분리 후보로 정리합니다.",
            "access_control": f"{concept} 관련 승인 주체, 권한 규칙, 부서 책임 경계를 분리 후보로 정리합니다.",
            "query_filter": f"{concept} 관련 조회 조건, 필터 조합, 정렬 규칙의 책임 경계를 식별합니다.",
            "amount_threshold": f"{concept} 관련 금액 구간, 한도 정책, 고액 처리 경계를 분리 후보로 정리합니다.",
        }.get(axis, "")
        if standardized:
            return standardized
        if improvement.execution_plan:
            next_step = str(improvement.execution_plan[0].goal or "").strip()
            if next_step:
                return next_step
        if improvement.verification_checkpoints:
            next_step = str(improvement.verification_checkpoints[0].item or "").strip()
            if next_step:
                return next_step
        return "누락된 레거시 코드 또는 운영 자산을 먼저 확보합니다."

    def _outline_axis(self, decisions: DecisionArtifacts) -> str:
        return str(
            decisions.narrative_axis
            or decisions.template_judgment
            or decisions.primary_judgment
            or decisions.selected_narrative_judgment
            or ""
        ).strip()

    def _outline_concept(self, prepared: Any) -> str:
        concept_map = {
            "order": "주문",
            "orders": "주문",
            "report": "보고서",
            "reports": "보고서",
            "request": "요청",
            "requests": "요청",
            "approval": "결재",
            "approvals": "결재",
            "claim": "청구",
            "claims": "청구",
            "policy": "권한",
            "policies": "권한",
            "user": "사용자",
            "users": "사용자",
        }
        concepts = list(getattr(getattr(prepared, "signals", None), "concepts", []) or [])
        for item in concepts:
            text = str(item or "").strip()
            if text:
                return concept_map.get(text.lower(), text)
        goal = str(getattr(prepared, "goal", "") or "").strip()
        if goal:
            normalized = re.sub(r"\s+", " ", goal).strip()
            return normalized[:18]
        return "기능"

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
        governance = result.extensions.get("decision_governance", {}) if isinstance(result.extensions, dict) else {}
        grounding = governance.get("recommendation_grounding", {}) if isinstance(governance, dict) else {}
        level = str((grounding or {}).get("level") or "")
        if level == "grounded":
            return result
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
