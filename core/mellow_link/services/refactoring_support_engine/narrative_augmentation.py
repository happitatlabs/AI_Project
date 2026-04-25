from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mellow_link.modules.rebuild_assistant.postprocess.consulting_contract import (
    build_consulting_min_contract,
)
from mellow_link.modules.rebuild_assistant.schemas import (
    CanonicalFunctionClassification,
    CanonicalRebuildPayload,
    CanonicalRequestContext,
    ConsultingDeckOutlineChapter,
    DeterministicExplanationBlock,
    NarrativeBlockRewriteMetadata,
    NarrativeCriticalFact,
    NarrativeDecisionDrivingEvidence,
    NarrativeLockedFields,
    NarrativeValidationResult,
    NarrativeValidationMetadata,
    RebuildNarrativeLayer,
    StructuredRebuildResult,
)
from .runtime_contracts import assert_stage_action
from .template_support import TemplateSupport

logger = logging.getLogger(__name__)

PROMPT_VERSION = "phase2.0-single-shot-narrative-v1"
FAILURE_EMPTY_BLOCK_CANDIDATE = "empty_block_candidate"
FAILURE_FORBIDDEN_EXPRESSION = "forbidden_expression"
FAILURE_PRIORITY_MUTATION = "priority_mutation"
FAILURE_RECOMMENDED_OPTION_MUTATION = "recommended_option_mutation"
FAILURE_RECOMMENDED_OPTION_NAME_MISSING = "recommended_option_name_missing"
FAILURE_CLASSIFICATION_MUTATION = "classification_mutation"
FAILURE_DIAGNOSIS_MUTATION = "diagnosis_mutation"
FAILURE_EXECUTION_STAGE_COUNT_MISMATCH = "execution_stage_count_mismatch"
FAILURE_EXECUTION_STAGE_ORDER_MUTATION = "execution_stage_order_mutation"
FAILURE_EXECUTION_STAGE_TASK_MISSING = "execution_stage_task_missing"
FAILURE_RISK_ITEM_COUNT_MISMATCH = "risk_item_count_mismatch"
FAILURE_RISK_ITEM_ORDER_MUTATION = "risk_item_order_mutation"
FAILURE_RISK_COVERAGE_MISSING = "risk_coverage_missing"
FAILURE_RISK_SEVERITY_DOWNGRADED = "risk_severity_downgraded"
FAILURE_RISK_GENERALIZATION_BEYOND_EVIDENCE = "risk_generalization_beyond_evidence"
FAILURE_LOCKED_FIELD_MUTATION = "locked_field_mutation"
FAILURE_UNSUPPORTED_CLAIM = "unsupported_claim"
FAILURE_DECISION_EVIDENCE_COVERAGE_MISSING = "decision_evidence_coverage_missing"
FAILURE_CRITICAL_FACT_MISSING = "critical_fact_missing"
FAILURE_AMBIGUOUS_FACT_MERGE = "ambiguous_fact_merge"
FAILURE_EMPTY_NARRATIVE_LAYER = "empty_narrative_layer"
FAILURE_INVALID_CONSULTING_DECK_OUTLINE = "invalid_consulting_deck_outline"
FAILURE_INVALID_EVIDENCE_REF = "invalid_evidence_ref"
FAILURE_GROUNDED_FACT_MISMATCH = "grounded_fact_mismatch"
FAILURE_FORBIDDEN_TOP_LEVEL_FIELD = "forbidden_top_level_field"
FAILURE_SCHEMA_VALIDATION_ERROR = "schema_validation_error"
FAILURE_REWRITE_SCOPE_VIOLATION = "rewrite_scope_violation"
FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION = "operational_governance_violation"
FAILURE_DETECTOR_NAME_EXPOSURE = "detector_name_exposure"
MATCH_MODE_EXACT = "exact"
MATCH_MODE_NORMALIZED = "normalized"
MATCH_MODE_SEMANTIC = "semantic"
MATCH_MODE_FAILED = "failed"
MATCH_MODE_MIXED = "mixed"
ALLOWED_OUTLINE_CHAPTER_KEYS = ("overview", "approach", "implementation", "design", "vision")
ALLOWED_REWRITE_FIELDS = (
    "report_purpose",
    "executive_summary_v2",
    "one_line_conclusion",
    "primary_judgment_reason",
    "recommended_option",
    "execution_plan",
    "risks",
)
FORBIDDEN_TOP_LEVEL_FIELDS = {
    "primary_judgment",
    "template_judgment",
    "structural_judgment",
    "narrative_axis",
    "feature_signal_mode",
    "diagnosis_report",
    "decision_summary",
    "design_options",
}
REWRITE_SCOPE_FORBIDDEN_FIELDS = {
    "decision_narrative",
    "consulting_deck_outline",
}
BLOCK_FIELD_TYPES = {
    "report_purpose": "text",
    "primary_judgment_reason": "text",
    "one_line_conclusion": "text",
    "executive_summary_v2": "list",
    "recommended_option": "text",
    "execution_plan": "list",
    "risks": "list",
}
FORBIDDEN_EXPRESSIONS = (
    r"원문에는 없지만",
    r"추정컨대",
    r"가정하면",
    r"업계 관례상",
    r"일반적으로 보면",
    r"새로운 [^,.\n]{0,20}(?:규칙|정책|근거|리스크|옵션|사실)",
    r"신규 [^,.\n]{0,20}(?:규칙|정책|근거|리스크|옵션|사실)",
    r"새로 [^,.\n]{0,20}(?:추가|생성|정의)",
)
DETECTOR_NAME_PATTERNS = (
    r"detector_id\s*=",
    r"\b[a-z_]{3,}(?:_candidate|_mismatch|_leak|_scatter|_needed)\b",
)
OPERATIONAL_REDESIGN_PATTERNS = (
    r"분리 구조",
    r"계층 분리",
    r"계층으로 분리",
    r"재설계",
    r"재구성 로드맵",
    r"서비스 분리",
    r"분리안",
    r"service split",
    r"layer separation",
    r"redesign",
)
RISK_EXAGGERATION_PATTERNS = (
    r"치명적(?:인)?",
    r"전사(?:적)?",
    r"광범위(?:한)?",
    r"대규모(?:의)?",
    r"즉시 장애",
    r"심각한 장애",
    r"전체 시스템",
    r"\b항상\b",
    r"\b반드시\b",
    r"\b모든\b",
    r"매우 높은 확률",
)
RISK_SEVERITY_TOKENS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (4, ("치명", "중단", "전면", "유실", "장애", "마비", "catastrophic", "critical", "major outage")),
    (3, ("회귀", "regression", "누락", "빠짐", "유실", "불일치", "불정합", "오판", "위반", "정합성", "무결성", "차단", "붕괴", "integrity", "inconsistency")),
    (2, ("영향", "파급", "오류", "흔들", "지연", "불안정", "instability", "delay")),
)
OPTION_ALIAS_SUFFIXES = ("개선안", "개선 방향", "방향", "옵션", "option")
NORMALIZATION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"검증|확인|체크|검사", "검증"),
    (r"저장|save|persist|commit", "저장"),
    (r"경로|흐름|플로우|flow", "흐름"),
    (r"분리|격리|추출|분해|독립", "분리"),
    (r"정리|재배치|정돈|구조화|재구성", "정리"),
    (r"승인|결재|approval", "승인"),
    (r"경계|boundary", "경계"),
    (r"흐려|불명확|모호", "모호"),
    (r"회귀|되돌림|regression", "회귀"),
    (r"영향|파급", "영향"),
    (r"누락|빠짐|미반영|유실", "누락"),
    (r"불일치|불정합|비일관|정합성.?깨짐|정합성.?손상", "불일치"),
    (r"위험|리스크|risk", "리스크"),
    (r"드러남|확인됨|보임", "확인"),
    (r"조건|분기", "분기"),
)
UNSUPPORTED_CLAIM_THRESHOLDS: dict[str, tuple[int, float]] = {
    "default": (3, 0.25),
    "recommended_option": (2, 0.18),
    "execution_plan": (5, 0.45),
    "risks": (5, 0.45),
}
STRATEGY_TOKENS = {
    "refactor",
    "redesign",
    "migration_consideration",
    "observation_only",
    "workflow",
    "state_transition",
    "access_control",
    "query_filter",
    "validation",
}
PRIORITY_MUTATION_PATTERNS = (
    r"\bpriority\b",
    r"우선순위",
    r"\bP[0-3]\b",
    r"[1-9]순위",
)
CLASSIFICATION_TOKENS = {
    "workflow",
    "state_transition",
    "access_control",
    "query_filter",
    "validation",
    "amount_threshold",
    "fx_fifo",
    "interface_linkage",
    "settlement_journal",
    "refactor",
    "redesign",
    "migration_consideration",
    "observation_only",
}
STOP_WORDS = {
    "현재",
    "기준",
    "구조",
    "판단",
    "결과",
    "설명",
    "보고서",
    "기능",
    "방향",
    "분리",
    "책임",
    "경계",
    "이슈",
    "처리",
    "구조적",
    "단순화",
    "상위",
    "유지",
    "정리",
    "우선",
    "검토",
    "근거",
    "직접",
    "확인",
    "권장",
    "필요",
    "합니다",
    "입니다",
    "레이어",
    "메시지",
    "핵심",
    "상태",
    "흐름",
    "계획",
    "설계",
    "향후",
    "조치",
    "요약",
    "문장",
    "수준",
    "대한",
    "위한",
    "기반",
    "관련",
    "통해",
    "먼저",
    "추가",
    "중심",
    "client",
    "manager",
    "summary",
    "report",
    "decision",
    "outline",
    "evidence",
}


class SlimGroundedRule(BaseModel):
    title: str = ""
    description: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class SlimDecisionItem(BaseModel):
    statement: str = ""
    rationale: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class SlimRetainedContract(BaseModel):
    item: str = ""
    basis: str = ""


class SlimExecutionItem(BaseModel):
    week_label: str = ""
    goal: str = ""
    deliverables: list[str] = Field(default_factory=list)


class SlimEvidenceItem(BaseModel):
    evidence_id: str = ""
    asset_name: str = ""
    asset_type: str = ""
    locator: str = ""
    excerpt: str = ""


class SlimNarrativePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_context: dict[str, Any] = Field(default_factory=dict)
    function_classification: dict[str, Any] = Field(default_factory=dict)
    analysis_summary: list[str] = Field(default_factory=list)
    deterministic_narrative: dict[str, Any] = Field(default_factory=dict)
    grounded_business_rules: list[SlimGroundedRule] = Field(default_factory=list)
    decision_items: list[SlimDecisionItem] = Field(default_factory=list)
    retained_contracts: list[SlimRetainedContract] = Field(default_factory=list)
    recommended_option: dict[str, Any] | None = None
    execution_plan: list[SlimExecutionItem] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    consulting_contract_seed: dict[str, list[str]] = Field(default_factory=dict)
    evidence_index: list[SlimEvidenceItem] = Field(default_factory=list)
    explanation_blocks: list[DeterministicExplanationBlock] = Field(default_factory=list)


class NarrativeAugmentationOutcome(BaseModel):
    narrative_layer: RebuildNarrativeLayer | None = None
    metadata: NarrativeValidationMetadata
    validated_explanation_blocks: list[DeterministicExplanationBlock] = Field(default_factory=list)


class NarrativeAugmentationService:
    def __init__(self) -> None:
        self.template_support = TemplateSupport()

    def augment_sync(
        self,
        *,
        prepared,
        result: StructuredRebuildResult,
        llm_service: Any | None,
        stage_control: dict[str, object] | None = None,
    ) -> StructuredRebuildResult:
        augmentation = asyncio.run(
            self.augment(
                prepared=prepared,
                result=result,
                llm_service=llm_service,
                stage_control=stage_control,
            )
        )
        return self.apply(result, augmentation)

    async def augment(
        self,
        *,
        prepared,
        result: StructuredRebuildResult,
        llm_service: Any | None,
        stage_control: dict[str, object] | None = None,
    ) -> NarrativeAugmentationOutcome:
        assert_stage_action(
            stage_control or getattr(prepared, "stage_control", None) or getattr(result, "stage_control", None),
            expected_stage="planning",
            action="augment_narrative",
            goal=str(getattr(prepared, "goal", "") or ""),
        )
        canonical_payload = self.freeze_canonical_payload(prepared=prepared, result=result)
        deterministic_blocks = self.build_deterministic_explanation_blocks(
            canonical_payload=canonical_payload,
            result=result,
        )
        slim_payload = self.build_slim_payload(
            canonical_payload=canonical_payload,
            result=result,
            explanation_blocks=deterministic_blocks,
        )
        slim_payload_hash = self._payload_hash(slim_payload)

        if llm_service is None or not hasattr(llm_service, "generate"):
            return self._fallback_outcome(
                result=result,
                deterministic_blocks=deterministic_blocks,
                failure_reason="llm_service_unavailable",
                slim_payload_hash=slim_payload_hash,
                llm_invoked=False,
                llm_call_count=0,
            )

        try:
            raw_response = await llm_service.generate(
                prompt=self._build_prompt(slim_payload),
                system_prompt=self._system_prompt(),
                mode="thinking",
                temperature=0.1,
                max_tokens=1200,
                auto_unload=True,
            )
        except Exception as exc:
            logger.warning("[NarrativeAugmentation] LLM generate failed: %s", exc)
            return self._fallback_outcome(
                result=result,
                deterministic_blocks=deterministic_blocks,
                failure_reason=f"llm_generate_failed:{type(exc).__name__}",
                slim_payload_hash=slim_payload_hash,
                llm_invoked=True,
                llm_call_count=1,
            )

        parsed = self._parse_response(raw_response)
        if parsed is None:
            return self._fallback_outcome(
                result=result,
                deterministic_blocks=deterministic_blocks,
                failure_reason="invalid_json_response",
                slim_payload_hash=slim_payload_hash,
                llm_invoked=True,
                llm_call_count=1,
                model=self._model_name(raw_response, llm_service),
            )

        candidate, failure_reason = self._validate_candidate_schema(candidate=parsed)
        if candidate is None:
            return self._fallback_outcome(
                result=result,
                deterministic_blocks=deterministic_blocks,
                failure_reason=failure_reason,
                slim_payload_hash=slim_payload_hash,
                llm_invoked=True,
                llm_call_count=1,
                model=self._model_name(raw_response, llm_service),
            )

        resolved_blocks, block_results, block_rewrite_metadata = self.resolve_explanation_blocks(
            candidate=parsed,
            canonical_payload=canonical_payload,
            slim_payload=slim_payload,
        )
        narrative_layer = self.materialize_narrative_layer(resolved_blocks)
        validated_layer, failure_reason = self.validate_candidate(
            candidate=narrative_layer.model_dump(),
            canonical_payload=canonical_payload,
            slim_payload=slim_payload,
            result=result,
        )
        if validated_layer is None:
            return self._fallback_outcome(
                result=result,
                deterministic_blocks=resolved_blocks,
                failure_reason=failure_reason,
                slim_payload_hash=slim_payload_hash,
                llm_invoked=True,
                llm_call_count=1,
                model=self._model_name(raw_response, llm_service),
            )

        fields_rewritten = [
            item.block_id
            for item in block_rewrite_metadata
            if item.source == "ai" and str(item.block_id or "").strip()
        ]
        any_ai_rewrite = any(item.source == "ai" for item in block_rewrite_metadata)
        aggregate_match_mode = self._aggregate_match_mode(block_results)
        block_match_modes = self._block_match_modes(block_results)
        return NarrativeAugmentationOutcome(
            narrative_layer=validated_layer,
            metadata=NarrativeValidationMetadata(
                source="ai" if any_ai_rewrite else "deterministic_fallback",
                match_mode=aggregate_match_mode,
                fields_rewritten=fields_rewritten,
                model=self._model_name(raw_response, llm_service),
                prompt_version=PROMPT_VERSION,
                validation_passed=all(item.validation_passed for item in block_results),
                failure_reason=self._aggregate_block_failure_reason(block_results),
                axis=self._narrative_axis(result),
                llm_invoked=True,
                llm_call_count=1,
                fallback_used=not all(item.validation_passed for item in block_results),
                slim_payload_hash=slim_payload_hash,
                block_match_modes=block_match_modes,
                block_results=block_results,
                block_rewrite_metadata=block_rewrite_metadata,
            ),
            validated_explanation_blocks=resolved_blocks,
        )

    def apply(
        self,
        result: StructuredRebuildResult,
        augmentation: NarrativeAugmentationOutcome,
    ) -> StructuredRebuildResult:
        metadata = augmentation.metadata
        existing_narrative = result.extensions.get("narrative") if isinstance(result.extensions, dict) else {}
        insufficient_grounding = False
        grounding_level = ""
        if isinstance(existing_narrative, dict):
            insufficient_grounding = bool(existing_narrative.get("insufficient_grounding"))
            grounding_level = str(existing_narrative.get("grounding_level") or "")
        extensions = dict(result.extensions if isinstance(result.extensions, dict) else {})
        extensions["narrative"] = {
            "source": metadata.source,
            "match_mode": metadata.match_mode,
            "fields_rewritten": list(metadata.fields_rewritten),
            "model": metadata.model,
            "prompt_version": metadata.prompt_version,
            "validation_passed": metadata.validation_passed,
            "failure_reason": metadata.failure_reason,
            "axis": metadata.axis or self._narrative_axis(result),
            "llm_invoked": metadata.llm_invoked,
            "llm_call_count": metadata.llm_call_count,
            "fallback_used": metadata.fallback_used,
            "slim_payload_hash": metadata.slim_payload_hash,
            "block_match_modes": dict(metadata.block_match_modes),
            "insufficient_grounding": insufficient_grounding,
            "grounding_level": grounding_level,
        }
        if augmentation.narrative_layer is None:
            return result.model_copy(
                update={
                    "extensions": extensions,
                    "narrative_layer": None,
                    "narrative_metadata": metadata,
                    "validated_explanation_blocks": [
                        item.model_copy(deep=True) for item in augmentation.validated_explanation_blocks
                    ],
                    "narrative_guard_metadata": metadata,
                }
            )
        update_payload = {
            "report_purpose": augmentation.narrative_layer.report_purpose or result.report_purpose,
            "primary_judgment_reason": augmentation.narrative_layer.primary_judgment_reason or result.primary_judgment_reason,
            "one_line_conclusion": augmentation.narrative_layer.one_line_conclusion or result.one_line_conclusion,
            "executive_summary_v2": (
                list(augmentation.narrative_layer.executive_summary_v2)
                if augmentation.narrative_layer.executive_summary_v2
                else list(result.executive_summary_v2)
            ),
            "extensions": extensions,
            "narrative_layer": augmentation.narrative_layer,
            "narrative_metadata": metadata,
            "validated_explanation_blocks": [
                item.model_copy(deep=True) for item in augmentation.validated_explanation_blocks
            ],
            "narrative_guard_metadata": metadata,
        }
        return result.model_copy(update=update_payload)

    def freeze_canonical_payload(
        self,
        *,
        prepared,
        result: StructuredRebuildResult,
    ) -> CanonicalRebuildPayload:
        if result.canonical_payload is not None:
            return result.canonical_payload.model_copy(deep=True)
        request_context = CanonicalRequestContext(
            goal=str(getattr(prepared, "goal", "") or ""),
            constraints=list(getattr(prepared, "constraints", []) or []),
            scope_limited=bool(getattr(prepared, "scope_limited", False)),
            question_axis=self.template_support.resolve_question_axis(
                prepared,
                family=str(getattr(getattr(result, "family_classification", None), "family", "") or "").strip(),
                narrative_axis=str(getattr(result, "narrative_axis", "") or "").strip(),
            ),
            primary_feature_mode=str(getattr(getattr(prepared, "signals", None), "primary_feature_mode", "") or ""),
            secondary_feature_mode=str(getattr(getattr(prepared, "signals", None), "secondary_feature_mode", "") or ""),
            concept_signals=list(getattr(getattr(prepared, "signals", None), "concepts", []) or []),
            accounting_asset_name=str(getattr(prepared, "accounting_asset_name", "") or ""),
        )
        return self.freeze_canonical_payload_from_result(result, request_context=request_context)

    def freeze_canonical_payload_from_result(
        self,
        result: StructuredRebuildResult,
        *,
        request_context: CanonicalRequestContext | None = None,
    ) -> CanonicalRebuildPayload:
        if result.canonical_payload is not None:
            return result.canonical_payload.model_copy(deep=True)
        return CanonicalRebuildPayload(
            request_context=request_context or CanonicalRequestContext(question_axis=str(getattr(result, "question_axis", "") or "").strip()),
            function_classification=CanonicalFunctionClassification(
                primary_judgment=result.primary_judgment,
                template_judgment=result.template_judgment,
                structural_judgment=result.structural_judgment,
                narrative_axis=result.narrative_axis,
                feature_signal_mode=result.feature_signal_mode,
                pattern_candidates=list(result.pattern_candidates),
            ),
            structure_snapshot=deepcopy(result.structure_snapshot),
            diagnosis_report=deepcopy(result.diagnosis_report),
            decision_summary=deepcopy(result.decision_summary),
            analysis_summary=list(result.analysis_summary),
            core_business_rules=list(result.core_business_rules),
            grounded_business_rules=list(result.grounded_business_rules),
            decision_items=list(result.decision_items),
            retained_contracts=list(result.retained_contracts),
            design_options=list(result.design_options),
            recommended_option=result.recommended_option.model_copy(deep=True) if result.recommended_option else None,
            execution_plan=[item.model_copy(deep=True) for item in result.execution_plan],
            recommended_directions=list(result.recommended_directions),
            risks=list(result.risks),
            missing_context_details=[item.model_copy(deep=True) for item in result.missing_context_details],
            appendix=deepcopy(result.appendix),
        )

    def build_slim_payload(
        self,
        *,
        canonical_payload: CanonicalRebuildPayload,
        result: StructuredRebuildResult,
        explanation_blocks: list[DeterministicExplanationBlock] | None = None,
    ) -> SlimNarrativePayload:
        if explanation_blocks is None:
            explanation_blocks = self.build_deterministic_explanation_blocks(
                canonical_payload=canonical_payload,
                result=result,
            )
        evidence_items = []
        for raw in self._evidence_index(canonical_payload)[:6]:
            evidence_items.append(
                SlimEvidenceItem(
                    evidence_id=str(raw.get("evidence_id") or "").strip(),
                    asset_name=str(raw.get("asset_name") or "").strip(),
                    asset_type=str(raw.get("asset_type") or "").strip(),
                    locator=str(raw.get("locator") or "").strip(),
                    excerpt=self._compact_excerpt(str(raw.get("excerpt") or "").strip()),
                )
            )
        grounded_rules = []
        for rule in canonical_payload.grounded_business_rules[:5]:
            grounded_rules.append(
                SlimGroundedRule(
                    title=rule.title,
                    description=rule.description,
                    evidence_refs=self._rule_evidence_refs(rule, canonical_payload),
                )
            )
        decision_items = []
        for item in canonical_payload.decision_items[:4]:
            decision_items.append(
                SlimDecisionItem(
                    statement=item.statement,
                    rationale=item.rationale,
                    evidence_refs=self._decision_evidence_refs(item, canonical_payload),
                )
            )
        retained_contracts = [
            SlimRetainedContract(item=item.item, basis=item.basis)
            for item in canonical_payload.retained_contracts[:4]
        ]
        execution_plan = [
            SlimExecutionItem(
                week_label=item.week_label,
                goal=item.goal,
                deliverables=list(item.deliverables[:3]),
            )
            for item in canonical_payload.execution_plan[:4]
        ]
        execution_stages = (
            result.improvement_plan_bundle.get("execution_stages")
            if isinstance(result.improvement_plan_bundle, dict)
            else []
        )
        execution_stages = execution_stages if isinstance(execution_stages, list) else []
        consulting_seed = build_consulting_min_contract(
            {
                "analysis_summary": list(canonical_payload.analysis_summary),
                "core_conclusion": str(result.one_line_conclusion or "").strip(),
                "grounded_business_rules": [item.model_dump() for item in canonical_payload.grounded_business_rules],
                "retained_contracts": [item.model_dump() for item in canonical_payload.retained_contracts],
                "decision_items": [item.model_dump() for item in canonical_payload.decision_items],
                "priority_split_items": [],
                "execution_plan": [item.model_dump() for item in canonical_payload.execution_plan],
                "recommended_directions": list(canonical_payload.recommended_directions),
                "risks": list(canonical_payload.risks),
                "missing_context_details": [item.model_dump() for item in canonical_payload.missing_context_details],
            }
        ).model_dump()
        return SlimNarrativePayload(
            request_context={
                "goal": canonical_payload.request_context.goal,
                "constraints": list(canonical_payload.request_context.constraints),
                "scope_limited": canonical_payload.request_context.scope_limited,
                "question_axis": canonical_payload.request_context.question_axis,
                "primary_feature_mode": canonical_payload.request_context.primary_feature_mode,
                "secondary_feature_mode": canonical_payload.request_context.secondary_feature_mode,
                "concept_signals": list(canonical_payload.request_context.concept_signals[:8]),
                "accounting_asset_name": canonical_payload.request_context.accounting_asset_name,
            },
            function_classification={
                "primary_judgment": canonical_payload.function_classification.primary_judgment,
                "template_judgment": canonical_payload.function_classification.template_judgment,
                "structural_judgment": canonical_payload.function_classification.structural_judgment,
                "narrative_axis": canonical_payload.function_classification.narrative_axis,
                "feature_signal_mode": canonical_payload.function_classification.feature_signal_mode,
                "pattern_candidates": [item.model_dump() for item in canonical_payload.function_classification.pattern_candidates[:5]],
            },
            analysis_summary=list(canonical_payload.analysis_summary[:5]),
            deterministic_narrative={
                "report_purpose": result.report_purpose,
                "executive_summary_v2": list(result.executive_summary_v2[:4]),
                "one_line_conclusion": result.one_line_conclusion,
                "primary_judgment_reason": result.primary_judgment_reason,
                "recommended_option": self._recommended_option_text(canonical_payload),
                "execution_plan": [
                    self._execution_stage_line(
                        week=week,
                        stage=execution_stages[index] if index < len(execution_stages) else {},
                    )
                    for index, week in enumerate(canonical_payload.execution_plan[:4])
                ],
                "risks": list(canonical_payload.risks[:4]),
            },
            grounded_business_rules=grounded_rules,
            decision_items=decision_items,
            retained_contracts=retained_contracts,
            recommended_option=(
                canonical_payload.recommended_option.model_dump()
                if canonical_payload.recommended_option is not None
                else None
            ),
            execution_plan=execution_plan,
            risks=list(canonical_payload.risks[:5]),
            consulting_contract_seed=consulting_seed,
            evidence_index=evidence_items,
            explanation_blocks=[item.model_copy(deep=True) for item in explanation_blocks],
        )

    def build_deterministic_explanation_blocks(
        self,
        *,
        canonical_payload: CanonicalRebuildPayload,
        result: StructuredRebuildResult,
    ) -> list[DeterministicExplanationBlock]:
        locked_fields = self._locked_fields(canonical_payload)
        operational_context = self._operational_source_context(
            canonical_payload=canonical_payload,
            result=result,
        )
        comparison_surface = self._uses_option_comparison_surface(result)
        report_purpose_lines = (
            self._normalize_candidate_lines(self._comparison_surface_lines(result, "report_purpose"))
            if comparison_surface
            else self._normalize_candidate_lines(result.report_purpose)
        )
        primary_reason_lines = (
            self._normalize_candidate_lines(self._comparison_surface_lines(result, "primary_judgment_reason"))
            if comparison_surface
            else self._normalize_candidate_lines(result.primary_judgment_reason)
        )
        conclusion_lines = (
            self._normalize_candidate_lines(self._comparison_surface_lines(result, "one_line_conclusion"))
            if comparison_surface
            else self._normalize_candidate_lines(result.one_line_conclusion)
        )
        executive_lines = (
            self._normalize_candidate_lines(self._comparison_surface_lines(result, "executive_summary_v2"))
            if comparison_surface
            else self._normalize_candidate_lines(list(result.executive_summary_v2))
        )
        return [
            self._make_block(
                block_id="report_purpose",
                lines=report_purpose_lines,
                locked_fields=locked_fields,
                operational_context=operational_context,
            ),
            self._make_block(
                block_id="primary_judgment_reason",
                lines=primary_reason_lines,
                locked_fields=locked_fields,
                operational_context=operational_context,
            ),
            self._make_block(
                block_id="one_line_conclusion",
                lines=conclusion_lines,
                locked_fields=locked_fields,
                operational_context=operational_context,
            ),
            self._make_block(
                block_id="executive_summary_v2",
                lines=executive_lines,
                locked_fields=locked_fields,
                operational_context=operational_context,
            ),
            self._make_block(
                block_id="recommended_option",
                lines=self._normalize_candidate_lines(self._recommended_option_text(canonical_payload)),
                locked_fields=locked_fields,
            ),
            self._make_execution_plan_block(
                canonical_payload=canonical_payload,
                result=result,
                locked_fields=locked_fields,
            ),
            self._make_risks_block(
                canonical_payload=canonical_payload,
                result=result,
                locked_fields=locked_fields,
            ),
        ]

    def _uses_option_comparison_surface(self, result: StructuredRebuildResult) -> bool:
        classification = getattr(result, "family_classification", None)
        return str(getattr(classification, "family", "") or "").strip() == "option_comparison"

    def _comparison_surface_lines(self, result: StructuredRebuildResult, block_id: str) -> list[str] | str:
        option = self._comparison_primary_option(result)
        option_name = self._comparison_option_label(getattr(option, "name", "") if option is not None else "")
        structure_summary = str(getattr(option, "structure_summary", "") or "").strip() if option is not None else ""
        selection_reason = str(getattr(option, "selection_reason", "") or "").strip() if option is not None else ""
        option_risks = list(getattr(option, "risks", []) or []) if option is not None else []
        display_strategy = str(getattr(getattr(result, "family_classification", None), "display_strategy", "") or "").strip() or "비교 기준 우선"
        option_count = max(len(list(result.design_options or [])), 1)
        if block_id == "report_purpose":
            if option_name:
                return f"복수 선택지를 {display_strategy} 원칙으로 검토해 {self._attach_object_particle(option_name)} 우선 검토안으로 정리하기 위한 보고서입니다."
            return f"복수 선택지를 {display_strategy} 원칙으로 검토해 추천안을 정리하기 위한 보고서입니다."
        if block_id == "primary_judgment_reason":
            if selection_reason and structure_summary:
                return f"비교 기준은 {selection_reason}이며, 핵심 판단 축은 {structure_summary}입니다."
            return selection_reason or structure_summary
        if block_id == "one_line_conclusion":
            if option_name and structure_summary and selection_reason:
                return f"우선 검토안은 {option_name}입니다. {structure_summary}를 기준으로 {selection_reason}"
            if option_name and structure_summary:
                return f"우선 검토안은 {option_name}입니다. {structure_summary}"
            if option_name:
                return f"우선 검토안은 {option_name}입니다."
            return ""
        if block_id == "executive_summary_v2":
            lines = [f"비교 관점: {display_strategy} 기준으로 {option_count}개 선택지를 나란히 검토했습니다."]
            if option_name and structure_summary:
                lines.append(f"우선 검토안: {option_name} - {structure_summary}")
            elif option_name:
                lines.append(f"우선 검토안: {option_name}")
            if selection_reason:
                lines.append(f"선택 이유: {selection_reason}")
            if option_risks:
                lines.append(f"유의점: {str(option_risks[0]).strip()}")
            return lines
        return ""

    def _comparison_primary_option(self, result: StructuredRebuildResult) -> Any | None:
        if result.recommended_option is not None:
            return result.recommended_option
        for item in list(result.design_options or []):
            if bool(getattr(item, "recommended", False)):
                return item
        options = list(result.design_options or [])
        return options[0] if options else None

    def _comparison_option_label(self, name: str) -> str:
        return re.sub(r"^옵션\s+[A-Z]\.\s*", "", str(name or "").strip()).strip() or str(name or "").strip()

    def _attach_object_particle(self, text: str) -> str:
        stripped = str(text or "").strip()
        if not stripped:
            return stripped
        code = ord(stripped[-1])
        if 0xAC00 <= code <= 0xD7A3:
            has_batchim = (code - 0xAC00) % 28 != 0
            return stripped + ("을" if has_batchim else "를")
        return stripped + "을"

    def materialize_narrative_layer(
        self,
        blocks: list[DeterministicExplanationBlock],
    ) -> RebuildNarrativeLayer:
        block_map = {item.block_id: item for item in blocks}
        return RebuildNarrativeLayer(
            report_purpose=self._single_text(block_map.get("report_purpose")),
            primary_judgment_reason=self._single_text(block_map.get("primary_judgment_reason")),
            one_line_conclusion=self._single_text(block_map.get("one_line_conclusion")),
            executive_summary_v2=self._line_list(block_map.get("executive_summary_v2")),
            recommended_option=self._single_text(block_map.get("recommended_option")),
            execution_plan=self._line_list(block_map.get("execution_plan")),
            risks=self._line_list(block_map.get("risks")),
        )

    def resolve_explanation_blocks(
        self,
        *,
        candidate: dict[str, Any],
        canonical_payload: CanonicalRebuildPayload,
        slim_payload: SlimNarrativePayload,
    ) -> tuple[
        list[DeterministicExplanationBlock],
        list[NarrativeValidationResult],
        list[NarrativeBlockRewriteMetadata],
    ]:
        deterministic_blocks = [
            item.model_copy(deep=True) for item in slim_payload.explanation_blocks
        ]
        resolved_blocks: list[DeterministicExplanationBlock] = []
        block_results: list[NarrativeValidationResult] = []
        rewrite_metadata: list[NarrativeBlockRewriteMetadata] = []
        for block in deterministic_blocks:
            candidate_lines = self._extract_candidate_block_lines(candidate, block.block_id)
            validation = self.validate_explanation_block(
                block=block,
                rewritten_lines=candidate_lines,
                canonical_payload=canonical_payload,
                slim_payload=slim_payload,
            )
            block_results.append(validation)
            source = "ai" if validation.validation_passed else "deterministic_fallback"
            resolved_lines = (
                list(candidate_lines)
                if validation.validation_passed and candidate_lines
                else list(block.deterministic_lines)
            )
            metadata = NarrativeBlockRewriteMetadata(
                block_id=block.block_id,
                source=source,
                validation_passed=validation.validation_passed,
                failure_reason=validation.failure_reason,
                match_mode=validation.match_mode,
                fields_rewritten=[block.block_id] if source == "ai" else [],
            )
            rewrite_metadata.append(metadata)
            self._log_block_validation(
                block_id=block.block_id,
                validation_passed=validation.validation_passed,
                rule=validation.failure_reason or self._pass_rule_for_match_mode(validation.match_mode),
                match_mode=validation.match_mode,
            )
            resolved_blocks.append(
                block.model_copy(
                    update={
                        "resolved_lines": resolved_lines,
                        "rewrite_metadata": metadata,
                    }
                )
            )
        return resolved_blocks, block_results, rewrite_metadata

    def validate_explanation_block(
        self,
        *,
        block: DeterministicExplanationBlock,
        rewritten_lines: list[str],
        canonical_payload: CanonicalRebuildPayload,
        slim_payload: SlimNarrativePayload,
    ) -> NarrativeValidationResult:
        candidate_lines = self._normalize_candidate_lines(rewritten_lines)
        if not candidate_lines:
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=FAILURE_EMPTY_BLOCK_CANDIDATE,
                match_mode=MATCH_MODE_FAILED,
            )
        layer = self._layer_from_block_lines(block.block_id, candidate_lines)
        if not self._validate_forbidden_expressions(layer):
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=FAILURE_FORBIDDEN_EXPRESSION,
                match_mode=MATCH_MODE_FAILED,
            )
        if not self._validate_priority_invariance(layer, slim_payload):
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=FAILURE_PRIORITY_MUTATION,
                match_mode=MATCH_MODE_FAILED,
                mutated_locked_fields=["priority_score"],
            )
        if not self._validate_recommended_option_invariance(layer, canonical_payload):
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=FAILURE_RECOMMENDED_OPTION_MUTATION,
                match_mode=MATCH_MODE_FAILED,
                mutated_locked_fields=["recommended_strategy"],
            )
        if not self._validate_classification_invariance(layer, canonical_payload):
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=FAILURE_CLASSIFICATION_MUTATION,
                match_mode=MATCH_MODE_FAILED,
                mutated_locked_fields=["decision_type"],
            )
        if not self._validate_diagnosis_invariance(layer, canonical_payload):
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=FAILURE_DIAGNOSIS_MUTATION,
                match_mode=MATCH_MODE_FAILED,
            )
        recommended_option_name_failure, recommended_option_match_mode = self._recommended_option_name_failure(
            block,
            candidate_lines,
        )
        if recommended_option_name_failure:
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=recommended_option_name_failure,
                match_mode=MATCH_MODE_FAILED,
                mutated_locked_fields=["recommended_strategy"],
            )

        execution_plan_failure = self._execution_plan_order_failure(block, candidate_lines)
        if execution_plan_failure:
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=execution_plan_failure,
                match_mode=MATCH_MODE_FAILED,
            )
        execution_plan_task_failure, execution_plan_match_mode = self._execution_plan_task_coverage_failure(
            block,
            candidate_lines,
        )
        if execution_plan_task_failure:
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=execution_plan_task_failure,
                match_mode=MATCH_MODE_FAILED,
            )
        risks_failure = self._risks_shape_failure(block, candidate_lines)
        if risks_failure:
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=risks_failure,
                match_mode=MATCH_MODE_FAILED,
            )
        risks_generalization = self._risk_generalization_failure(block, candidate_lines, slim_payload)
        if risks_generalization:
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=risks_generalization,
                match_mode=MATCH_MODE_FAILED,
            )
        risks_coverage_failure, risks_match_mode = self._risk_coverage_failure(block, candidate_lines)
        if risks_coverage_failure:
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=risks_coverage_failure,
                match_mode=MATCH_MODE_FAILED,
            )
        risks_severity_failure = self._risk_severity_failure(block, candidate_lines)
        if risks_severity_failure:
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=risks_severity_failure,
                match_mode=MATCH_MODE_FAILED,
            )
        operational_failure = self._operational_source_governance_failure(block, candidate_lines)
        if operational_failure:
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=operational_failure,
                match_mode=MATCH_MODE_FAILED,
            )
        comparison_failure = self._option_comparison_governance_failure(block, candidate_lines)
        if comparison_failure:
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=comparison_failure,
                match_mode=MATCH_MODE_FAILED,
            )

        missing_critical_facts, critical_fact_match_mode = self._missing_critical_fact_ids(block, candidate_lines)
        missing_evidence, evidence_match_mode = self._missing_evidence_ids(block, candidate_lines)
        mutated_locked_fields = self._mutated_locked_field_names(block, candidate_lines)
        unsupported_claims = self._unsupported_claims(block, candidate_lines, slim_payload)
        ambiguous_merge = self._detect_ambiguous_fact_merge(block, candidate_lines, missing_critical_facts)

        if mutated_locked_fields:
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=FAILURE_LOCKED_FIELD_MUTATION,
                match_mode=MATCH_MODE_FAILED,
                mutated_locked_fields=mutated_locked_fields,
            )
        if unsupported_claims:
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=FAILURE_UNSUPPORTED_CLAIM,
                match_mode=MATCH_MODE_FAILED,
                unsupported_claims=unsupported_claims,
            )
        if missing_evidence:
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=FAILURE_DECISION_EVIDENCE_COVERAGE_MISSING,
                match_mode=MATCH_MODE_FAILED,
                missing_evidence_ids=missing_evidence,
            )
        if missing_critical_facts:
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=FAILURE_CRITICAL_FACT_MISSING,
                match_mode=MATCH_MODE_FAILED,
                missing_critical_fact_ids=missing_critical_facts,
                ambiguous_fact_merge_detected=ambiguous_merge,
            )
        if ambiguous_merge:
            return NarrativeValidationResult(
                block_id=block.block_id,
                validation_passed=False,
                failure_reason=FAILURE_AMBIGUOUS_FACT_MERGE,
                match_mode=MATCH_MODE_FAILED,
                ambiguous_fact_merge_detected=True,
            )
        match_mode = self._looser_match_mode(
            recommended_option_match_mode,
            execution_plan_match_mode,
            risks_match_mode,
            critical_fact_match_mode,
            evidence_match_mode,
        )
        return NarrativeValidationResult(
            block_id=block.block_id,
            validation_passed=True,
            failure_reason="",
            match_mode=match_mode,
        )

    def validate_candidate(
        self,
        *,
        candidate: dict[str, Any],
        canonical_payload: CanonicalRebuildPayload,
        slim_payload: SlimNarrativePayload,
        result: StructuredRebuildResult,
    ) -> tuple[RebuildNarrativeLayer | None, str]:
        validated, failure_reason = self._validate_candidate_schema(candidate=candidate)
        if validated is None:
            return None, failure_reason
        if not self._has_meaningful_content(validated):
            return None, FAILURE_EMPTY_NARRATIVE_LAYER
        if not self._validate_outline_keys(validated.consulting_deck_outline):
            return None, FAILURE_INVALID_CONSULTING_DECK_OUTLINE
        if not self._validate_evidence_refs(validated, canonical_payload):
            return None, FAILURE_INVALID_EVIDENCE_REF
        if not self._validate_recommended_option_invariance(validated, canonical_payload):
            return None, FAILURE_RECOMMENDED_OPTION_MUTATION
        if not self._validate_classification_invariance(validated, canonical_payload):
            return None, FAILURE_CLASSIFICATION_MUTATION
        if not self._validate_diagnosis_invariance(validated, canonical_payload):
            return None, FAILURE_DIAGNOSIS_MUTATION
        if not self._validate_priority_invariance(validated, slim_payload):
            return None, FAILURE_PRIORITY_MUTATION
        if not self._validate_no_new_facts(validated, slim_payload):
            return None, FAILURE_GROUNDED_FACT_MISMATCH
        if not self._validate_forbidden_expressions(validated):
            return None, FAILURE_FORBIDDEN_EXPRESSION
        return validated, ""

    def _validate_candidate_schema(
        self,
        *,
        candidate: dict[str, Any],
    ) -> tuple[RebuildNarrativeLayer | None, str]:
        if any(key in FORBIDDEN_TOP_LEVEL_FIELDS for key in candidate):
            return None, FAILURE_FORBIDDEN_TOP_LEVEL_FIELD
        try:
            validated = RebuildNarrativeLayer.model_validate(candidate)
        except ValidationError:
            return None, FAILURE_SCHEMA_VALIDATION_ERROR
        if not self._validate_rewrite_scope(validated):
            return None, FAILURE_REWRITE_SCOPE_VIOLATION
        return validated, ""

    def _make_block(
        self,
        *,
        block_id: str,
        lines: list[str],
        locked_fields: NarrativeLockedFields,
        operational_context: dict[str, Any] | None = None,
    ) -> DeterministicExplanationBlock:
        cleaned_lines = self._normalize_candidate_lines(lines)
        if operational_context and operational_context.get("active") and block_id in {
            "report_purpose",
            "primary_judgment_reason",
            "one_line_conclusion",
            "executive_summary_v2",
        }:
            return self._make_operational_source_block(
                block_id=block_id,
                lines=cleaned_lines,
                locked_fields=locked_fields,
                operational_context=operational_context,
            )
        critical_facts = [
            NarrativeCriticalFact(fact_id=f"{block_id}:{index + 1}", text=text)
            for index, text in enumerate(cleaned_lines)
        ]
        return DeterministicExplanationBlock(
            block_id=block_id,
            field_type=BLOCK_FIELD_TYPES.get(block_id, "text"),
            deterministic_lines=cleaned_lines,
            resolved_lines=list(cleaned_lines),
            critical_facts=critical_facts,
            decision_driving_evidence=[],
            locked_fields=locked_fields.model_copy(deep=True),
        )

    def _make_operational_source_block(
        self,
        *,
        block_id: str,
        lines: list[str],
        locked_fields: NarrativeLockedFields,
        operational_context: dict[str, Any],
    ) -> DeterministicExplanationBlock:
        critical_facts = [
            NarrativeCriticalFact(fact_id=f"{block_id}:{index + 1}", text=text)
            for index, text in enumerate(lines)
        ]
        identity_anchor = str(operational_context.get("identity_anchor") or "").strip()
        flow_anchor = str(operational_context.get("flow_anchor") or "").strip()
        object_anchor = str(operational_context.get("object_anchor") or "").strip()
        risk_anchor = str(operational_context.get("risk_anchor") or "").strip()
        restore_anchor = str(operational_context.get("restore_anchor") or "").strip()
        extra_fact_map = {
            "report_purpose": [
                ("flow", flow_anchor),
            ],
            "primary_judgment_reason": [
                ("identity", identity_anchor),
                ("restore", restore_anchor),
                ("flow", flow_anchor),
            ],
            "one_line_conclusion": [
                ("identity", identity_anchor),
                ("objects", object_anchor),
                ("flow", flow_anchor),
            ],
            "executive_summary_v2": [
                ("identity", identity_anchor),
                ("objects", object_anchor),
                ("flow", flow_anchor),
                ("risk", risk_anchor),
            ],
        }
        for suffix, text in extra_fact_map.get(block_id, []):
            if text:
                critical_facts.append(
                    NarrativeCriticalFact(
                        fact_id=f"operational:{block_id}:{suffix}",
                        text=text,
                    )
                )
        evidence_items: list[NarrativeDecisionDrivingEvidence] = []
        if block_id in {"one_line_conclusion", "executive_summary_v2"} and object_anchor:
            evidence_items.append(
                NarrativeDecisionDrivingEvidence(
                    evidence_id=f"operational:{block_id}:objects",
                    asset_name="operational_objects",
                    locator="current_state_objects",
                    summary=object_anchor,
                )
            )
        if block_id in {"primary_judgment_reason", "one_line_conclusion", "executive_summary_v2"} and flow_anchor:
            evidence_items.append(
                NarrativeDecisionDrivingEvidence(
                    evidence_id=f"operational:{block_id}:flow",
                    asset_name="operational_flow",
                    locator="current_state_flow",
                    summary=flow_anchor,
                )
            )
        if block_id == "executive_summary_v2" and risk_anchor:
            evidence_items.append(
                NarrativeDecisionDrivingEvidence(
                    evidence_id="operational:executive_summary_v2:risk",
                    asset_name="operational_risk",
                    locator="risk_checkpoint",
                    summary=risk_anchor,
                )
            )
        return DeterministicExplanationBlock(
            block_id=block_id,
            field_type=BLOCK_FIELD_TYPES.get(block_id, "text"),
            deterministic_lines=list(lines),
            resolved_lines=list(lines),
            critical_facts=critical_facts,
            decision_driving_evidence=evidence_items,
            locked_fields=locked_fields.model_copy(deep=True),
        )

    def _make_execution_plan_block(
        self,
        *,
        canonical_payload: CanonicalRebuildPayload,
        result: StructuredRebuildResult,
        locked_fields: NarrativeLockedFields,
    ) -> DeterministicExplanationBlock:
        execution_stages = (
            result.improvement_plan_bundle.get("execution_stages")
            if isinstance(result.improvement_plan_bundle, dict)
            else []
        )
        execution_stages = execution_stages if isinstance(execution_stages, list) else []
        lines: list[str] = []
        critical_facts: list[NarrativeCriticalFact] = []
        evidence_items: list[NarrativeDecisionDrivingEvidence] = []
        for index, week in enumerate(canonical_payload.execution_plan):
            stage = execution_stages[index] if index < len(execution_stages) and isinstance(execution_stages[index], dict) else {}
            line = self._execution_stage_line(
                week=week,
                stage=stage,
                family=str(getattr(getattr(result, "family_classification", None), "family", "") or "").strip(),
            )
            if not line:
                continue
            stage_id = str(stage.get("stage_id") or f"execution_stage:{index + 1}").strip() or f"execution_stage:{index + 1}"
            lines.append(line)
            critical_facts.append(NarrativeCriticalFact(fact_id=stage_id, text=line))
            first_task = self._execution_stage_primary_task(week=week, stage=stage)
            if first_task:
                evidence_items.append(
                    NarrativeDecisionDrivingEvidence(
                        evidence_id=stage_id,
                        asset_name="execution_stage",
                        locator=str(stage.get("title") or getattr(week, "goal", "") or "").strip(),
                        summary=first_task,
                    )
                )
            else:
                evidence_items.append(
                    NarrativeDecisionDrivingEvidence(
                        evidence_id=stage_id,
                        asset_name="execution_stage",
                        locator=str(stage.get("title") or getattr(week, "goal", "") or "").strip(),
                        summary="",
                    )
                )
        return DeterministicExplanationBlock(
            block_id="execution_plan",
            field_type="list",
            deterministic_lines=lines,
            resolved_lines=list(lines),
            critical_facts=critical_facts,
            decision_driving_evidence=evidence_items,
            locked_fields=locked_fields.model_copy(deep=True),
        )

    def _make_risks_block(
        self,
        *,
        canonical_payload: CanonicalRebuildPayload,
        result: StructuredRebuildResult,
        locked_fields: NarrativeLockedFields,
    ) -> DeterministicExplanationBlock:
        risk_checkpoints = (
            result.improvement_plan_bundle.get("risk_checkpoints")
            if isinstance(result.improvement_plan_bundle, dict)
            else []
        )
        risk_checkpoints = risk_checkpoints if isinstance(risk_checkpoints, list) else []
        lines: list[str] = []
        critical_facts: list[NarrativeCriticalFact] = []
        evidence_items: list[NarrativeDecisionDrivingEvidence] = []
        for index, risk in enumerate(canonical_payload.risks):
            risk_text = str(risk or "").strip()
            if not risk_text:
                continue
            checkpoint = risk_checkpoints[index] if index < len(risk_checkpoints) and isinstance(risk_checkpoints[index], dict) else {}
            checkpoint_id = str(checkpoint.get("checkpoint_id") or f"risk:{index + 1}").strip() or f"risk:{index + 1}"
            lines.append(risk_text)
            critical_facts.append(NarrativeCriticalFact(fact_id=checkpoint_id, text=risk_text))
            evidence_items.append(
                NarrativeDecisionDrivingEvidence(
                    evidence_id=checkpoint_id,
                    asset_name="risk_checkpoint",
                    locator=str(checkpoint.get("title") or "").strip(),
                    summary=str(checkpoint.get("description") or risk_text).strip(),
                )
            )
        return DeterministicExplanationBlock(
            block_id="risks",
            field_type="list",
            deterministic_lines=lines,
            resolved_lines=list(lines),
            critical_facts=critical_facts,
            decision_driving_evidence=evidence_items,
            locked_fields=locked_fields.model_copy(deep=True),
        )

    def _locked_fields(self, canonical_payload: CanonicalRebuildPayload) -> NarrativeLockedFields:
        recommended_strategy = ""
        recommended_option_aliases: list[str] = []
        if canonical_payload.recommended_option is not None:
            recommended_strategy = str(canonical_payload.recommended_option.name or "").strip()
            recommended_option_aliases = self._recommended_option_aliases(recommended_strategy)
        decision_type = str(canonical_payload.function_classification.primary_judgment or "").strip()
        family = str(canonical_payload.input_family_classification.family or "").strip()
        display_strategy = str(canonical_payload.input_family_classification.display_strategy or "").strip()
        return NarrativeLockedFields(
            recommended_strategy=recommended_strategy,
            recommended_option_aliases=recommended_option_aliases,
            decision_type=decision_type,
            family=family,
            display_strategy=display_strategy,
            priority_score=None,
            score_breakdown={},
        )

    def _extract_candidate_block_lines(self, candidate: dict[str, Any], block_id: str) -> list[str]:
        return self._normalize_candidate_lines(candidate.get(block_id))

    def _normalize_candidate_lines(self, value: Any) -> list[str]:
        if isinstance(value, list):
            normalized = [str(item or "").strip() for item in value]
            return [item for item in normalized if item]
        text = str(value or "").strip()
        return [text] if text else []

    def _single_text(self, block: DeterministicExplanationBlock | None) -> str:
        if block is None:
            return ""
        lines = self._line_list(block)
        return lines[0] if lines else ""

    def _line_list(self, block: DeterministicExplanationBlock | None) -> list[str]:
        if block is None:
            return []
        lines = list(block.resolved_lines or block.deterministic_lines)
        return [str(item or "").strip() for item in lines if str(item or "").strip()]

    def _layer_from_block_lines(self, block_id: str, lines: list[str]) -> RebuildNarrativeLayer:
        normalized = self._normalize_candidate_lines(lines)
        if block_id == "executive_summary_v2":
            return RebuildNarrativeLayer(executive_summary_v2=normalized)
        if block_id == "execution_plan":
            return RebuildNarrativeLayer(execution_plan=normalized)
        if block_id == "risks":
            return RebuildNarrativeLayer(risks=normalized)
        if block_id == "report_purpose":
            return RebuildNarrativeLayer(report_purpose=normalized[0] if normalized else "")
        if block_id == "primary_judgment_reason":
            return RebuildNarrativeLayer(primary_judgment_reason=normalized[0] if normalized else "")
        if block_id == "recommended_option":
            return RebuildNarrativeLayer(recommended_option=normalized[0] if normalized else "")
        return RebuildNarrativeLayer(one_line_conclusion=normalized[0] if normalized else "")

    def _recommended_option_text(self, canonical_payload: CanonicalRebuildPayload) -> str:
        option = canonical_payload.recommended_option
        if option is None:
            return ""
        name = str(option.name or "").strip()
        structure_summary = str(option.structure_summary or "").strip()
        selection_reason = str(option.selection_reason or "").strip()
        if name and structure_summary and selection_reason:
            return f"추천안은 {name}이며, {structure_summary}를 기준으로 {selection_reason}"
        if name and selection_reason:
            return f"추천안은 {name}이며, {selection_reason}"
        if structure_summary and selection_reason:
            return f"{structure_summary}를 기준으로 {selection_reason}"
        return name or structure_summary or selection_reason

    def _execution_stage_line(self, *, week, stage: dict[str, Any], family: str = "") -> str:
        week_label = str(getattr(week, "week_label", "") or "").strip()
        stage_title = str(stage.get("title") or getattr(week, "goal", "") or "").strip()
        first_task = self._execution_stage_primary_task(week=week, stage=stage)
        base = f"{week_label}: {stage_title}" if week_label and stage_title else (stage_title or week_label)
        if family == "operational_source" and first_task and base:
            return f"{base}. 주요 확인 항목은 {first_task}입니다."
        if family == "option_comparison" and first_task and base:
            return f"{base}. 주요 적용 기준은 {first_task}입니다."
        if first_task and base:
            return f"{base}. 주요 작업은 {first_task}입니다."
        return base

    def _execution_stage_primary_task(self, *, week, stage: dict[str, Any]) -> str:
        stage_tasks = stage.get("tasks") if isinstance(stage, dict) else []
        if isinstance(stage_tasks, list):
            first_task = next((str(item or "").strip() for item in stage_tasks if str(item or "").strip()), "")
            if first_task:
                return first_task
        week_tasks = getattr(week, "tasks", []) or []
        if isinstance(week_tasks, list):
            return next((str(item or "").strip() for item in week_tasks if str(item or "").strip()), "")
        return ""

    def _missing_critical_fact_ids(
        self,
        block: DeterministicExplanationBlock,
        candidate_lines: list[str],
    ) -> tuple[list[str], str]:
        if block.block_id in {"report_purpose", "primary_judgment_reason", "executive_summary_v2"} and not self._has_operational_source_marker(block):
            candidate_text = " ".join(candidate_lines)
            fact_text = " ".join(str(fact.text or "").strip() for fact in block.critical_facts if str(fact.text or "").strip())
            if self._exact_match(fact_text, candidate_text, min_overlap=1):
                return [], MATCH_MODE_EXACT
            if self._normalized_synonym_match(fact_text, candidate_text, min_overlap=1):
                return [], MATCH_MODE_NORMALIZED
            return [], MATCH_MODE_NORMALIZED
        candidate_text = " ".join(candidate_lines)
        missing: list[str] = []
        match_modes: list[str] = []
        for fact in block.critical_facts:
            if not fact.text.strip():
                continue
            match_mode = self._match_mode_with_relaxation(
                fact.text,
                candidate_text,
                exact_min_overlap=1,
                normalized_min_overlap=1,
            )
            if match_mode == MATCH_MODE_FAILED:
                missing.append(fact.fact_id)
                continue
            match_modes.append(match_mode)
        return missing, self._aggregate_success_match_mode(match_modes)

    def _missing_evidence_ids(
        self,
        block: DeterministicExplanationBlock,
        candidate_lines: list[str],
    ) -> tuple[list[str], str]:
        if not block.decision_driving_evidence:
            return [], MATCH_MODE_EXACT
        candidate_text = " ".join(candidate_lines)
        missing: list[str] = []
        match_modes: list[str] = []
        for evidence in block.decision_driving_evidence:
            evidence_text = " ".join(
                [
                    str(evidence.summary or ""),
                    str(evidence.asset_name or ""),
                    str(evidence.locator or ""),
                ]
            )
            if not evidence_text.strip():
                continue
            match_mode = self._match_mode_with_relaxation(
                evidence_text,
                candidate_text,
                exact_min_overlap=1,
                normalized_min_overlap=1,
            )
            if match_mode == MATCH_MODE_FAILED:
                missing.append(evidence.evidence_id or evidence.summary or evidence.asset_name or block.block_id)
                continue
            match_modes.append(match_mode)
        return missing, self._aggregate_success_match_mode(match_modes)

    def _mutated_locked_field_names(
        self,
        block: DeterministicExplanationBlock,
        candidate_lines: list[str],
    ) -> list[str]:
        joined = " ".join(candidate_lines).lower()
        mutated: list[str] = []
        recommended_strategy = str(block.locked_fields.recommended_strategy or "").strip().lower()
        if recommended_strategy:
            mentioned = {token for token in STRATEGY_TOKENS if token in joined}
            if mentioned and recommended_strategy not in mentioned:
                mutated.append("recommended_strategy")
        decision_type = str(block.locked_fields.decision_type or "").strip().lower()
        if decision_type:
            mentioned = {token for token in CLASSIFICATION_TOKENS if token in joined}
            if mentioned and decision_type not in mentioned:
                mutated.append("decision_type")
        if block.locked_fields.priority_score is not None:
            matches = []
            for pattern in PRIORITY_MUTATION_PATTERNS:
                matches.extend(re.findall(pattern, joined, flags=re.IGNORECASE))
            if matches and str(block.locked_fields.priority_score) not in joined:
                mutated.append("priority_score")
        return mutated

    def _unsupported_claims(
        self,
        block: DeterministicExplanationBlock,
        candidate_lines: list[str],
        slim_payload: SlimNarrativePayload,
    ) -> list[str]:
        allowed_source = {
            "deterministic_lines": list(block.deterministic_lines),
            "critical_facts": [item.text for item in block.critical_facts],
            "decision_driving_evidence": [
                {
                    "summary": item.summary,
                    "asset_name": item.asset_name,
                    "locator": item.locator,
                }
                for item in block.decision_driving_evidence
            ],
            "locked_fields": block.locked_fields.model_dump(),
            "slim_payload": slim_payload.model_dump(),
        }
        allowed_words = self._normalized_salient_words(json.dumps(allowed_source, ensure_ascii=False, sort_keys=True))
        candidate_words = self._normalized_salient_words(" ".join(candidate_lines))
        novel = sorted(item for item in candidate_words if item not in allowed_words)
        min_novel, ratio_threshold = UNSUPPORTED_CLAIM_THRESHOLDS.get(
            block.block_id,
            UNSUPPORTED_CLAIM_THRESHOLDS["default"],
        )
        if len(novel) >= min_novel and len(novel) / max(len(candidate_words), 1) > ratio_threshold:
            return novel
        return []

    def _detect_ambiguous_fact_merge(
        self,
        block: DeterministicExplanationBlock,
        candidate_lines: list[str],
        missing_critical_fact_ids: list[str],
    ) -> bool:
        if len(block.critical_facts) < 2:
            return False
        if not missing_critical_fact_ids:
            return False
        return len(candidate_lines) < len(block.critical_facts)

    def _recommended_option_name_failure(
        self,
        block: DeterministicExplanationBlock,
        candidate_lines: list[str],
    ) -> tuple[str, str]:
        if block.block_id != "recommended_option":
            return "", MATCH_MODE_EXACT
        locked_name = str(block.locked_fields.recommended_strategy or "").strip()
        if not locked_name:
            return "", MATCH_MODE_EXACT
        joined = " ".join(candidate_lines).strip()
        if locked_name.lower() in joined.lower():
            return "", MATCH_MODE_EXACT
        if self._contains_alias(joined, locked_name):
            return "", MATCH_MODE_NORMALIZED
        for alias in block.locked_fields.recommended_option_aliases or []:
            alias_text = str(alias or "").strip()
            if alias_text and alias_text.lower() in joined.lower():
                return "", MATCH_MODE_NORMALIZED
            if self._contains_alias(joined, alias):
                return "", MATCH_MODE_NORMALIZED
        return FAILURE_RECOMMENDED_OPTION_NAME_MISSING, MATCH_MODE_FAILED

    def _execution_plan_order_failure(
        self,
        block: DeterministicExplanationBlock,
        candidate_lines: list[str],
    ) -> str:
        if block.block_id != "execution_plan":
            return ""
        if len(candidate_lines) != len(block.critical_facts):
            return FAILURE_EXECUTION_STAGE_COUNT_MISMATCH
        if not block.critical_facts:
            return ""
        fact_word_sets = [self._normalized_salient_words(item.text) for item in block.critical_facts]
        matched_indices: list[int] = []
        for line in candidate_lines:
            line_words = self._normalized_salient_words(line)
            best_index = -1
            best_score = 0
            for index, fact_words in enumerate(fact_word_sets):
                score = len(line_words.intersection(fact_words))
                if score > best_score:
                    best_index = index
                    best_score = score
            if best_score == 0:
                return ""
            matched_indices.append(best_index)
        expected = list(range(len(block.critical_facts)))
        if matched_indices != expected:
            return FAILURE_EXECUTION_STAGE_ORDER_MUTATION
        return ""

    def _execution_plan_task_coverage_failure(
        self,
        block: DeterministicExplanationBlock,
        candidate_lines: list[str],
    ) -> tuple[str, str]:
        if block.block_id != "execution_plan":
            return "", MATCH_MODE_EXACT
        if len(candidate_lines) != len(block.decision_driving_evidence):
            return "", MATCH_MODE_EXACT
        match_modes: list[str] = []
        for candidate_line, evidence in zip(candidate_lines, block.decision_driving_evidence):
            expected_task = str(evidence.summary or "").strip()
            if not expected_task:
                continue
            match_mode = self._task_match_mode(expected_task=expected_task, candidate_line=candidate_line)
            if match_mode == MATCH_MODE_FAILED:
                return FAILURE_EXECUTION_STAGE_TASK_MISSING, MATCH_MODE_FAILED
            match_modes.append(match_mode)
        return "", self._aggregate_success_match_mode(match_modes)

    def _task_match_mode(self, *, expected_task: str, candidate_line: str) -> str:
        expected_exact = self._task_tokens(expected_task, normalized=False)
        candidate_exact = self._task_tokens(candidate_line, normalized=False)
        if expected_exact and expected_exact.issubset(candidate_exact):
            return MATCH_MODE_EXACT
        expected_normalized = self._task_tokens(expected_task, normalized=True)
        candidate_normalized = self._task_tokens(candidate_line, normalized=True)
        if expected_normalized and expected_normalized.issubset(candidate_normalized):
            return MATCH_MODE_NORMALIZED
        return MATCH_MODE_FAILED

    def _task_tokens(self, text: str, *, normalized: bool) -> set[str]:
        source = self._normalize_match_text(text) if normalized else str(text or "").lower()
        ignored = {"주요", "작업", "주차", "단계", "계획"}
        tokens: set[str] = set()
        for token in re.findall(r"[A-Za-z가-힣][A-Za-z가-힣0-9_/-]{0,}", source):
            token = self._normalize_salient_token(token)
            if not token or len(token) <= 1 or token in ignored:
                continue
            tokens.add(token)
        return tokens

    def _risks_shape_failure(
        self,
        block: DeterministicExplanationBlock,
        candidate_lines: list[str],
    ) -> str:
        if block.block_id != "risks":
            return ""
        if len(candidate_lines) != len(block.critical_facts):
            return FAILURE_RISK_ITEM_COUNT_MISMATCH
        if not block.critical_facts:
            return ""
        fact_word_sets = [self._normalized_salient_words(item.text) for item in block.critical_facts]
        matched_indices: list[int] = []
        for line in candidate_lines:
            line_words = self._normalized_salient_words(line)
            best_index = -1
            best_score = 0
            for index, fact_words in enumerate(fact_word_sets):
                score = len(line_words.intersection(fact_words))
                if score > best_score:
                    best_index = index
                    best_score = score
            if best_score == 0:
                return ""
            matched_indices.append(best_index)
        expected = list(range(len(block.critical_facts)))
        if matched_indices != expected:
            return FAILURE_RISK_ITEM_ORDER_MUTATION
        return ""

    def _risk_coverage_failure(
        self,
        block: DeterministicExplanationBlock,
        candidate_lines: list[str],
    ) -> tuple[str, str]:
        if block.block_id != "risks":
            return "", MATCH_MODE_EXACT
        if len(candidate_lines) != len(block.critical_facts):
            return "", MATCH_MODE_EXACT
        match_modes: list[str] = []
        for candidate_line, fact in zip(candidate_lines, block.critical_facts):
            fact_words = self._normalized_salient_words(fact.text)
            if not fact_words:
                continue
            minimum_overlap = 1 if len(fact_words) <= 2 else 2
            match_mode = self._match_mode_with_relaxation(
                fact.text,
                candidate_line,
                exact_min_overlap=minimum_overlap,
                normalized_min_overlap=minimum_overlap,
            )
            if match_mode == MATCH_MODE_FAILED:
                return FAILURE_RISK_COVERAGE_MISSING, MATCH_MODE_FAILED
            match_modes.append(match_mode)
        return "", self._aggregate_success_match_mode(match_modes)

    def _risk_severity_failure(
        self,
        block: DeterministicExplanationBlock,
        candidate_lines: list[str],
    ) -> str:
        if block.block_id != "risks":
            return ""
        if len(candidate_lines) != len(block.critical_facts):
            return ""
        for candidate_line, fact in zip(candidate_lines, block.critical_facts):
            original_rank = self._risk_severity_rank(fact.text)
            candidate_rank = self._risk_severity_rank(candidate_line)
            if original_rank > 0 and candidate_rank < original_rank:
                return FAILURE_RISK_SEVERITY_DOWNGRADED
        return ""

    def _risk_generalization_failure(
        self,
        block: DeterministicExplanationBlock,
        candidate_lines: list[str],
        slim_payload: SlimNarrativePayload,
    ) -> str:
        if block.block_id != "risks":
            return ""
        allowed_source = {
            "deterministic_lines": list(block.deterministic_lines),
            "critical_facts": [item.text for item in block.critical_facts],
            "decision_driving_evidence": [
                {
                    "summary": item.summary,
                    "asset_name": item.asset_name,
                    "locator": item.locator,
                }
                for item in block.decision_driving_evidence
            ],
            "slim_payload_risks": list(slim_payload.risks),
        }
        allowed_text = json.dumps(allowed_source, ensure_ascii=False, sort_keys=True)
        candidate_text = " ".join(candidate_lines)
        for pattern in RISK_EXAGGERATION_PATTERNS:
            if re.search(pattern, candidate_text, flags=re.IGNORECASE) and not re.search(pattern, allowed_text, flags=re.IGNORECASE):
                return FAILURE_RISK_GENERALIZATION_BEYOND_EVIDENCE
        return ""

    def _risk_severity_rank(self, text: str) -> int:
        normalized = str(text or "")
        for rank, tokens in RISK_SEVERITY_TOKENS:
            if any(token in normalized for token in tokens):
                return rank
        return 0

    def _aggregate_block_failure_reason(self, block_results: list[NarrativeValidationResult]) -> str:
        failures = [item.failure_reason for item in block_results if not item.validation_passed and item.failure_reason]
        return failures[0] if failures else ""

    def _validate_rewrite_scope(self, layer: RebuildNarrativeLayer) -> bool:
        return not layer.decision_narrative and not layer.consulting_deck_outline

    def _build_prompt(self, slim_payload: SlimNarrativePayload) -> str:
        payload = json.dumps(slim_payload.model_dump(), ensure_ascii=False, indent=2)
        operational_guidance = ""
        comparison_guidance = ""
        if self._requires_operational_source_governance(slim_payload):
            operational_guidance = (
                "운영 소스 우선 게이트가 활성화된 입력이다.\n"
                "report_purpose, one_line_conclusion, executive_summary_v2의 첫 문장은 자산 정체와 현행 처리 흐름 설명으로 시작하라.\n"
                "explanation_blocks와 evidence에 있는 실제 객체명과 FIFO lot, 환차손익, 전표, GL 연계 같은 처리 흐름을 사용하라.\n"
                "개선 제안은 뒤에 배치하라.\n"
                "detector_id, validation_guard_leak, layer_leak 같은 내부 detector 이름은 쓰지 마라.\n"
            )
        if self._requires_option_comparison_guidance(slim_payload):
            comparison_guidance = (
                "비교형 surface 게이트가 활성화된 입력이다.\n"
                "report_purpose, one_line_conclusion, executive_summary_v2의 첫 문장은 비교 목적, 추천안, 비교 기준을 중심으로 시작하라.\n"
                "recommended_option이나 design_options에 있는 option name, structure summary, selection reason 안에서만 비교 문구를 만들라.\n"
                "generic 운영 분석 문구나 실행계획 일반론으로 시작하지 마라.\n"
            )
        return (
            "아래 canonical slim payload를 읽고 narrative layer만 보강하라.\n"
            "이 payload는 deterministic engine이 이미 판단을 끝낸 결과다.\n"
            "절대 classification, detector result, recommendation, execution priority, risk priority를 바꾸지 마라.\n"
            "새 사실, 새 규칙, 새 근거, 새 숫자, 새 고유명사를 만들지 마라.\n"
            "source_code, full sql, full ui raw는 없다. 제공된 요약과 evidence refs 안에서만 서술하라.\n"
            "허용 범위는 guard-approved narrative blocks 뿐이다.\n"
            "각 block은 deterministic explanation block을 입력으로 받는다.\n"
            "execution_plan과 risks는 list item count와 순서를 바꾸지 마라.\n"
            "execution_plan은 각 단계의 핵심 작업을 빠뜨리지 마라.\n"
            "recommended_option은 option name을 그대로 유지하라.\n"
            "risks는 severity를 약화하거나 evidence 밖으로 일반화하지 마라.\n"
            "Narrative must only rephrase existing facts, preserve all critical facts, "
            "not omit decision-driving evidence, and not merge distinct facts into ambiguous statements.\n"
            f"{operational_guidance}"
            f"{comparison_guidance}"
            "허용 JSON schema:\n"
            "{\n"
            '  "report_purpose": "string",\n'
            '  "executive_summary_v2": ["string"],\n'
            '  "one_line_conclusion": "string",\n'
            '  "primary_judgment_reason": "string",\n'
            '  "recommended_option": "string",\n'
            '  "execution_plan": ["string"],\n'
            '  "risks": ["string"]\n'
            "}\n"
            "JSON object만 반환하라.\n\n"
            f"{payload}"
        )

    def _system_prompt(self) -> str:
        return (
            "You rewrite only the narrative layer of a deterministic modernization engine. "
            "Do not change facts, classifications, detector outcomes, recommendation, risks, or execution order. "
            "Do not invent evidence. Return JSON only."
        )

    def _parse_response(self, raw_response: Any) -> dict[str, Any] | None:
        raw_text = ""
        for attr in ("content", "text"):
            value = getattr(raw_response, attr, None)
            if isinstance(value, str) and value.strip():
                raw_text = value.strip()
                break
        if not raw_text and isinstance(raw_response, str):
            raw_text = raw_response.strip()
        if not raw_text:
            return None
        try:
            parsed = json.loads(raw_text)
        except Exception:
            match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
            if not match:
                return None
            try:
                parsed = json.loads(match.group(0))
            except Exception:
                return None
        return parsed if isinstance(parsed, dict) else None

    def _payload_hash(self, slim_payload: SlimNarrativePayload) -> str:
        raw = json.dumps(slim_payload.model_dump(), ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _fallback_outcome(
        self,
        *,
        result: StructuredRebuildResult,
        deterministic_blocks: list[DeterministicExplanationBlock],
        failure_reason: str,
        slim_payload_hash: str,
        llm_invoked: bool,
        llm_call_count: int,
        model: str = "",
    ) -> NarrativeAugmentationOutcome:
        block_rewrite_metadata = [
            NarrativeBlockRewriteMetadata(
                block_id=item.block_id,
                source="deterministic_fallback",
                validation_passed=False,
                failure_reason=failure_reason,
                match_mode=MATCH_MODE_FAILED,
                fields_rewritten=[],
            )
            for item in deterministic_blocks
        ]
        if not any(item.rewrite_metadata is not None for item in deterministic_blocks):
            for item in deterministic_blocks:
                self._log_block_validation(
                    block_id=item.block_id,
                    validation_passed=False,
                    rule=failure_reason,
                    match_mode=MATCH_MODE_FAILED,
                )
        resolved_blocks = [
            item.model_copy(
                update={
                    "resolved_lines": list(item.deterministic_lines),
                    "rewrite_metadata": metadata,
                }
            )
            for item, metadata in zip(deterministic_blocks, block_rewrite_metadata)
        ]
        return NarrativeAugmentationOutcome(
            narrative_layer=None,
            metadata=NarrativeValidationMetadata(
                source="deterministic_fallback",
                match_mode=MATCH_MODE_FAILED,
                fields_rewritten=[],
                model=model,
                prompt_version=PROMPT_VERSION,
                validation_passed=False,
                failure_reason=failure_reason,
                axis=self._narrative_axis(result),
                llm_invoked=llm_invoked,
                llm_call_count=llm_call_count,
                fallback_used=True,
                slim_payload_hash=slim_payload_hash,
                block_match_modes={item.block_id: MATCH_MODE_FAILED for item in deterministic_blocks},
                block_results=[
                    NarrativeValidationResult(
                        block_id=item.block_id,
                        validation_passed=False,
                        failure_reason=failure_reason,
                        match_mode=MATCH_MODE_FAILED,
                    )
                    for item in deterministic_blocks
                ],
                block_rewrite_metadata=block_rewrite_metadata,
            ),
            validated_explanation_blocks=resolved_blocks,
        )

    def _narrative_axis(self, result: StructuredRebuildResult) -> str:
        return str(result.narrative_axis or result.template_judgment or result.primary_judgment or "").strip()

    def _fields_rewritten(self, layer: RebuildNarrativeLayer) -> list[str]:
        rewritten: list[str] = []
        for field in ALLOWED_REWRITE_FIELDS:
            value = getattr(layer, field)
            if isinstance(value, list):
                if value:
                    rewritten.append(field)
            elif str(value or "").strip():
                rewritten.append(field)
        return rewritten

    def _has_meaningful_content(self, layer: RebuildNarrativeLayer) -> bool:
        return any(
            [
                bool(layer.report_purpose.strip()),
                bool(layer.executive_summary_v2),
                bool(layer.one_line_conclusion.strip()),
                bool(layer.primary_judgment_reason.strip()),
                bool(layer.recommended_option.strip()),
                bool(layer.execution_plan),
                bool(layer.risks),
                bool(layer.decision_narrative),
                bool(layer.consulting_deck_outline),
            ]
        )

    def _validate_outline_keys(self, chapters: list[ConsultingDeckOutlineChapter]) -> bool:
        seen: set[str] = set()
        for chapter in chapters:
            if chapter.chapter_key not in ALLOWED_OUTLINE_CHAPTER_KEYS:
                return False
            if chapter.chapter_key in seen:
                return False
            seen.add(chapter.chapter_key)
            if not chapter.headline.strip():
                return False
        return True

    def _validate_evidence_refs(
        self,
        layer: RebuildNarrativeLayer,
        canonical_payload: CanonicalRebuildPayload,
    ) -> bool:
        allowed = {
            str(item.get("evidence_id") or "").strip()
            for item in self._evidence_index(canonical_payload)
            if str(item.get("evidence_id") or "").strip()
        }
        if not allowed:
            return all(
                not statement.evidence_refs
                for statement in layer.decision_narrative
            ) and all(not chapter.evidence_refs for chapter in layer.consulting_deck_outline)
        for statement in layer.decision_narrative:
            if not set(statement.evidence_refs).issubset(allowed):
                return False
        for chapter in layer.consulting_deck_outline:
            if not set(chapter.evidence_refs).issubset(allowed):
                return False
        return True

    def _validate_recommended_option_invariance(
        self,
        layer: RebuildNarrativeLayer,
        canonical_payload: CanonicalRebuildPayload,
    ) -> bool:
        recommended_name = (
            canonical_payload.recommended_option.name.strip()
            if canonical_payload.recommended_option is not None
            else ""
        )
        other_option_names = {
            item.name.strip()
            for item in canonical_payload.design_options
            if item.name.strip() and item.name.strip() != recommended_name
        }
        if not other_option_names:
            return True
        texts = self._layer_texts(layer)
        for text in texts:
            for option_name in other_option_names:
                if option_name and option_name in text:
                    return False
        return True

    def _validate_classification_invariance(
        self,
        layer: RebuildNarrativeLayer,
        canonical_payload: CanonicalRebuildPayload,
    ) -> bool:
        allowed = {
            canonical_payload.function_classification.primary_judgment,
            canonical_payload.function_classification.template_judgment,
            canonical_payload.function_classification.structural_judgment,
            canonical_payload.function_classification.narrative_axis,
            canonical_payload.function_classification.feature_signal_mode,
        }
        allowed = {item for item in allowed if item}
        if not allowed:
            return True
        joined = " ".join(self._layer_texts(layer)).lower()
        mentioned = {token for token in CLASSIFICATION_TOKENS if token in joined}
        return not any(token not in allowed for token in mentioned)

    def _validate_diagnosis_invariance(
        self,
        layer: RebuildNarrativeLayer,
        canonical_payload: CanonicalRebuildPayload,
    ) -> bool:
        allowed_detector_ids = {
            str(item.get("detector_id") or "").strip()
            for item in (canonical_payload.diagnosis_report.get("issues") or [])
            if isinstance(item, dict) and str(item.get("detector_id") or "").strip()
        }
        if not allowed_detector_ids:
            return True
        joined = " ".join(self._layer_texts(layer))
        detector_mentions = set(re.findall(r"\b[a-z_]{3,}\b", joined))
        for mention in detector_mentions:
            if mention.endswith(("_candidate", "_mismatch", "_leak", "_scatter")) and mention not in allowed_detector_ids:
                return False
        return True

    def _validate_priority_invariance(
        self,
        layer: RebuildNarrativeLayer,
        slim_payload: SlimNarrativePayload,
    ) -> bool:
        allowed_text = json.dumps(slim_payload.model_dump(), ensure_ascii=False, sort_keys=True)
        for text in self._layer_texts(layer):
            for pattern in PRIORITY_MUTATION_PATTERNS:
                matches = re.findall(pattern, text, flags=re.IGNORECASE)
                if not matches:
                    continue
                if any(match not in allowed_text for match in matches):
                    return False
        return True

    def _validate_no_new_facts(
        self,
        layer: RebuildNarrativeLayer,
        slim_payload: SlimNarrativePayload,
    ) -> bool:
        allowed_text = json.dumps(slim_payload.model_dump(), ensure_ascii=False, sort_keys=True)
        allowed_numbers = set(re.findall(r"(?<!\d)\d[\d,]*(?!\d)", allowed_text))
        allowed_upper_tokens = set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", allowed_text))
        allowed_words = self._normalized_salient_words(allowed_text)
        for text in self._layer_texts(layer):
            numbers = set(re.findall(r"(?<!\d)\d[\d,]*(?!\d)", text))
            if not numbers.issubset(allowed_numbers):
                return False
            upper_tokens = set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", text))
            if not upper_tokens.issubset(allowed_upper_tokens):
                return False
        for text in self._layer_texts(layer):
            salient = self._normalized_salient_words(text)
            novel = {item for item in salient if item not in allowed_words}
            if salient and len(novel) >= 5 and len(novel) / max(len(salient), 1) > 0.5:
                return False
        return True

    def _validate_forbidden_expressions(self, layer: RebuildNarrativeLayer) -> bool:
        for text in self._layer_texts(layer):
            if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in FORBIDDEN_EXPRESSIONS):
                return False
            if self._contains_detector_name(text):
                return False
        return True

    def _layer_texts(self, layer: RebuildNarrativeLayer) -> list[str]:
        texts = [
            layer.report_purpose,
            layer.one_line_conclusion,
            layer.primary_judgment_reason,
            layer.recommended_option,
            *list(layer.executive_summary_v2),
            *list(layer.execution_plan),
            *list(layer.risks),
        ]
        texts.extend(item.text for item in layer.decision_narrative)
        texts.extend(item.headline for item in layer.consulting_deck_outline)
        return [str(text).strip() for text in texts if str(text).strip()]

    def _salient_words(self, text: str) -> set[str]:
        tokens = set()
        for token in re.findall(r"[A-Za-z가-힣][A-Za-z가-힣0-9_/-]{1,}", str(text or "").lower()):
            token = self._normalize_salient_token(token)
            if not token:
                continue
            if token in STOP_WORDS:
                continue
            if len(token) <= 1:
                continue
            tokens.add(token)
        return tokens

    def _normalize_salient_token(self, token: str) -> str:
        normalized = str(token or "").strip().lower()
        normalized = re.sub(
            r"(입니다|합니다|했습니다|하였다|했다|하는|하며|하고|하기|하기를|합니다만|합니다\.|설명합니다|설명하기)$",
            "",
            normalized,
        )
        normalized = re.sub(
            r"(으로부터|으로서|으로|에서|에게|까지|부터|처럼|마다|보다|와|과|를|을|은|는|이|가|의|도|만|로|에)$",
            "",
            normalized,
        )
        return normalized.strip("_-/ ")

    def _normalize_match_text(self, text: str) -> str:
        normalized = str(text or "").lower()
        for pattern, replacement in NORMALIZATION_PATTERNS:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _normalized_salient_words(self, text: str) -> set[str]:
        return self._salient_words(self._normalize_match_text(text))

    def _exact_match(self, expected_text: str, candidate_text: str, *, min_overlap: int) -> bool:
        expected = " ".join(str(expected_text or "").split()).strip().lower()
        candidate = " ".join(str(candidate_text or "").split()).strip().lower()
        if expected and candidate and expected in candidate:
            return True
        expected_words = self._salient_words(expected_text)
        candidate_words = self._salient_words(candidate_text)
        if not expected_words:
            return False
        if not expected_words.issubset(candidate_words):
            return False
        return len(expected_words.intersection(candidate_words)) >= min_overlap

    def _normalized_synonym_match(self, expected_text: str, candidate_text: str, *, min_overlap: int) -> bool:
        expected = self._normalize_match_text(expected_text)
        candidate = self._normalize_match_text(candidate_text)
        if expected and candidate and expected in candidate:
            return True
        expected_words = self._normalized_salient_words(expected_text)
        candidate_words = self._normalized_salient_words(candidate_text)
        if not expected_words:
            return False
        return len(expected_words.intersection(candidate_words)) >= min_overlap

    def _semantic_match(self, expected_text: str, candidate_text: str) -> bool:
        return False

    def _match_mode_with_relaxation(
        self,
        expected_text: str,
        candidate_text: str,
        *,
        exact_min_overlap: int = 1,
        normalized_min_overlap: int = 1,
        semantic_enabled: bool = False,
    ) -> str:
        if self._exact_match(expected_text, candidate_text, min_overlap=exact_min_overlap):
            return MATCH_MODE_EXACT
        if self._normalized_synonym_match(expected_text, candidate_text, min_overlap=normalized_min_overlap):
            return MATCH_MODE_NORMALIZED
        if semantic_enabled and self._semantic_match(expected_text, candidate_text):
            return MATCH_MODE_SEMANTIC
        return MATCH_MODE_FAILED

    def _matches_with_relaxation(
        self,
        expected_text: str,
        candidate_text: str,
        *,
        exact_min_overlap: int = 1,
        normalized_min_overlap: int = 1,
        semantic_enabled: bool = False,
    ) -> bool:
        return self._match_mode_with_relaxation(
            expected_text,
            candidate_text,
            exact_min_overlap=exact_min_overlap,
            normalized_min_overlap=normalized_min_overlap,
            semantic_enabled=semantic_enabled,
        ) != MATCH_MODE_FAILED

    def _looser_match_mode(self, *modes: str) -> str:
        ordered = {
            MATCH_MODE_EXACT: 0,
            MATCH_MODE_NORMALIZED: 1,
            MATCH_MODE_SEMANTIC: 2,
            MATCH_MODE_FAILED: 3,
            MATCH_MODE_MIXED: 4,
        }
        resolved = [mode for mode in modes if str(mode or "").strip() and mode != MATCH_MODE_FAILED]
        if not resolved:
            return MATCH_MODE_FAILED
        return max(resolved, key=lambda item: ordered.get(item, 99))

    def _aggregate_success_match_mode(self, match_modes: list[str]) -> str:
        return self._looser_match_mode(*match_modes) if match_modes else MATCH_MODE_EXACT

    def _aggregate_match_mode(self, block_results: list[NarrativeValidationResult]) -> str:
        modes = [item.match_mode for item in block_results if str(item.match_mode or "").strip()]
        if not modes:
            return MATCH_MODE_FAILED
        unique = {mode for mode in modes}
        if unique == {MATCH_MODE_FAILED}:
            return MATCH_MODE_FAILED
        successful = {mode for mode in unique if mode != MATCH_MODE_FAILED}
        if len(unique) == 1:
            return next(iter(unique))
        if len(successful) == 1 and MATCH_MODE_FAILED not in unique:
            return next(iter(successful))
        return MATCH_MODE_MIXED

    def _block_match_modes(self, block_results: list[NarrativeValidationResult]) -> dict[str, str]:
        return {
            str(item.block_id or ""): str(item.match_mode or MATCH_MODE_FAILED)
            for item in block_results
            if str(item.block_id or "").strip()
        }

    def _operational_source_context(
        self,
        *,
        canonical_payload: CanonicalRebuildPayload,
        result: StructuredRebuildResult,
    ) -> dict[str, Any]:
        governance = result.extensions.get("decision_governance") if isinstance(result.extensions, dict) else {}
        outline = governance.get("document_outline") if isinstance(governance, dict) else {}
        analysis_lines = self._normalize_candidate_lines(
            list(result.analysis_summary) or list(canonical_payload.analysis_summary)
        )
        combined_texts = [
            result.report_purpose,
            result.primary_judgment_reason,
            result.one_line_conclusion,
            *list(result.analysis_summary),
            *list(result.executive_summary_v2),
            *list(result.risks),
            *list(canonical_payload.analysis_summary),
        ]
        narrative_axis = str(result.narrative_axis or "").strip()
        active = bool(
            narrative_axis in {"fx_fifo", "interface_linkage", "settlement_journal"}
            or (isinstance(outline, dict) and outline.get("recommended_strategy") == "현행 분석 우선")
            or (analysis_lines and analysis_lines[0].startswith("핵심 객체는"))
        )
        object_names = self._extract_operational_object_names(combined_texts)
        flow_anchor = " ".join(self._extract_operational_flow_terms(combined_texts, narrative_axis))
        risk_anchor = " ".join(self._extract_operational_risk_terms(combined_texts, narrative_axis))
        identity_anchor = self._operational_identity_anchor(narrative_axis)
        return {
            "active": active,
            "identity_anchor": identity_anchor,
            "object_anchor": " ".join(object_names[:6]),
            "flow_anchor": flow_anchor,
            "risk_anchor": risk_anchor,
            "restore_anchor": "현행 처리 흐름 복원",
        }

    def _extract_operational_object_names(self, texts: list[str]) -> list[str]:
        combined = "\n".join(str(text or "") for text in texts if str(text or "").strip())
        ignore = {
            "CREATE",
            "TABLE",
            "PROCEDURE",
            "TRIGGER",
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "FROM",
            "INTO",
            "WHERE",
            "ORDER",
            "GROUP",
        }
        seen: list[str] = []
        for token in re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", combined):
            if token in ignore or token in seen:
                continue
            seen.append(token)
        return seen

    def _extract_operational_flow_terms(self, texts: list[str], narrative_axis: str = "") -> list[str]:
        combined = "\n".join(str(text or "") for text in texts if str(text or "").strip()).lower()
        ordered_terms: list[tuple[str, tuple[str, ...]]] = []
        if narrative_axis in {"", "fx_fifo"}:
            ordered_terms.extend(
                [
                    ("외화 입금", ("외화 입금", "입금", "deposit", "forins")),
                    ("외화 출금", ("외화 출금", "출금", "withdraw", "forout")),
                    ("FIFO lot", ("fifo", "lot", "선입선출")),
                    ("환차손익", ("환차", "gain_loss", "gap_amt", "exchange p/l")),
                    ("전표", ("전표", "voucher", "journal", "bkchit")),
                    ("GL interface", ("gl_interface", "gl interface", "ledger", "reference4", "reference6")),
                ]
            )
        if narrative_axis in {"", "interface_linkage"}:
            ordered_terms.extend(
                [
                    ("staging", ("staging", "ib_bulk_tran_add", "bulk_tran", "file_date", "file_num", "file_seq")),
                    ("상태 확정", ("tran_status", "confirm", "cnf_yn", "status")),
                    ("ACK", ("ack", "erp_rcv_flag", "result_cd")),
                    ("retry", ("retry", "react_cd", "reprocess", "fail")),
                    ("latest snapshot", ("ib_acctall_tr_dd_lst", "snapshot", "latest", "lst")),
                    ("PAY_ORDER", ("tn_pay_order_dtl", "pay_order", "pay_date", "pay_chitno")),
                ]
            )
        if narrative_axis in {"", "settlement_journal"}:
            ordered_terms.extend(
                [
                    ("정산 확정", ("settle", "settlement", "stl_", "cnf_yn")),
                    ("전표 헤더", ("tn_bkchno", "ac_chitno", "ac_date")),
                    ("전표 라인", ("tn_bkchit", "dc_flag", "journal", "voucher")),
                    ("GL interface", ("gl_interface", "gl interface", "user_je", "entered_dr", "entered_cr")),
                    ("취소 역처리", ("cancel", "reverse", "reverse_yn", "can_yn")),
                    ("PAY_ORDER", ("tn_pay_order_dtl", "pay_order", "pay_date", "pay_no")),
                ]
            )
        seen: list[str] = []
        for label, keywords in ordered_terms:
            if label in seen:
                continue
            if any(keyword in combined for keyword in keywords):
                seen.append(label)
        return seen

    def _extract_operational_risk_terms(self, texts: list[str], narrative_axis: str = "") -> list[str]:
        combined = "\n".join(str(text or "") for text in texts if str(text or "").strip()).lower()
        ordered_terms: list[tuple[str, tuple[str, ...]]] = []
        if narrative_axis in {"", "fx_fifo"}:
            ordered_terms.extend(
                [
                    ("FIFO 소진 순서", ("fifo", "lot", "소진 순서")),
                    ("환차손익 기준", ("환차", "gain_loss", "gap_amt")),
                    ("전표-GL 연계", ("전표", "gl", "interface")),
                    ("취소 역분개", ("취소", "cancel", "reverse", "역분개", "delete")),
                    ("정합성", ("정합성", "reconciliation", "integrity")),
                ]
            )
        if narrative_axis in {"", "interface_linkage"}:
            ordered_terms.extend(
                [
                    ("중복 적재", ("duplicate", "dup", "file_seq", "file_num")),
                    ("ACK/status 불일치", ("ack", "tran_status", "erp_rcv_flag", "result_cd")),
                    ("retry 누락", ("retry", "react_cd", "fail", "reprocess")),
                    ("latest snapshot 누락", ("snapshot", "lst", "latest")),
                    ("PAY_ORDER 연계 누락", ("pay_order", "pay_chitno", "pay_hang")),
                ]
            )
        if narrative_axis in {"", "settlement_journal"}:
            ordered_terms.extend(
                [
                    ("정산-전표 불일치", ("settle", "settlement", "tn_bkchno", "tn_bkchit")),
                    ("차변/대변 불균형", ("dc_flag", "entered_dr", "entered_cr", "credit", "debit")),
                    ("GL 적재 누락", ("gl_interface", "reference4", "reference6")),
                    ("취소 역분개", ("cancel", "reverse", "delete", "역분개")),
                    ("PAY_ORDER 상태 미동기화", ("pay_order", "settle_yn", "pay_stat")),
                ]
            )
        seen: list[str] = []
        for label, keywords in ordered_terms:
            if label in seen:
                continue
            if any(keyword in combined for keyword in keywords):
                seen.append(label)
        return seen

    def _operational_identity_anchor(self, narrative_axis: str) -> str:
        return {
            "fx_fifo": "회계 처리 소스 묶음",
            "interface_linkage": "인터페이스 운영 소스 묶음",
            "settlement_journal": "회계 운영 소스 묶음",
        }.get(narrative_axis, "운영 소스 묶음")

    def _requires_operational_source_governance(self, slim_payload: SlimNarrativePayload) -> bool:
        return any(
            str(block.locked_fields.family or "").strip() == "operational_source"
            or any(str(fact.fact_id or "").startswith("operational:") for fact in block.critical_facts)
            for block in slim_payload.explanation_blocks
        )

    def _requires_option_comparison_guidance(self, slim_payload: SlimNarrativePayload) -> bool:
        return any(self._has_option_comparison_marker(block) for block in slim_payload.explanation_blocks)

    def _has_operational_source_marker(self, block: DeterministicExplanationBlock) -> bool:
        return str(block.locked_fields.family or "").strip() == "operational_source" or any(
            str(item.fact_id or "").startswith("operational:") for item in block.critical_facts
        )

    def _has_option_comparison_marker(self, block: DeterministicExplanationBlock) -> bool:
        if str(block.locked_fields.family or "").strip() == "option_comparison":
            return True
        joined = " ".join(str(item.text or "").strip() for item in block.critical_facts)
        return any(token in joined for token in ("비교 관점:", "우선 검토안은", "복수 선택지"))

    def _operational_source_governance_failure(
        self,
        block: DeterministicExplanationBlock,
        candidate_lines: list[str],
    ) -> str:
        if not self._has_operational_source_marker(block):
            return ""
        joined = " ".join(candidate_lines)
        level = self.template_support.operational_section_level(block.block_id)
        if self._contains_detector_name(joined):
            return FAILURE_DETECTOR_NAME_EXPOSURE
        leading_lines = candidate_lines[:2] if block.block_id == "executive_summary_v2" else candidate_lines[:1]
        leading_text = " ".join(leading_lines).lower()
        if any(pattern in leading_text for pattern in OPERATIONAL_REDESIGN_PATTERNS) and not self._has_negated_redesign_context(leading_text):
            return FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION
        if block.block_id == "execution_plan":
            if any(token in joined.lower() for token in ("로드맵", "roadmap")):
                return FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION
            if re.search(r"\b\d+\s*주차\b", joined):
                return FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION
        if level == "l1" and block.block_id in {
            "report_purpose",
            "one_line_conclusion",
            "executive_summary_v2",
            "primary_judgment_reason",
            "recommended_option",
            "execution_plan",
            "risks",
            "rationale",
            "next_step",
            "risk",
        } and self._operational_candidate_exposes_object_name(block, candidate_lines):
            return FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION
        if level == "l2":
            if not candidate_lines:
                return FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION
            if not str(candidate_lines[0] or "").strip().startswith("핵심 객체는"):
                return FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION
            object_lines = [str(item or "").strip() for item in candidate_lines[1:] if str(item or "").strip()]
            if not object_lines or len(object_lines) > 5:
                return FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION
            if any(
                self.template_support.operational_text_exposes_technical_token(line)
                or not re.match(r"^[^:]+: .+$", line)
                for line in object_lines
            ):
                return FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION
        if block.block_id == "one_line_conclusion":
            first_line = str(candidate_lines[0] if candidate_lines else "").strip()
            if first_line and not first_line.startswith("본 자산은"):
                return FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION
        if block.block_id == "executive_summary_v2":
            first_line = str(candidate_lines[0] if candidate_lines else "").strip()
            if first_line and not first_line.startswith("현행 분석:"):
                return FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION
        if block.block_id in {"one_line_conclusion", "executive_summary_v2"} and not self._operational_candidate_mentions_anchor(block, candidate_lines):
            return FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION
        return ""

    def _option_comparison_governance_failure(
        self,
        block: DeterministicExplanationBlock,
        candidate_lines: list[str],
    ) -> str:
        if not self._has_option_comparison_marker(block):
            return ""
        first_line = str(candidate_lines[0] if candidate_lines else "").strip()
        if not first_line:
            return ""
        lowered = first_line.lower()
        if any(token in lowered for token in ("현행 분석:", "본 자산은", "운영 판단", "운영 소스")):
            return FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION
        if block.block_id == "report_purpose" and not any(token in first_line for token in ("비교", "선택지", "추천안")):
            return FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION
        if block.block_id == "one_line_conclusion" and not any(first_line.startswith(prefix) for prefix in ("우선 검토안은", "추천안은")):
            return FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION
        if block.block_id == "executive_summary_v2" and not first_line.startswith("비교 관점:"):
            return FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION
        if block.block_id == "execution_plan" and any(token in lowered for token in ("현행 분석", "운영 리스크", "본 자산은")):
            return FAILURE_OPERATIONAL_GOVERNANCE_VIOLATION
        return ""

    def _operational_candidate_mentions_anchor(
        self,
        block: DeterministicExplanationBlock,
        candidate_lines: list[str],
    ) -> bool:
        joined = " ".join(candidate_lines)
        lowered = joined.lower()
        object_anchor = " ".join(
            item.text for item in block.critical_facts if str(item.fact_id or "").startswith("operational:") and str(item.fact_id or "").endswith(":objects")
        )
        flow_anchor = " ".join(
            item.text for item in block.critical_facts if str(item.fact_id or "").startswith("operational:") and str(item.fact_id or "").endswith(":flow")
        )
        object_tokens = self._extract_operational_object_names([object_anchor]) if object_anchor else []
        if object_tokens and any(token in joined for token in object_tokens):
            return True
        flow_tokens = self._extract_operational_flow_terms([flow_anchor]) if flow_anchor else []
        if flow_tokens and any(token.lower() in lowered for token in flow_tokens):
            return True
        return not object_tokens and not flow_tokens

    def _operational_candidate_exposes_object_name(
        self,
        block: DeterministicExplanationBlock,
        candidate_lines: list[str],
    ) -> bool:
        object_anchor = " ".join(
            item.text for item in block.critical_facts if str(item.fact_id or "").startswith("operational:") and str(item.fact_id or "").endswith(":objects")
        )
        object_tokens = self._extract_operational_object_names([object_anchor]) if object_anchor else []
        return self.template_support.operational_lines_expose_technical_tokens(
            candidate_lines,
            extra_tokens=object_tokens,
        )

    def _contains_detector_name(self, text: str) -> bool:
        return any(re.search(pattern, str(text or ""), flags=re.IGNORECASE) for pattern in DETECTOR_NAME_PATTERNS)

    def _has_negated_redesign_context(self, text: str) -> bool:
        lowered = str(text or "").lower()
        patterns = (
            r"재설계[^.\n]{0,24}(?:보다|아니|하지\s*마|말라|제외|배제|후속|보조)",
            r"(?:현행|운영|분석|복원)[^.\n]{0,24}우선[^.\n]{0,24}재설계",
            r"(?:not|without|exclude|excluding|instead of)[^.\n]{0,24}redesign",
            r"redesign[^.\n]{0,24}(?:later|defer|exclude|instead of)",
        )
        return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in patterns)

    def _pass_rule_for_match_mode(self, match_mode: str) -> str:
        return {
            MATCH_MODE_EXACT: "exact_match",
            MATCH_MODE_NORMALIZED: "normalized_synonym_match",
            MATCH_MODE_SEMANTIC: "semantic_match",
        }.get(match_mode, "validated_block")

    def _log_block_validation(
        self,
        *,
        block_id: str,
        validation_passed: bool,
        rule: str,
        match_mode: str,
    ) -> None:
        logger.info(
            "[NarrativeGuard] block=%s result=%s rule=%s match_mode=%s",
            block_id,
            "pass" if validation_passed else "fail",
            rule or "validated_block",
            match_mode or MATCH_MODE_FAILED,
        )

    def _normalize_alias(self, value: str) -> str:
        return re.sub(r"[\s_-]+", "", str(value or "").lower()).strip()

    def _contains_alias(self, candidate_text: str, alias: str) -> bool:
        normalized_candidate = self._normalize_alias(candidate_text)
        normalized_alias = self._normalize_alias(alias)
        return bool(normalized_alias) and normalized_alias in normalized_candidate

    def _recommended_option_aliases(self, recommended_name: str) -> list[str]:
        base = str(recommended_name or "").strip()
        if not base:
            return []
        aliases: list[str] = [base]
        for suffix in OPTION_ALIAS_SUFFIXES:
            if base.endswith(suffix):
                trimmed = base[: -len(suffix)].strip()
                if trimmed:
                    aliases.append(trimmed)
        deduped: list[str] = []
        seen: set[str] = set()
        for item in aliases:
            normalized = self._normalize_alias(item)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(item)
        return deduped

    def _evidence_index(self, canonical_payload: CanonicalRebuildPayload) -> list[dict[str, Any]]:
        evidence_index = canonical_payload.appendix.get("evidence_index")
        return evidence_index if isinstance(evidence_index, list) else []

    def _rule_evidence_refs(
        self,
        rule,
        canonical_payload: CanonicalRebuildPayload,
    ) -> list[str]:
        allowed = self._evidence_index(canonical_payload)
        evidence_refs: list[str] = []
        for evidence in getattr(rule, "evidence", [])[:3]:
            match_id = self._match_evidence_ref(
                asset_name=evidence.asset_name,
                locator=evidence.locator,
                excerpt=evidence.excerpt,
                evidence_index=allowed,
            )
            if match_id and match_id not in evidence_refs:
                evidence_refs.append(match_id)
        return evidence_refs

    def _decision_evidence_refs(
        self,
        decision_item,
        canonical_payload: CanonicalRebuildPayload,
    ) -> list[str]:
        allowed = self._evidence_index(canonical_payload)
        evidence_refs: list[str] = []
        for evidence in getattr(decision_item, "linked_evidence", [])[:3]:
            match_id = self._match_evidence_ref(
                asset_name=evidence.asset_name,
                locator=evidence.locator,
                excerpt=evidence.excerpt,
                evidence_index=allowed,
            )
            if match_id and match_id not in evidence_refs:
                evidence_refs.append(match_id)
        return evidence_refs

    def _match_evidence_ref(
        self,
        *,
        asset_name: str,
        locator: str,
        excerpt: str,
        evidence_index: list[dict[str, Any]],
    ) -> str:
        normalized_asset = asset_name.strip().lower()
        normalized_locator = locator.strip().lower()
        normalized_excerpt = excerpt.strip()
        for item in evidence_index:
            evidence_id = str(item.get("evidence_id") or "").strip()
            if not evidence_id:
                continue
            if normalized_asset and normalized_asset != str(item.get("asset_name") or "").strip().lower():
                continue
            if normalized_locator and normalized_locator != str(item.get("locator") or "").strip().lower():
                continue
            item_excerpt = str(item.get("excerpt") or "").strip()
            if normalized_excerpt and normalized_excerpt[:60] and normalized_excerpt[:60] not in item_excerpt:
                continue
            return evidence_id
        return ""

    def _compact_excerpt(self, excerpt: str) -> str:
        compact = re.sub(r"\s+", " ", str(excerpt or "").strip())
        compact = re.sub(r"\b[A-Z_]{6,}\b", "[TOKEN]", compact)
        return compact[:220]

    def _model_name(self, raw_response: Any, llm_service: Any | None) -> str:
        model = str(getattr(raw_response, "model", "") or "").strip()
        if model:
            return model
        getter = getattr(llm_service, "get_model_for_mode", None)
        if callable(getter):
            try:
                return str(getter("thinking") or "").strip()
            except Exception:
                return ""
        return ""
