from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from mellow_link.modules.rebuild_assistant.schemas import (
    CanonicalFunctionClassification,
    CanonicalRebuildPayload,
    CanonicalRequestContext,
    ExecutionPlanWeek,
    MissingContextItem,
    NarrativeValidationMetadata,
    StructuredRebuildResult,
)

from .narrative_fallback import DeterministicNarrativeBuilder
from .runtime_contracts import assert_stage_action, snapshot_stage_control
from .template_support import TemplateSupport
from .schemas import (
    DecisionArtifacts,
    DecisionSummary,
    DiagnosisArtifacts,
    ExecutionStage,
    ImprovementArtifacts,
    StructureAnalysisResult,
    StructuredRefactoringResult,
)


class ResultPackager:
    NARRATIVE_PROMPT_VERSION = "phase2.0-single-shot-narrative-v1"

    def __init__(self) -> None:
        self.narrative_builder = DeterministicNarrativeBuilder()
        self.template_support = TemplateSupport()

    def package(
        self,
        prepared: Any,
        structure: StructureAnalysisResult,
        diagnosis: DiagnosisArtifacts,
        decisions: DecisionArtifacts,
        improvement: ImprovementArtifacts,
        legacy_service: Any,
        *,
        stage_control: dict[str, object] | None = None,
        validation_result: dict[str, Any] | None = None,
    ) -> StructuredRebuildResult:
        stage_control_snapshot = snapshot_stage_control(
            assert_stage_action(
                stage_control or getattr(prepared, "stage_control", None),
                expected_stage="planning",
                action="package_result",
                goal=str(getattr(prepared, "goal", "") or ""),
            ),
            goal=str(getattr(prepared, "goal", "") or ""),
        )
        decision_engine_guard_applied = bool(decisions.synthetic_signal_detected)
        decisions, packager_guard_applied = self._apply_decision_governance(decisions, diagnosis)
        confidence = legacy_service.estimate_confidence(prepared)
        grounding_profile = self._build_recommendation_grounding_profile(prepared, diagnosis, decisions, confidence)
        constraint_filters = self._constraint_filters(prepared)
        diagnosis = self._apply_family_diagnosis_surface_templates(
            prepared=prepared,
            diagnosis=diagnosis,
            decisions=decisions,
        )
        improvement = self._apply_recommendation_grounding(improvement, grounding_profile)
        improvement = self._apply_family_surface_templates(
            prepared=prepared,
            diagnosis=diagnosis,
            decisions=decisions,
            improvement=improvement,
        )
        diagnosis = self._degrade_unverified_claims(diagnosis)
        context_linkage = self._build_context_linkage(prepared, diagnosis)
        governance_extension = self._build_governance_extension(
            prepared=prepared,
            diagnosis=diagnosis,
            decisions=decisions,
            improvement=improvement,
            family_classification=decisions.family_classification,
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
        question_axis = self.template_support.resolve_question_axis(
            prepared,
            family=str(getattr(decisions.family_classification, "family", "") or "").strip(),
            narrative_axis=str(decisions.narrative_axis or decisions.selected_narrative_judgment or "").strip(),
        )
        judgment_canvas = self._build_judgment_canvas(
            prepared=prepared,
            diagnosis=diagnosis,
            decisions=decisions,
            improvement=improvement,
            question_axis=question_axis,
        )
        self._validate_judgment_canvas(judgment_canvas)
        authoritative = StructuredRefactoringResult(
            structure_snapshot=structure.structure_snapshot.model_copy(update={"feature_slices": feature_slices}),
            diagnosis_report=diagnosis.diagnosis_report,
            decision_summary=decisions.decision_summary,
            improvement_plan_bundle=improvement.improvement_plan_bundle,
            judgment_canvas=deepcopy(judgment_canvas),
            stage_control=stage_control_snapshot,
            validation_result=deepcopy(validation_result or {"status": "pass", "failure_types": [], "retry_hint": ""}),
            appendix={
                "evidence_index": [item.model_dump() for item in diagnosis.evidence_index],
                "context_linkage": context_linkage,
            },
        )
        result = StructuredRebuildResult(
            context_id=context_linkage["context_id"],
            input_fingerprint=context_linkage["input_fingerprint"],
            safe_bundle_id=context_linkage["safe_bundle_id"],
            evidence_refs=context_linkage["evidence_refs"],
            stage_control=authoritative.stage_control,
            validation_result=authoritative.validation_result,
            primary_judgment=decisions.primary_judgment,
            template_judgment=decisions.template_judgment or decisions.primary_judgment,
            structural_judgment=decisions.structural_judgment,
            narrative_axis=decisions.narrative_axis or decisions.selected_narrative_judgment,
            question_axis=question_axis,
            feature_signal_mode=decisions.feature_signal_mode,
            family_classification=decisions.family_classification,
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
            assumptions=decisions.assumptions,
            extensions=extensions,
            structure_snapshot=authoritative.structure_snapshot.model_dump(),
            diagnosis_report=authoritative.diagnosis_report.model_dump(),
            decision_summary=authoritative.decision_summary.model_dump(),
            improvement_plan_bundle=authoritative.improvement_plan_bundle.model_dump(),
            judgment_canvas=authoritative.judgment_canvas,
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
            "prompt_version": self.NARRATIVE_PROMPT_VERSION,
            "validation_passed": False,
            "failure_reason": "llm_not_invoked",
            "axis": narrative_bundle.narrative_axis,
            "llm_invoked": False,
            "llm_call_count": 0,
            "fallback_used": True,
            "slim_payload_hash": "",
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
        question_guard_payload = self._build_question_guard_payload(prepared)
        if question_guard_payload:
            merged_extensions["question_guard"] = question_guard_payload
        guarded_report_questions = self._guarded_report_questions(prepared, narrative_bundle.report_questions)
        result = result.model_copy(
            update={
                "narrative_axis": narrative_bundle.narrative_axis or result.narrative_axis,
                "report_purpose": narrative_bundle.report_purpose,
                "report_scope": narrative_bundle.report_scope,
                "report_questions": guarded_report_questions,
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
        result_appendix = deepcopy(result.appendix)
        result_appendix["context_linkage"] = context_linkage
        if question_guard_payload:
            result_appendix["question_guard"] = deepcopy(question_guard_payload)
        result = result.model_copy(
            update={
                "context_id": context_linkage["context_id"],
                "input_fingerprint": context_linkage["input_fingerprint"],
                "safe_bundle_id": context_linkage["safe_bundle_id"],
                "evidence_refs": context_linkage["evidence_refs"],
                "stage_control": stage_control_snapshot,
                "validation_result": deepcopy(validation_result or {"status": "pass", "failure_types": [], "retry_hint": ""}),
                "judgment_canvas": deepcopy(judgment_canvas),
                "appendix": result_appendix,
                "canonical_payload": CanonicalRebuildPayload(
                    request_context=CanonicalRequestContext(
                        goal=str(getattr(prepared, "goal", "") or ""),
                        constraints=list(getattr(prepared, "constraints", []) or []),
                        scope_limited=bool(getattr(prepared, "scope_limited", False)),
                        question_axis=question_axis,
                        primary_feature_mode=str(getattr(getattr(prepared, "signals", None), "primary_feature_mode", "") or ""),
                        secondary_feature_mode=str(getattr(getattr(prepared, "signals", None), "secondary_feature_mode", "") or ""),
                        concept_signals=list(getattr(getattr(prepared, "signals", None), "concepts", []) or []),
                        accounting_asset_name=str(getattr(prepared, "accounting_asset_name", "") or ""),
                    ),
                    function_classification=CanonicalFunctionClassification(
                        primary_judgment=result.primary_judgment,
                        template_judgment=result.template_judgment,
                        structural_judgment=result.structural_judgment,
                        narrative_axis=result.narrative_axis,
                        feature_signal_mode=result.feature_signal_mode,
                        pattern_candidates=list(result.pattern_candidates),
                    ),
                    input_family_classification=result.family_classification,
                    structure_snapshot=deepcopy(result.structure_snapshot),
                    diagnosis_report=deepcopy(result.diagnosis_report),
                    decision_summary=deepcopy(result.decision_summary),
                    analysis_summary=list(result.analysis_summary),
                    core_business_rules=list(result.core_business_rules),
                    grounded_business_rules=list(result.grounded_business_rules),
                    decision_items=list(result.decision_items),
                    retained_contracts=list(result.retained_contracts),
                    design_options=list(result.design_options),
                    recommended_option=result.recommended_option,
                    execution_plan=list(result.execution_plan),
                    recommended_directions=list(result.recommended_directions),
                    risks=list(result.risks),
                    missing_context_details=list(result.missing_context_details),
                    appendix=deepcopy(result_appendix),
                ),
                "narrative_metadata": NarrativeValidationMetadata(
                    source="deterministic_fallback",
                    fields_rewritten=[],
                    model="",
                    prompt_version=self.NARRATIVE_PROMPT_VERSION,
                    validation_passed=False,
                    failure_reason="llm_not_invoked",
                    axis=result.narrative_axis,
                    llm_invoked=False,
                    llm_call_count=0,
                    fallback_used=True,
                    slim_payload_hash="",
                ),
                "narrative_layer": None,
            }
        )
        return legacy_service._sanitize_structured_result(result)

    def _build_judgment_canvas(
        self,
        *,
        prepared: Any,
        diagnosis: DiagnosisArtifacts,
        decisions: DecisionArtifacts,
        improvement: ImprovementArtifacts,
        question_axis: str,
    ) -> dict[str, Any]:
        decision_records = list(decisions.decision_summary.decisions or [])
        top_decision = decision_records[0] if decision_records else None
        issue_map = {
            item.issue_id: item
            for item in list(getattr(diagnosis.diagnosis_report, "issues", []) or [])
        }
        top_issue = issue_map.get(top_decision.issue_ids[0], None) if top_decision and top_decision.issue_ids else None
        evidence_fallback = self._canvas_evidence_refs(
            diagnosis=diagnosis,
            decision=top_decision,
            issue=top_issue,
        )
        design_options = list(improvement.design_options or [])
        recommended_option = improvement.recommended_option
        option_payloads = []
        for option in design_options[:3]:
            option_payloads.append(
                {
                    "title": str(option.name or "").strip() or "대안",
                    "summary": str(option.structure_summary or option.selection_reason or "").strip() or "구조 대안을 비교합니다.",
                    "evidence_refs": self._canvas_evidence_refs(
                        diagnosis=diagnosis,
                        decision=top_decision,
                        issue=top_issue,
                    ),
                }
            )
        if not option_payloads:
            option_payloads.append(
                {
                    "title": str(getattr(recommended_option, "name", "") or decisions.decision_summary.recommended_strategy or "권장안"),
                    "summary": str(getattr(recommended_option, "structure_summary", "") or "현재 근거에서 가장 보수적인 개선안을 유지합니다.").strip(),
                    "evidence_refs": list(evidence_fallback),
                }
            )

        criteria_payloads = [
            {
                "title": "근거 충실도",
                "summary": "결정은 issue evidence와 구조 근거가 연결되는 경우에만 유지합니다.",
                "evidence_refs": list(evidence_fallback),
            },
            {
                "title": "기존 계약 보존",
                "summary": "기존 DB/업무 계약과 충돌하지 않는 방향을 우선 선택합니다.",
                "evidence_refs": self._canvas_evidence_refs(
                    diagnosis=diagnosis,
                    decision=top_decision,
                    issue=top_issue,
                    preferred_refs=self._retained_contract_evidence_refs(diagnosis),
                ),
            },
        ]

        conclusion_text = str(
            getattr(recommended_option, "selection_reason", "")
            or getattr(top_decision, "rationale", "")
            or decisions.decision_summary.recommended_strategy
            or "현재 근거에서 가장 안정적인 개선 방향을 우선 적용합니다."
        ).strip()
        risk_text = str(
            (improvement.risks[0] if improvement.risks else "")
            or (diagnosis.missing_context_details[0].reason if diagnosis.missing_context_details else "")
            or "근거가 얇은 지점은 후속 검증 없이 확정하면 안 됩니다."
        ).strip()

        return {
            "situation_purpose": {
                "text": str(getattr(prepared, "goal", "") or "").strip() or "현재 판단 목적을 정리합니다.",
                "evidence_refs": list(evidence_fallback),
            },
            "problem_definition": {
                "text": str(getattr(top_issue, "summary", "") or (diagnosis.analysis_summary[0] if diagnosis.analysis_summary else "핵심 구조 문제를 정의합니다.")).strip(),
                "evidence_refs": self._canvas_evidence_refs(
                    diagnosis=diagnosis,
                    decision=top_decision,
                    issue=top_issue,
                ),
            },
            "judgment_question": {
                "text": str(question_axis or "어떤 개선 전략을 우선 적용해야 하는가?").strip(),
                "evidence_refs": list(evidence_fallback),
            },
            "options": option_payloads,
            "criteria": criteria_payloads,
            "conclusion": {
                "text": conclusion_text,
                "evidence_refs": self._canvas_evidence_refs(
                    diagnosis=diagnosis,
                    decision=top_decision,
                    issue=top_issue,
                ),
            },
            "risk": {
                "text": risk_text,
                "evidence_refs": self._canvas_evidence_refs(
                    diagnosis=diagnosis,
                    decision=top_decision,
                    issue=top_issue,
                ),
            },
        }

    def _validate_judgment_canvas(self, canvas: dict[str, Any]) -> None:
        required_fields = (
            "situation_purpose",
            "problem_definition",
            "judgment_question",
            "options",
            "criteria",
            "conclusion",
            "risk",
        )
        missing_fields = [field for field in required_fields if field not in canvas]
        if missing_fields:
            raise ValueError(f"judgment_canvas missing fields: {', '.join(missing_fields)}")
        for field in ("situation_purpose", "problem_definition", "judgment_question", "conclusion", "risk"):
            payload = canvas.get(field)
            evidence_refs = list(payload.get("evidence_refs") or []) if isinstance(payload, dict) else []
            if not evidence_refs:
                raise ValueError(f"judgment_canvas field '{field}' requires at least one evidence_ref")
        for field in ("options", "criteria"):
            payload = canvas.get(field)
            if not isinstance(payload, list) or not payload:
                raise ValueError(f"judgment_canvas field '{field}' must be a non-empty list")
            if any(not list(item.get("evidence_refs") or []) for item in payload if isinstance(item, dict)):
                raise ValueError(f"judgment_canvas field '{field}' requires evidence_refs for every item")

    def _guarded_report_questions(self, prepared: Any, fallback_questions: list[str]) -> list[str]:
        summary = getattr(prepared, "question_guard_summary", None)
        selected = list(getattr(summary, "selected_questions", []) or [])
        if selected:
            return selected[:4]
        return list(fallback_questions or [])

    def _build_question_guard_payload(self, prepared: Any) -> dict[str, Any]:
        candidates = list(getattr(prepared, "source_question_candidates", []) or [])
        blocked = list(getattr(prepared, "blocked_user_questions", []) or [])
        review = list(getattr(prepared, "review_user_questions", []) or [])
        summary = getattr(prepared, "question_guard_summary", None)
        if not candidates and not blocked and not review and summary is None:
            return {}
        payload: dict[str, Any] = {
            "raw_goal": str(getattr(prepared, "raw_goal", "") or ""),
            "raw_constraints": list(getattr(prepared, "raw_constraints", []) or []),
            "effective_goal": str(getattr(prepared, "goal", "") or ""),
            "effective_constraints": list(getattr(prepared, "constraints", []) or []),
            "source_question_candidates": [
                item.model_dump() if hasattr(item, "model_dump") else dict(item)
                for item in candidates
            ],
            "blocked_user_questions": [
                item.model_dump() if hasattr(item, "model_dump") else dict(item)
                for item in blocked
            ],
            "review_user_questions": [
                item.model_dump() if hasattr(item, "model_dump") else dict(item)
                for item in review
            ],
        }
        if summary is not None:
            payload["question_guard_summary"] = (
                summary.model_dump() if hasattr(summary, "model_dump") else dict(summary)
            )
        return payload

    def _canvas_evidence_refs(
        self,
        *,
        diagnosis: DiagnosisArtifacts,
        decision=None,
        issue=None,
        preferred_refs: list[str] | None = None,
    ) -> list[str]:
        refs: list[str] = []
        refs.extend(list(preferred_refs or []))
        refs.extend(list(getattr(decision, "evidence_ids", []) or []))
        refs.extend(list(getattr(issue, "evidence_ids", []) or []))
        if not refs:
            refs.extend(
                str(getattr(item, "evidence_id", "") or "").strip()
                for item in list(diagnosis.evidence_index or [])[:3]
            )
        deduped = [item for item in dict.fromkeys(ref for ref in refs if str(ref or "").strip())]
        if not deduped:
            synthetic_refs: list[str] = []
            issue_id = str(getattr(issue, "issue_id", "") or "").strip()
            if issue_id:
                synthetic_refs.append(f"issue:{issue_id}")
            for decision_issue_id in list(getattr(decision, "issue_ids", []) or []):
                normalized_issue_id = str(decision_issue_id or "").strip()
                if normalized_issue_id:
                    synthetic_refs.append(f"issue:{normalized_issue_id}")
            if not synthetic_refs:
                for item in list(getattr(getattr(diagnosis, "diagnosis_report", None), "issues", []) or [])[:2]:
                    normalized_issue_id = str(getattr(item, "issue_id", "") or "").strip()
                    if normalized_issue_id:
                        synthetic_refs.append(f"issue:{normalized_issue_id}")
            if not synthetic_refs and list(getattr(diagnosis, "analysis_summary", []) or []):
                synthetic_refs.append("analysis:summary")
            if not synthetic_refs and list(getattr(diagnosis, "core_business_rules", []) or []):
                synthetic_refs.append("analysis:core_rules")
            deduped = [item for item in dict.fromkeys(synthetic_refs) if item]
        return deduped[:3]

    def _retained_contract_evidence_refs(self, diagnosis: DiagnosisArtifacts) -> list[str]:
        refs: list[str] = []
        for item in list(diagnosis.retained_contracts or []):
            for evidence in list(getattr(item, "evidence", []) or []):
                evidence_id = str(getattr(evidence, "evidence_id", "") or "").strip()
                if evidence_id:
                    refs.append(evidence_id)
        return list(dict.fromkeys(refs))[:3]

    def _build_context_linkage(self, prepared: Any, diagnosis: DiagnosisArtifacts) -> dict[str, Any]:
        context = getattr(prepared, "analysis_context", None)
        evidence_refs = [item.evidence_id for item in diagnosis.evidence_index]
        if context is not None:
            context_refs = [item.evidence_id for item in context.evidence_index]
            evidence_refs = context_refs or evidence_refs
        # v1 evidence_refs are evidence_id[] and may stay empty when evidence has not
        # been normalized enough to support a specific claim linkage.
        if context is None:
            return {
                "context_id": "",
                "input_fingerprint": "",
                "safe_bundle_id": str(getattr(getattr(prepared, "safe_bundle", None), "bundle_id", "") or ""),
                "evidence_refs": evidence_refs,
            }
        return {
            "context_id": context.context_id,
            "input_fingerprint": context.run.input_fingerprint,
            "safe_bundle_id": context.trust.safe_bundle_id,
            "evidence_refs": evidence_refs,
        }

    def _degrade_unverified_claims(self, diagnosis: DiagnosisArtifacts) -> DiagnosisArtifacts:
        degraded = False
        rules = []
        for rule in diagnosis.grounded_business_rules:
            has_evidence = bool(getattr(rule, "evidence", []) or [])
            confidence = str(getattr(rule, "confidence", "") or "").strip()
            if has_evidence or confidence != "확정":
                rules.append(rule)
                continue
            degraded = True
            reason = str(getattr(rule, "confidence_reason", "") or "").strip()
            if "missing_decision_driving_evidence" not in reason:
                reason = (
                    f"{reason} / missing_decision_driving_evidence"
                    if reason
                    else "missing_decision_driving_evidence"
                )
            rules.append(
                rule.model_copy(
                    update={
                        "confidence": "가정",
                        "confidence_reason": reason,
                        "needs_verification": True,
                    }
                )
            )
        if not degraded:
            return diagnosis
        missing_context = list(diagnosis.missing_context_details or [])
        if not any(item.reason == "missing_decision_driving_evidence" for item in missing_context):
            missing_context.append(
                MissingContextItem(
                    required_material="결정 근거 evidence",
                    reason="missing_decision_driving_evidence",
                )
            )
        # Degradation is applied at claim/decision/plan item level and is not propagated
        # as a whole-run failure.
        return diagnosis.model_copy(
            update={
                "grounded_business_rules": rules,
                "missing_context_details": missing_context,
            }
        )

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
                issue_summary=str(issue.summary or ""),
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
        issue_summary: str,
        evidence_ids: list[str],
        evidence_map: dict[str, Any],
        asset_text_map: dict[str, str],
    ) -> dict[str, Any] | None:
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
            observed = self._extract_observed_pattern_snippet(
                source_text,
                str(evidence.excerpt or ""),
                locator=str(evidence.locator or ""),
            )
            expected_pattern = self._build_grounded_expected_pattern(
                detector_id=detector_id,
                asset_type=str(evidence.asset_type or ""),
                observed=observed,
            )
            if not self._is_meaningful_pattern_comparison(observed, expected_pattern):
                continue
            return {
                "type": "before_after",
                "file": str(evidence.asset_name or evidence.asset_id or "-"),
                "detector_id": detector_id,
                "issue_summary": issue_summary,
                "difference_summary": self._difference_summary(detector_id=detector_id),
                "observed": observed,
                "expected_pattern": expected_pattern,
            }
        return None

    def _build_grounded_expected_pattern(self, *, detector_id: str, asset_type: str, observed: str) -> str:
        lowered_asset_type = str(asset_type or "").strip().lower()
        grounded_pattern = ""
        if lowered_asset_type == "sql":
            grounded_pattern = self._ground_sql_expected_pattern(observed)
        else:
            grounded_pattern = self._ground_source_expected_pattern(
                detector_id=detector_id,
                observed=observed,
            )
        return grounded_pattern or self._expected_pattern_template(
            detector_id=detector_id,
            asset_type=asset_type,
        )

    def _ground_source_expected_pattern(self, *, detector_id: str, observed: str) -> str:
        lines = [line.rstrip() for line in str(observed or "").replace("\r\n", "\n").split("\n") if line.strip()]
        if not lines:
            return ""

        class_line = next((line for line in lines if re.match(r"^\s*class\s+[A-Za-z_][\w]*", line)), "")
        def_line = next((line for line in lines if re.match(r"^\s*def\s+[A-Za-z_][\w]*\s*\(", line)), "")
        if not def_line:
            return ""

        signature_match = re.match(
            r"^(?P<indent>\s*)def\s+(?P<name>[A-Za-z_][\w]*)\((?P<args>.*)\):\s*$",
            def_line,
        )
        if not signature_match:
            return ""

        indent = signature_match.group("indent")
        body_indent = f"{indent}    "
        function_name = signature_match.group("name")
        helper_base = self._helper_base_name(function_name)
        args = [item.strip() for item in signature_match.group("args").split(",") if item.strip()]
        normalized_args = [item.split("=", 1)[0].strip() for item in args]
        call_args = [item for item in normalized_args if item not in {"self", "cls"}]
        repository_arg = next(
            (
                item
                for item in call_args
                if re.search(r"(repo|repository|dao|store|storage|gateway)$", item, flags=re.IGNORECASE)
            ),
            "",
        )
        business_args = [item for item in call_args if item != repository_arg]
        primary_input = next(
            (
                item
                for item in business_args
                if item.lower() not in {"retry_flag", "note_text", "ctx", "context", "request", "view_model"}
            ),
            business_args[0] if business_args else "",
        )
        last_return_expression = ""
        for line in reversed(lines):
            stripped = line.strip()
            if stripped.startswith("return "):
                last_return_expression = stripped[len("return ") :].strip()
                break

        normalized_input_call = ", ".join(business_args or call_args or ["input_data"])
        command_input_call = ", ".join(business_args or call_args or ["input_data"])
        result_call_args = "command"
        if repository_arg:
            result_call_args = f"{result_call_args}, {repository_arg}"

        payload_target = primary_input or (business_args[0] if business_args else "")
        working_value_name = payload_target or "input_data"

        if detector_id == "query_filter_leak":
            body_lines = [
                f"{body_indent}filters = normalize_{helper_base}_filters({primary_input or 'params'})",
                f"{body_indent}query = build_{helper_base}_query(filters)",
                f"{body_indent}return run_{helper_base}_query(query)",
            ]
        elif detector_id == "validation_guard_leak":
            body_lines = [
                f"{body_indent}validation = validate_{helper_base}_input({normalized_input_call})",
                f"{body_indent}if not validation.valid:",
                f"{body_indent}    return validation.errors",
                f"{body_indent}return {self._preferred_payload_return_expression(last_return_expression, source_name=payload_target, replacement='validation.payload', repository_arg=repository_arg, fallback_expression=f'apply_{helper_base}(validation.payload)')}",
            ]
        elif detector_id == "state_transition_leak":
            body_lines = [
                f"{body_indent}next_state = resolve_{helper_base}_state({normalized_input_call})",
                f"{body_indent}if not next_state:",
                f"{body_indent}    raise TransitionBlocked()",
                f"{body_indent}return {self._preferred_payload_return_expression(last_return_expression, source_name=payload_target, replacement='next_state', repository_arg=repository_arg, fallback_expression=f'save_{helper_base}_state(next_state)')}",
            ]
        elif detector_id == "boundary_mismatch":
            body_lines = [
                f"{body_indent}policy_result = evaluate_{helper_base}_policy({normalized_input_call})",
                f"{body_indent}if not policy_result.allowed:",
                f"{body_indent}    return policy_result",
                f"{body_indent}return {self._preferred_payload_return_expression(last_return_expression, source_name=payload_target, replacement='policy_result.payload', repository_arg=repository_arg, fallback_expression=f'save_{helper_base}(policy_result.payload)')}",
            ]
        elif detector_id == "rule_scatter":
            body_lines = [
                f"{body_indent}rule_result = evaluate_{helper_base}_rules({normalized_input_call})",
                f"{body_indent}if not rule_result.allowed:",
                f"{body_indent}    return rule_result",
                f"{body_indent}return {self._preferred_payload_return_expression(last_return_expression, source_name=payload_target, replacement='rule_result.payload', repository_arg=repository_arg, fallback_expression=f'execute_{helper_base}(rule_result.payload)')}",
            ]
        elif detector_id == "duplicate_logic_candidate":
            body_lines = [
                f"{body_indent}{working_value_name} = normalize_{helper_base}_input({normalized_input_call})",
                f"{body_indent}if not {working_value_name}.valid:",
                f"{body_indent}    return {working_value_name}.errors",
                f"{body_indent}return {self._preferred_payload_return_expression(last_return_expression, source_name=payload_target, replacement=f'{working_value_name}.payload', repository_arg=repository_arg, fallback_expression=f'apply_{helper_base}({working_value_name}.payload)')}",
            ]
        else:
            body_lines = [
                f"{body_indent}command = build_{helper_base}_command({command_input_call})",
                f"{body_indent}result = execute_{helper_base}({result_call_args})",
                f"{body_indent}return present_{helper_base}(result)",
            ]

        rendered_lines = []
        if class_line:
            rendered_lines.append(class_line)
        rendered_lines.append(def_line)
        rendered_lines.extend(body_lines)
        return "\n".join(rendered_lines).strip()

    def _ground_sql_expected_pattern(self, observed: str) -> str:
        lines = [line.rstrip() for line in str(observed or "").replace("\r\n", "\n").split("\n") if line.strip()]
        if not lines:
            return ""
        has_sql_context = any(
            re.match(r"^\s*(select|from|where|join|left join|right join|inner join|order by|group by)\b", line, flags=re.IGNORECASE)
            for line in lines
        )
        if not has_sql_context:
            return ""

        rendered_lines: list[str] = []
        if not any(re.match(r"^\s*select\b", line, flags=re.IGNORECASE) for line in lines) and any(
            re.match(r"^\s*from\b", line, flags=re.IGNORECASE) for line in lines
        ):
            rendered_lines.append("SELECT *")

        used_params: set[str] = set()
        for line in lines:
            rendered_lines.append(self._parameterize_sql_predicate_line(line, used_params=used_params))
        return "\n".join(rendered_lines).strip()

    def _parameterize_sql_predicate_line(self, line: str, *, used_params: set[str]) -> str:
        match = re.match(
            r"^(?P<indent>\s*)(?P<keyword>WHERE|AND|OR)\s+(?P<lhs>[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)\s*(?P<op>=|<>|!=|>=|<=|>|<|LIKE)\s*(?P<rhs>.+?)(?P<suffix>\s*(?:--.*)?[;,]?\s*)$",
            str(line or ""),
            flags=re.IGNORECASE,
        )
        if not match:
            return line

        rhs = str(match.group("rhs") or "").strip()
        if rhs.startswith(":") or re.fullmatch(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*", rhs):
            return line

        base_name = self._helper_base_name(match.group("lhs").split(".")[-1] or "value")
        if not base_name:
            base_name = "value"
        unique_name = base_name
        counter = 2
        while unique_name in used_params:
            unique_name = f"{base_name}_{counter}"
            counter += 1
        used_params.add(unique_name)
        return (
            f"{match.group('indent')}{match.group('keyword').upper()} {match.group('lhs')} "
            f"{match.group('op')} :{unique_name}{match.group('suffix')}"
        )

    def _helper_base_name(self, raw_name: str) -> str:
        normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(raw_name or "").strip())
        normalized = re.sub(r"[^A-Za-z0-9_]+", "_", normalized)
        normalized = re.sub(r"_+", "_", normalized).strip("_").lower()
        return normalized or "flow"

    def _rewrite_return_expression(self, expression: str, source_name: str, replacement: str) -> str:
        normalized_expression = str(expression or "").strip()
        if not normalized_expression:
            return ""
        if not source_name:
            return normalized_expression
        return re.sub(
            rf"\b{re.escape(source_name)}\b",
            replacement,
            normalized_expression,
        )

    def _preferred_payload_return_expression(
        self,
        expression: str,
        *,
        source_name: str,
        replacement: str,
        repository_arg: str,
        fallback_expression: str,
    ) -> str:
        rewritten = self._rewrite_return_expression(expression, source_name, replacement).strip()
        if rewritten and replacement in rewritten:
            return rewritten
        if repository_arg:
            return f"{repository_arg}.save({replacement})"
        return fallback_expression

    def _source_text_map(self, prepared: Any) -> dict[str, str]:
        safe_bundle = getattr(prepared, "safe_bundle", None)
        if safe_bundle is None:
            context = getattr(prepared, "analysis_context", None)
            if context is None:
                return {}
            result: dict[str, str] = {}
            for source in getattr(context, "source_blocks", []) or []:
                asset_id = str(getattr(source, "asset_id", "") or "").strip()
                asset_name = str(getattr(source, "asset_name", "") or getattr(source, "locator", "") or "").strip()
                content = str(getattr(source, "content", "") or "")
                if not content.strip():
                    continue
                if asset_id:
                    result[asset_id] = content
                if asset_name:
                    result[asset_name] = content
                    result[asset_name.lower()] = content
            return result
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

    def _extract_observed_pattern_snippet(self, source_text: str, excerpt: str, *, locator: str = "") -> str:
        normalized_lines = [line.rstrip() for line in str(source_text or "").replace("\r\n", "\n").split("\n")]
        excerpt_lines = [line.strip() for line in str(excerpt or "").replace("\r\n", "\n").split("\n") if line.strip()]
        if not normalized_lines:
            return ""
        index = self._line_index_from_locator(locator, line_count=len(normalized_lines))
        if index < 0:
            index = self._line_index_from_anchor(normalized_lines, excerpt_lines)
        if index < 0:
            index = self._line_index_from_token_overlap(normalized_lines, excerpt_lines)
        if index < 0:
            return "\n".join([line for line in normalized_lines[:6] if line.strip()]).strip()
        start = max(0, index - 2)
        end = min(len(normalized_lines), index + 4)
        snippet_lines = normalized_lines[start:end]
        trimmed_lines = [line for line in snippet_lines if line.strip()]
        return "\n".join(trimmed_lines[:6]).strip()

    def _line_index_from_locator(self, locator: str, *, line_count: int) -> int:
        match = re.search(r"(?:^|:)line:(\d+)\b", str(locator or ""), flags=re.IGNORECASE)
        if not match:
            return -1
        try:
            line_no = int(match.group(1))
        except ValueError:
            return -1
        if line_no < 1 or line_no > line_count:
            return -1
        return line_no - 1

    def _line_index_from_anchor(self, normalized_lines: list[str], excerpt_lines: list[str]) -> int:
        anchor = excerpt_lines[0] if excerpt_lines else ""
        if not anchor:
            return -1
        lowered_anchor = anchor.lower()
        for current_index, line in enumerate(normalized_lines):
            if lowered_anchor in line.lower():
                return current_index
        return -1

    def _line_index_from_token_overlap(self, normalized_lines: list[str], excerpt_lines: list[str]) -> int:
        excerpt_text = " ".join(excerpt_lines).lower()
        tokens = [
            token
            for token in re.findall(r"[a-z0-9_]{3,}", excerpt_text)
            if token not in {"return", "class", "false", "true", "null", "none"}
        ]
        if not tokens:
            return -1
        best_index = -1
        best_score = 0
        for current_index, line in enumerate(normalized_lines):
            lowered_line = line.lower()
            score = sum(1 for token in tokens if token in lowered_line)
            if score > best_score:
                best_index = current_index
                best_score = score
        minimum_score = 1 if len(tokens) <= 2 else 2
        return best_index if best_score >= minimum_score else -1

    def _difference_summary(self, *, detector_id: str) -> list[str]:
        mapping = {
            "query_filter_leak": [
                "조회 조건이 여러 경로에 분산되어 있음",
                "권장 구조는 조회 조건 정규화와 SQL 적용을 조회 계층으로 모음",
                "필터 조합 규칙이 화면이나 SQL 문자열에 직접 남지 않음",
            ],
            "validation_guard_leak": [
                "validation이 저장 또는 처리 경로에 섞여 있음",
                "권장 구조는 validation을 선행 단계로 분리함",
                "실행 단계는 검증을 통과한 입력만 처리함",
            ],
            "state_transition_leak": [
                "상태 전이 판단과 저장 호출이 한 경로에 묶여 있음",
                "권장 구조는 상태 전이 정책과 저장 단계를 분리함",
                "허용된 다음 상태만 persistence 계층으로 전달함",
            ],
            "ui_data_access_coupling": [
                "화면 계층이 조회 또는 저장 규칙을 직접 알고 있음",
                "권장 구조는 UI를 service 호출과 화면 표현에만 집중시킴",
                "데이터 접근과 command 처리는 service 또는 repository로 분리함",
            ],
            "boundary_mismatch": [
                "정책 판단과 persistence 의존이 한 경로에 묶여 있음",
                "권장 구조는 boundary policy와 저장 책임을 분리함",
                "허용 여부 판단 결과만 저장 계층으로 전달함",
            ],
            "rule_scatter": [
                "업무 규칙이 여러 컴포넌트에 흩어져 있음",
                "권장 구조는 규칙 평가를 공통 rule set으로 모음",
                "실행 서비스는 평가 결과만 사용해 처리함",
            ],
            "duplicate_logic_candidate": [
                "정규화 또는 검증 흐름이 중복 구현되어 있음",
                "권장 구조는 공통 normalize 경로로 입력 처리를 통합함",
                "서비스는 정규화된 payload만 받아 실행함",
            ],
            "mixed_responsibility": [
                "하나의 구성요소에 validation, business, persistence 책임이 함께 있음",
                "권장 구조는 책임을 계층별로 분리함",
                "service 책임을 줄이고 저장 의존을 별도 계층으로 이동함",
            ],
        }
        return list(mapping.get(detector_id, [
            "현재 구조와 권장 구조의 책임 경계가 일치하지 않음",
            "권장 구조는 입력 정리, 정책 판단, 실행 단계를 분리함",
        ]))

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
                    "input_data = RuleFragment01.normalize(input_data)",
                    "if not input_data.valid:",
                    "    return input_data.errors",
                    "return Service01.apply(input_data.payload)",
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
                lines.extend(["```", "", "#### difference_summary"])
                difference_summary = item.get("difference_summary") or []
                if difference_summary:
                    for summary_line in difference_summary[:3]:
                        lines.append(f"- {summary_line}")
                else:
                    lines.append("- responsibility split guidance unavailable")

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
        family_classification,
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
            "family_classifier": family_classification.model_dump(),
            "ordered_sections": ["recommended_strategy", "rationale", "evidence", "risk", "next_step"],
            "surface_wording": self._surface_wording(
                prepared=prepared,
                decisions=decisions,
                diagnosis=diagnosis,
                improvement=improvement,
            ),
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

    def _apply_family_diagnosis_surface_templates(
        self,
        *,
        prepared: Any,
        diagnosis: DiagnosisArtifacts,
        decisions: DecisionArtifacts,
    ) -> DiagnosisArtifacts:
        family = str(decisions.family_classification.family or "").strip()
        if family == "operational_source":
            return self._apply_operational_source_diagnosis_surface_templates(
                prepared=prepared,
                diagnosis=diagnosis,
            )
        return diagnosis

    def _apply_operational_source_diagnosis_surface_templates(
        self,
        *,
        prepared: Any,
        diagnosis: DiagnosisArtifacts,
    ) -> DiagnosisArtifacts:
        analysis_summary = self.template_support.render_operational_section_lines(
            section_key="analysis_summary",
            prepared=prepared,
        )
        if not analysis_summary:
            analysis_summary = list(diagnosis.analysis_summary or [])
        return diagnosis.model_copy(update={"analysis_summary": analysis_summary[:6]})

    def _apply_family_surface_templates(
        self,
        *,
        prepared: Any,
        diagnosis: DiagnosisArtifacts,
        decisions: DecisionArtifacts,
        improvement: ImprovementArtifacts,
    ) -> ImprovementArtifacts:
        family = str(decisions.family_classification.family or "").strip()
        if family == "operational_source":
            return self._apply_operational_source_surface_templates(
                prepared=prepared,
                diagnosis=diagnosis,
                improvement=improvement,
            )
        return improvement

    def _apply_operational_source_surface_templates(
        self,
        *,
        prepared: Any,
        diagnosis: DiagnosisArtifacts,
        improvement: ImprovementArtifacts,
    ) -> ImprovementArtifacts:
        execution_plan = self._operational_surface_execution_plan(
            prepared=prepared,
            diagnosis=diagnosis,
            improvement=improvement,
        )
        recommended_directions = self.template_support.render_operational_section_lines(
            section_key="recommended_directions",
            prepared=prepared,
        )
        risks = self.template_support.render_operational_section_lines(
            section_key="risks",
            prepared=prepared,
        )
        prior_stages = list(improvement.improvement_plan_bundle.execution_stages or [])
        execution_stages: list[ExecutionStage] = []
        for index, week in enumerate(execution_plan):
            prior_stage = prior_stages[index] if index < len(prior_stages) else None
            execution_stages.append(
                ExecutionStage(
                    stage_id=self._stage_attr(prior_stage, "stage_id") or f"operational_analysis_stage_{index + 1}",
                    title=str(week.goal or "").strip(),
                    tasks=list(week.tasks or []),
                    decision_ids=self._stage_list(prior_stage, "decision_ids"),
                    verification_checkpoint_ids=self._stage_list(prior_stage, "verification_checkpoint_ids"),
                    risk_ids=self._stage_list(prior_stage, "risk_ids"),
                    depends_on=self._stage_list(prior_stage, "depends_on"),
                )
            )
        improvement_plan_bundle = improvement.improvement_plan_bundle.model_copy(
            update={"execution_stages": execution_stages}
        )
        return improvement.model_copy(
            update={
                "execution_plan": execution_plan,
                "recommended_directions": recommended_directions or list(improvement.recommended_directions or []),
                "risks": risks or list(improvement.risks or []),
                "improvement_plan_bundle": improvement_plan_bundle,
            }
        )

    def _operational_surface_execution_plan(
        self,
        *,
        prepared: Any,
        diagnosis: DiagnosisArtifacts,
        improvement: ImprovementArtifacts,
    ) -> list[ExecutionPlanWeek]:
        profile = self.template_support.operational_analysis_profile(prepared)
        domain = str(profile.get("domain") or "").strip()
        question_axis = str(profile.get("question_axis") or "").strip()
        related_rules = [str(item.title or "").strip() for item in diagnosis.grounded_business_rules[:3] if str(item.title or "").strip()]
        raw_related_contracts = [str(item.item or "").strip() for item in diagnosis.retained_contracts[:3] if str(item.item or "").strip()]
        contract_fallbacks = {
            "fx_fifo": [
                "입금 lot 잔량 계산 계약은 유지하는 것이 필요합니다.",
                "출금 lot 소진 순서 계약은 유지하는 것이 필요합니다.",
                "환차손익과 회계 인터페이스 반영 계약은 유지하는 것이 필요합니다.",
            ],
            "interface_linkage": [
                "파일 수신 키와 상태 갱신 계약은 유지하는 것이 필요합니다.",
                "최신 상태와 후속 지급 연계 키 계약은 유지하는 것이 필요합니다.",
                "재처리 이력과 응답 상태 연결 계약은 유지하는 것이 필요합니다.",
            ],
            "settlement_journal": [
                "정산 번호와 전표 연결 계약은 유지하는 것이 필요합니다.",
                "회계 인터페이스 기준번호 계약은 유지하는 것이 필요합니다.",
                "취소 역처리와 지급 상태 연결 계약은 유지하는 것이 필요합니다.",
            ],
            "operational_source": [
                "데이터 반영 순서 계약은 유지하는 것이 필요합니다.",
                "핵심 계산 또는 상태 기준 계약은 유지하는 것이 필요합니다.",
                "후속 연계 기준 계약은 유지하는 것이 필요합니다.",
            ],
        }
        related_contracts = self.template_support.render_operational_section_lines(
            section_key="related_contracts",
            prepared=prepared,
            lines=raw_related_contracts,
            fallback_lines=contract_fallbacks.get(domain, contract_fallbacks["operational_source"]),
        )
        option_name = self._option_display_name(improvement.recommended_option.name) if improvement.recommended_option is not None else ""
        if domain == "fx_fifo":
            if question_axis == "journal_linkage":
                stage_specs = [
                    (
                        "1단계",
                        "전표/GL 기준 불일치 가능성을 진단합니다.",
                        [
                            "전표 생성 기준과 GL 연결 기준이 달라질 수 있는 지점을 확인합니다.",
                            "거래 기준번호가 유지되지 않을 때의 회계 영향을 정리합니다.",
                        ],
                        ["전표/GL 진단표", "거래 기준번호 영향 목록"],
                    ),
                    (
                        "2단계",
                        "취소와 역처리의 회계 영향 범위를 확인합니다.",
                        [
                            "취소 시 같은 회계 키가 유지되지 않을 가능성을 확인합니다.",
                            "역처리 누락이 전표와 회계 반영 결과에 주는 영향을 정리합니다.",
                        ],
                        ["취소 영향 점검표", "역처리 진단 메모"],
                    ),
                    (
                        "3단계",
                        "진단 결과를 리스크와 참조 범위로 압축합니다.",
                        [
                            "전표 기준 불일치, GL 연결 누락, 취소 역처리 키 이탈 가능성만 진단 문서에 남깁니다.",
                            "처리 단계 상세는 Structure 문서 참조로만 연결합니다.",
                        ],
                        ["운영 리스크 목록", "참조 범위"],
                    ),
                ]
            elif question_axis == "calculation_rule":
                stage_specs = [
                    (
                        "1단계",
                        "계산 기준 선택지를 정의합니다.",
                        [
                            "현행 FIFO 기준 유지, 평균 기준 단순화, 거래별 지정 기준을 같은 비교 축에 놓습니다.",
                            "비교 기준은 계산 재현성, 환율 기준 일관성, 회계 연결 가능성으로 고정합니다.",
                        ],
                        ["선택지 비교표", "비교 기준표"],
                    ),
                    (
                        "2단계",
                        "우선 추천안을 정리합니다.",
                        [
                            "우선안은 현행 FIFO 기준 유지와 예외 검증 보강으로 둡니다.",
                            "평균 기준 단순화와 거래별 지정 기준은 대안으로만 비교합니다.",
                        ],
                        ["추천안 메모", "대안 비교 메모"],
                    ),
                    (
                        "3단계",
                        "추천안 적용 검증 기준을 정합니다.",
                        [
                            "예외와 취소 처리에서도 같은 계산 기준이 유지되는지 확인 항목을 둡니다.",
                            "흐름 상세와 리스크 상세는 Structure, Diagnosis 문서 참조로만 연결합니다.",
                        ],
                        ["적용 검증 기준", "문서 참조 메모"],
                    ),
                ]
            else:
                stage_specs = [
                    (
                        "1단계",
                        "입금부터 lot 소진까지 처리 흐름을 구조화합니다.",
                        [
                            "외화 입금이 저장된 뒤 출금에서 어떤 lot이 선택되는지 흐름을 정리합니다.",
                            "남은 잔량이 어떤 순서와 기준으로 줄어드는지 확인합니다.",
                        ],
                        ["처리 흐름표", "lot 소진 기준표"],
                    ),
                    (
                        "2단계",
                        "계산 결과와 회계 반영 순서를 표시합니다.",
                        [
                            "어떤 환율과 금액 기준으로 계산 결과가 만들어지는지 단계만 표시합니다.",
                            "계산 결과가 전표 반영과 회계 연결로 이어지는 순서를 표시합니다.",
                        ],
                        ["계산 단계 표", "회계 반영 순서표"],
                    ),
                    (
                        "3단계",
                        "처리 결과와 후속 반영 지점을 표시합니다.",
                        [
                            "계산 결과가 전표 반영과 회계 연결로 넘어가는 지점을 표시합니다.",
                            "리스크와 선택 기준은 Diagnosis, Decision 문서 참조로만 연결합니다.",
                        ],
                        ["후속 반영 지점", "문서 참조 메모"],
                    ),
                ]
        elif domain == "interface_linkage":
            stage_specs = [
                (
                    "1단계",
                    "파일 수신부터 후속 반영까지 처리 흐름을 구조화합니다.",
                    [
                        "파일 수신 뒤 상태 확정과 후속 반영이 어떤 순서로 이어지는지 정리합니다.",
                        "같은 거래 기준이 재처리와 후속 업무 연계까지 유지되는지 확인합니다.",
                    ],
                    ["처리 흐름표", "연계 기준표"],
                ),
                (
                    "2단계",
                    "응답 확정과 재처리 규칙을 검증합니다.",
                    [
                        "확정 응답, 처리 상태, 수신 반영 상태, 재처리 기록이 어떤 순서로 갱신되는지 대조합니다.",
                        "최신 상태와 후속 지급 연계가 같은 거래 키를 유지하는지 확인합니다.",
                    ],
                    ["상태 전이 점검표", "재처리 규칙 표"],
                ),
                (
                    "3단계",
                    "운영 리스크와 후속 확인 항목을 정리합니다.",
                    [
                        "중복 적재, 응답 상태 불일치, 재처리 누락, 후속 지급 연계 누락 가능성을 운영 리스크로 정리합니다.",
                        "추가로 확인할 연계 기준과 재처리 기준을 별도 메모로 정리합니다.",
                    ],
                    ["운영 리스크 목록", "후속 확인 항목"],
                ),
            ]
        elif domain == "settlement_journal":
            if question_axis == "journal_linkage":
                stage_specs = [
                    (
                        "1단계",
                        "정산 결과가 어떤 전표 기준과 회계 reference로 이어지는지 구조화합니다.",
                        [
                            "정산 결과가 전표 헤더·라인으로 어떤 기준으로 이어지는지 정리합니다.",
                            "회계 reference와 거래 기준번호가 어디서 결정되는지 확인합니다.",
                        ],
                        ["전표 연계 흐름표", "회계 reference 점검표"],
                    ),
                    (
                        "2단계",
                        "전표 생성 기준과 취소 역처리 키를 검증합니다.",
                        [
                            "전표 생성과 회계 reference가 같은 거래 키를 유지하는지 대조합니다.",
                            "취소와 reverse posting 시 같은 회계 기준이 유지되는지 확인합니다.",
                        ],
                        ["전표 기준 표", "취소 역처리 키 점검표"],
                    ),
                    (
                        "3단계",
                        "운영 리스크와 후속 확인 항목을 정리합니다.",
                        [
                            "정산-전표 기준 불일치, 회계 reference 누락, 취소 역처리 키 이탈 가능성을 운영 리스크로 정리합니다.",
                            "추가로 확인할 전표 연계 기준과 취소 처리 기준을 별도 메모로 정리합니다.",
                        ],
                        ["운영 리스크 목록", "후속 확인 항목"],
                    ),
                ]
            else:
                stage_specs = [
                    (
                        "1단계",
                        "정산 확정부터 회계 반영까지 처리 흐름을 구조화합니다.",
                        [
                            "정산이 확정된 뒤 전표 반영과 회계 연계로 이어지는 순서를 정리합니다.",
                            "취소와 역처리가 어느 지점에서 같은 기준번호를 유지하는지 확인합니다.",
                        ],
                        ["처리 흐름표", "회계 반영 기준표"],
                    ),
                    (
                        "2단계",
                        "정산 기준과 취소 역처리 규칙을 검증합니다.",
                        [
                            "정산번호, 회계 기준일, 전표 번호 연결 규칙을 현행 로직 기준으로 대조합니다.",
                            "취소, reverse posting, 지급 상태 갱신이 같은 체인으로 유지되는지 확인합니다.",
                        ],
                        ["정산 기준 점검표", "취소 역처리 규칙 표"],
                    ),
                    (
                        "3단계",
                        "운영 리스크와 후속 확인 항목을 정리합니다.",
                        [
                            "정산-전표 불일치, GL 적재 누락, 취소 역분개 누락 가능성을 운영 리스크로 정리합니다.",
                            "추가로 확인할 정산 기준과 취소 처리 기준을 별도 메모로 정리합니다.",
                        ],
                        ["운영 리스크 목록", "후속 확인 항목"],
                    ),
                ]
        else:
            stage_specs = [
                (
                    "1단계",
                    "데이터 흐름과 반영 순서를 구조화합니다.",
                    [
                        "데이터가 저장된 뒤 어떤 순서로 후속 처리로 이어지는지 정리합니다.",
                        "후속 반영이 어떤 기준으로 연결되는지 확인합니다.",
                    ],
                    ["데이터 흐름표", "반영 순서 점검표"],
                ),
                (
                    "2단계",
                    "행동 규칙과 계산·상태 조건을 검증합니다.",
                    [
                        "처리 가능 조건, 계산 기준, 후속 연계 순서를 실제 흐름 기준으로 대조합니다.",
                        "재처리, 취소, 삭제 시 누락되기 쉬운 지점을 확인합니다.",
                    ],
                    ["행동 규칙 표", "계산·상태 점검표"],
                ),
                (
                    "3단계",
                    "운영 리스크와 후속 확인 항목을 정리합니다.",
                    [
                        "연계 정합성 불일치와 재처리 누락 가능성을 운영 리스크 목록으로 정리합니다.",
                        "추가로 확인할 운영 기준과 연계 항목을 별도 메모로 정리합니다.",
                    ],
                    ["운영 리스크 목록", "후속 확인 항목"],
                ),
            ]
        rendered_plan: list[ExecutionPlanWeek] = []
        for index, (label, goal, tasks, deliverables) in enumerate(stage_specs):
            rendered_lines = self.template_support.render_operational_section_lines(
                section_key="execution_plan",
                prepared=prepared,
                lines=[goal, *tasks],
                fallback_lines=[goal, *tasks],
            )
            rendered_goal = str(rendered_lines[0] if rendered_lines else goal).strip()
            rendered_tasks = [str(item).strip() for item in rendered_lines[1:] if str(item).strip()] or list(tasks)
            rendered_plan.append(
                ExecutionPlanWeek(
                    week_label=label,
                    goal=rendered_goal,
                    tasks=rendered_tasks,
                    related_rules=related_rules,
                    related_contracts=related_contracts,
                    roles=["컨설턴트", "업무 분석가", "백엔드 아키텍트"] if index == 0 else ["백엔드 개발자", "QA"],
                    duration_weeks=1,
                    deliverables=deliverables,
                )
            )
        return rendered_plan

    def _stage_attr(self, stage: Any, field_name: str) -> str:
        if isinstance(stage, dict):
            return str(stage.get(field_name) or "").strip()
        return str(getattr(stage, field_name, "") or "").strip()

    def _stage_list(self, stage: Any, field_name: str) -> list[str]:
        if isinstance(stage, dict):
            values = stage.get(field_name) or []
        else:
            values = getattr(stage, field_name, []) or []
        return [str(item).strip() for item in values if str(item).strip()]

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

    def _surface_wording(
        self,
        *,
        prepared: Any,
        decisions: DecisionArtifacts,
        diagnosis: DiagnosisArtifacts,
        improvement: ImprovementArtifacts,
    ) -> dict[str, Any]:
        family_classification = decisions.family_classification
        internal_strategy = str(
            family_classification.internal_strategy
            or decisions.decision_summary.recommended_strategy
            or "리팩터링 우선"
        )
        default_titles = {
            "report_purpose": "보고 목적",
            "executive_summary_v2": "핵심 요약",
            "one_line_conclusion": "핵심 결론",
            "primary_judgment_reason": "판단 이유",
            "recommended_option": "추천안 설명",
            "execution_plan": "실행 단계 설명",
            "risks": "리스크 설명",
            "recommended_directions": "추천 방향",
            "recomposition_draft": "전환 초안",
        }
        if str(family_classification.family or "").strip() == "operational_source":
            profile = self.template_support.operational_analysis_profile(prepared)
            question_axis = str(profile.get("question_axis") or "").strip()
            if question_axis == "journal_linkage":
                return {
                    "mode": "analysis_first_operational_source",
                    "internal_strategy_taxonomy": internal_strategy,
                    "display_strategy": "전표/GL 진단 우선",
                    "summary_card_titles": {
                        "judgment": "진단 성격",
                        "strategy": "영향 기준",
                        "execution": "리스크 범위",
                    },
                    "section_titles": {
                        "report_purpose": "현행 요약",
                        "executive_summary_v2": "문제 정의",
                        "one_line_conclusion": "진단 대상",
                        "analysis_summary": "참조 객체",
                        "primary_judgment_reason": "영향 분석",
                        "recommended_option": "참조 메모",
                        "execution_plan": "진단 순서",
                        "risks": "리스크",
                        "recommended_directions": "리스크 메모",
                        "recomposition_draft": "참고 메모",
                    },
                    "document_tone": "diagnosis_first",
                }
            if question_axis == "calculation_rule":
                return {
                    "mode": "analysis_first_operational_source",
                    "internal_strategy_taxonomy": internal_strategy,
                    "display_strategy": "계산 기준 판단 우선",
                    "summary_card_titles": {
                        "judgment": "판단 성격",
                        "strategy": "비교 기준",
                        "execution": "적용 기준",
                    },
                    "section_titles": {
                        "report_purpose": "판단 목적",
                        "executive_summary_v2": "선택지 요약",
                        "one_line_conclusion": "추천안",
                        "analysis_summary": "참조 객체",
                        "primary_judgment_reason": "비교 기준",
                        "recommended_option": "추천 근거",
                        "execution_plan": "적용 검증 기준",
                        "risks": "참조 리스크",
                        "recommended_directions": "추천 근거",
                        "recomposition_draft": "참고 메모",
                    },
                    "document_tone": "decision_first",
                }
            return {
                "mode": "analysis_first_operational_source",
                "internal_strategy_taxonomy": internal_strategy,
                "display_strategy": str(family_classification.display_strategy or "").strip() or (
                    "현행 분석 우선" if str(profile.get("domain") or "").strip() == "fx_fifo" else "운영 로직 검토 우선"
                ),
                "summary_card_titles": {
                    "judgment": "분석 성격",
                    "strategy": "우선 검토 기준",
                    "execution": "검토 순서",
                },
                "section_titles": {
                    "report_purpose": "분석 목적",
                    "executive_summary_v2": "현행 분석 요약",
                    "one_line_conclusion": "자산 정체",
                    "analysis_summary": "핵심 객체",
                    "primary_judgment_reason": "우선 검토 기준",
                    "recommended_option": "후속 확인 항목",
                    "execution_plan": "검토 순서",
                    "risks": "운영 리스크",
                    "recommended_directions": "추가 확인 포인트",
                    "recomposition_draft": "참고 메모",
                },
                "document_tone": "analysis_first",
            }
        if str(family_classification.family or "").strip() == "option_comparison":
            return {
                "mode": "comparison_first_option",
                "internal_strategy_taxonomy": internal_strategy,
                "display_strategy": str(family_classification.display_strategy or "").strip() or "비교 기준 우선",
                "summary_card_titles": {
                    "judgment": "비교 성격",
                    "strategy": "추천 기준",
                    "execution": "도입 순서",
                },
                "section_titles": {
                    "report_purpose": "비교 목적",
                    "executive_summary_v2": "선택지 요약",
                    "one_line_conclusion": "추천안",
                    "primary_judgment_reason": "비교 기준",
                    "recommended_option": "추천 근거",
                    "execution_plan": "도입 단계",
                    "risks": "선택 시 유의점",
                    "recommended_directions": "검토 후보",
                    "recomposition_draft": "추가 구조 메모",
                },
                "document_tone": "comparison_first",
            }
        return {
            "mode": "default",
            "internal_strategy_taxonomy": internal_strategy,
            "display_strategy": str(family_classification.display_strategy or "").strip() or internal_strategy,
            "summary_card_titles": {
                "judgment": "핵심 판단",
                "strategy": "왜 이 방향인가",
                "execution": "다음 단계",
            },
            "section_titles": default_titles,
            "document_tone": "default",
        }

    def _document_outline(
        self,
        *,
        prepared: Any,
        decisions: DecisionArtifacts,
        diagnosis: DiagnosisArtifacts,
        improvement: ImprovementArtifacts,
        grounding_profile: dict[str, Any],
    ) -> dict[str, Any]:
        if str(decisions.family_classification.family or "").strip() == "operational_source":
            return self._operational_document_outline(
                prepared=prepared,
                decisions=decisions,
                diagnosis=diagnosis,
                improvement=improvement,
            )
        if str(decisions.family_classification.family or "").strip() == "option_comparison":
            return self._comparison_document_outline(
                decisions=decisions,
                diagnosis=diagnosis,
                improvement=improvement,
                grounding_profile=grounding_profile,
            )
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

    def _operational_document_outline(
        self,
        *,
        prepared: Any,
        decisions: DecisionArtifacts,
        diagnosis: DiagnosisArtifacts,
        improvement: ImprovementArtifacts,
    ) -> dict[str, Any]:
        profile = self.template_support.operational_analysis_profile(prepared)
        domain = str(profile.get("domain") or "").strip()
        display_strategy = str(decisions.family_classification.display_strategy or "").strip() or "현행 분석 우선"
        if domain == "fx_fifo":
            rationale = (
                "입력 자산이 외화 입출금 FIFO 운영 소스이므로, 현재 단계의 1차 목적은 현행 업무 규칙과 회계 처리 흐름을 복원하는 것입니다."
            )
            next_step = "입금 lot, FIFO 소진, 환차손익, 전표·총계정원장 연계를 역할 기준으로 표로 정리합니다."
            risk = (
                str((improvement.risks or [None])[0] or "")
                or "FIFO 소진 순서, 환차 계산 기준, 전표·GL 기준번호가 어긋나면 회계 정합성이 흔들릴 수 있습니다."
            )
        elif domain == "interface_linkage":
            rationale = (
                "입력 자산이 interface staging, ACK 상태 전이, retry/실패 처리, downstream 연계를 포함한 운영 소스이므로, "
                "현재 단계의 1차 목적은 현행 인터페이스 체인과 상태 갱신 순서를 복원하는 것입니다."
            )
            next_step = "수신 적재, 상태 확정, 최신 상태 갱신, 후속 지급 연계를 역할 기준으로 표로 정리합니다."
            risk = (
                str((improvement.risks or [None])[0] or "")
                or "중복 적재, ACK/status 불일치, retry 누락, 최신본 갱신 누락이 남으면 인터페이스 운영 정합성이 흔들릴 수 있습니다."
            )
        elif domain == "settlement_journal":
            rationale = (
                "입력 자산이 정산 확정, 전표 헤더/라인 생성, GL 적재, 취소 역처리를 포함한 운영 소스이므로, "
                "현재 단계의 1차 목적은 현행 정산-전표-GL 체인을 복원하는 것입니다."
            )
            next_step = "정산 헤더·상세, 전표 헤더·라인, 회계 연계, 취소 역처리 경로를 역할 기준으로 표로 정리합니다."
            risk = (
                str((improvement.risks or [None])[0] or "")
                or "정산-전표 불일치, GL 적재 누락, 취소 역분개 누락이 남으면 회계 정합성이 흔들릴 수 있습니다."
            )
        else:
            rationale = (
                "입력 자산이 실제 운영 처리와 후속 반영을 담당하는 현행 자산이므로, 현재 단계에서는 현행 데이터 흐름과 유지 계약 복원이 우선입니다."
            )
            next_step = "데이터 저장, 자동 반영, 후속 연계 역할을 구분해 데이터 반영 순서와 연결 관계를 먼저 복원합니다."
            risk = str((improvement.risks or [None])[0] or "") or "재처리·연계 정합성을 확인하지 않으면 운영 누락 위험이 남습니다."
        rationale_lines = self.template_support.render_operational_section_lines(
            section_key="rationale",
            prepared=prepared,
            lines=[rationale],
            fallback_lines=[rationale],
        )
        evidence_lines = self.template_support.render_operational_section_lines(
            section_key="evidence",
            prepared=prepared,
            lines=list(diagnosis.analysis_summary[:3]),
            fallback_lines=list(diagnosis.analysis_summary[:3]) or ["직접 확인된 운영 소스 근거를 우선 정리합니다."],
        )
        risk_lines = self.template_support.render_operational_section_lines(
            section_key="risk",
            prepared=prepared,
            lines=[risk],
            fallback_lines=[risk],
        )
        next_step_lines = self.template_support.render_operational_section_lines(
            section_key="next_step",
            prepared=prepared,
            lines=[next_step],
            fallback_lines=[next_step],
        )
        return {
            "recommended_strategy": display_strategy,
            "rationale": str(rationale_lines[0] if rationale_lines else rationale),
            "evidence": evidence_lines or ["직접 확인된 운영 소스 근거를 우선 정리합니다."],
            "risk": str(risk_lines[0] if risk_lines else risk),
            "next_step": str(next_step_lines[0] if next_step_lines else next_step),
        }

    def _comparison_document_outline(
        self,
        *,
        decisions: DecisionArtifacts,
        diagnosis: DiagnosisArtifacts,
        improvement: ImprovementArtifacts,
        grounding_profile: dict[str, Any],
    ) -> dict[str, Any]:
        display_strategy = str(decisions.family_classification.display_strategy or "").strip() or "비교 기준 우선"
        option = self._comparison_primary_option(improvement)
        option_label = self._option_display_name(getattr(option, "name", "") or "")
        structure_summary = str(getattr(option, "structure_summary", "") or "").strip()
        selection_reason = str(getattr(option, "selection_reason", "") or "").strip()
        rationale_parts = [part for part in (structure_summary, selection_reason) if part]
        if rationale_parts:
            rationale = f"{option_label or '추천 후보'}은 " + " ".join(rationale_parts)
        elif bool(grounding_profile.get("insufficient_grounding")):
            rationale = "직접 연결된 구조 근거가 제한적이므로 추천안을 확정안이 아니라 비교용 초안으로 유지합니다."
        else:
            rationale = "복수 선택지를 같은 기준으로 나란히 놓고 비교해 추천안을 좁혔습니다."
        evidence_lines: list[str] = []
        for item in list(getattr(improvement, "design_options", []) or [])[:3]:
            name = self._option_display_name(getattr(item, "name", "") or "")
            summary = str(getattr(item, "structure_summary", "") or "").strip()
            if name and summary:
                evidence_lines.append(f"{name}: {summary}")
            elif name:
                evidence_lines.append(name)
        if not evidence_lines:
            evidence_lines = list(diagnosis.analysis_summary[:3]) or ["비교 기준에 직접 연결된 선택지 설명을 우선 정리합니다."]
        option_risk = ""
        if option is not None:
            option_risks = list(getattr(option, "risks", []) or [])
            option_risk = str((option_risks or [None])[0] or "").strip()
        risk = (
            option_risk
            or str((improvement.risks or [None])[0] or "").strip()
            or "비교 기준 없이 구조를 고르면 후속 재작업과 회귀 검토 범위가 다시 커질 수 있습니다."
        )
        next_step = (
            str((improvement.recommended_directions or [None])[0] or "").strip()
            or "추천안을 기준으로 적용 순서와 검증 포인트를 연결해 실행안을 고정합니다."
        )
        return {
            "recommended_strategy": display_strategy,
            "rationale": rationale,
            "evidence": evidence_lines,
            "risk": risk,
            "next_step": next_step,
        }

    def _comparison_primary_option(self, improvement: ImprovementArtifacts) -> Any | None:
        if improvement.recommended_option is not None:
            return improvement.recommended_option
        for item in list(improvement.design_options or []):
            if bool(getattr(item, "recommended", False)):
                return item
        options = list(improvement.design_options or [])
        return options[0] if options else None

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
