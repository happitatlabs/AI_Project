from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from mellow_link.modules.rebuild_assistant.schemas import StructuredRebuildResult

logger = logging.getLogger(__name__)

PROMPT_VERSION = "phase1.8-top-narrative-v1"
ALLOWED_FIELDS = (
    "report_purpose",
    "primary_judgment_reason",
    "one_line_conclusion",
    "executive_summary_v2",
)


class NarrativeAugmentationRequest(BaseModel):
    goal: str = ""
    constraints: list[str] = Field(default_factory=list)
    primary_judgment: str = ""
    narrative_axis: str = ""
    top_decision: dict[str, Any] = Field(default_factory=dict)
    top_issue_summaries: list[str] = Field(default_factory=list)
    recommended_option: dict[str, Any] = Field(default_factory=dict)
    top_evidence_excerpts: list[str] = Field(default_factory=list)
    deterministic_fields: dict[str, Any] = Field(default_factory=dict)


class NarrativeAugmentationResult(BaseModel):
    updated_fields: dict[str, Any] = Field(default_factory=dict)
    source: str = "deterministic_fallback"
    fields_rewritten: list[str] = Field(default_factory=list)
    model: str = ""
    prompt_version: str = PROMPT_VERSION
    validation_passed: bool = False
    failure_reason: str = ""


class NarrativeAugmentationService:
    def augment_sync(
        self,
        *,
        prepared,
        result: StructuredRebuildResult,
        llm_service: Any | None,
    ) -> StructuredRebuildResult:
        augmentation = asyncio.run(self.augment(prepared=prepared, result=result, llm_service=llm_service))
        return self.apply(result, augmentation)

    async def augment(
        self,
        *,
        prepared,
        result: StructuredRebuildResult,
        llm_service: Any | None,
    ) -> NarrativeAugmentationResult:
        request = self._build_request(prepared=prepared, result=result)
        if llm_service is None or not hasattr(llm_service, "generate"):
            return self._fallback_result("llm_service_unavailable")

        try:
            raw_response = await llm_service.generate(
                prompt=self._build_prompt(request),
                system_prompt=self._system_prompt(),
                mode="thinking",
                temperature=0.1,
                max_tokens=700,
                auto_unload=True,
            )
        except Exception as exc:
            logger.warning("[NarrativeAugmentation] LLM generate failed: %s", exc)
            return self._fallback_result(f"llm_generate_failed:{type(exc).__name__}")

        parsed = self._parse_response(raw_response)
        if parsed is None:
            return self._fallback_result("invalid_json_response")
        valid, failure_reason = self._validate(parsed, request)
        if not valid:
            return self._fallback_result(failure_reason)

        fields_rewritten = [field for field in ALLOWED_FIELDS if field in parsed]
        return NarrativeAugmentationResult(
            updated_fields=parsed,
            source="ai",
            fields_rewritten=fields_rewritten,
            model=getattr(raw_response, "model", "") or getattr(llm_service, "get_model_for_mode", lambda mode: "")("thinking"),
            prompt_version=PROMPT_VERSION,
            validation_passed=True,
            failure_reason="",
        )

    def apply(
        self,
        result: StructuredRebuildResult,
        augmentation: NarrativeAugmentationResult,
    ) -> StructuredRebuildResult:
        extensions = dict(result.extensions if isinstance(result.extensions, dict) else {})
        extensions["narrative"] = {
            "source": augmentation.source,
            "fields_rewritten": list(augmentation.fields_rewritten),
            "model": augmentation.model,
            "prompt_version": augmentation.prompt_version,
            "validation_passed": augmentation.validation_passed,
            "failure_reason": augmentation.failure_reason,
        }
        if augmentation.source != "ai" or not augmentation.updated_fields:
            return result.model_copy(update={"extensions": extensions})
        return result.model_copy(update={**augmentation.updated_fields, "extensions": extensions})

    def _build_request(self, *, prepared, result: StructuredRebuildResult) -> NarrativeAugmentationRequest:
        decisions = result.decision_summary.get("decisions", []) if isinstance(result.decision_summary, dict) else []
        issues = result.diagnosis_report.get("issues", []) if isinstance(result.diagnosis_report, dict) else []
        evidence_index = result.appendix.get("evidence_index", []) if isinstance(result.appendix, dict) else []
        top_decision = decisions[0] if decisions else {}
        top_issue_summaries = [str(item.get("summary") or "") for item in issues[:3] if str(item.get("summary") or "").strip()]
        top_evidence_excerpts = [str(item.get("excerpt") or "") for item in evidence_index[:3] if str(item.get("excerpt") or "").strip()]
        narrative_extension = result.extensions.get("narrative") if isinstance(result.extensions, dict) else {}
        deterministic_fields = {
            "report_purpose": result.report_purpose,
            "primary_judgment_reason": result.primary_judgment_reason,
            "one_line_conclusion": result.one_line_conclusion,
            "executive_summary_v2": list(result.executive_summary_v2),
            "score_breakdown": dict(top_decision.get("score_breakdown") or {}),
            "explainability": dict(top_decision.get("explainability") or {}),
        }
        return NarrativeAugmentationRequest(
            goal=str(getattr(prepared, "goal", "") or ""),
            constraints=list(getattr(prepared, "constraints", []) or []),
            primary_judgment=result.primary_judgment,
            narrative_axis=str(narrative_extension.get("axis") or result.primary_judgment or ""),
            top_decision=top_decision,
            top_issue_summaries=top_issue_summaries,
            recommended_option=result.recommended_option.model_dump() if result.recommended_option is not None else {},
            top_evidence_excerpts=top_evidence_excerpts,
            deterministic_fields=deterministic_fields,
        )

    def _build_prompt(self, request: NarrativeAugmentationRequest) -> str:
        payload = request.model_dump()
        return (
            "아래 deterministic 결과를 읽고 상단 설명 4개 필드만 더 자연스럽게 다시 써라.\n"
            "절대 새 판단, 새 점수, 새 evidence, 새 고유명사, 새 숫자를 추가하지 마라.\n"
            "허용 필드: report_purpose, primary_judgment_reason, one_line_conclusion, executive_summary_v2\n"
            "executive_summary_v2는 2~4개의 문자열 리스트여야 한다.\n"
            "JSON object만 반환하라.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    def _system_prompt(self) -> str:
        return (
            "You are rewriting only the top explanatory narrative of a deterministic refactoring decision tool. "
            "Do not change facts, decisions, scores, or evidence. "
            "Do not add new numbers or named entities not present in the input. "
            "Return JSON only."
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
        if not isinstance(parsed, dict):
            return None
        unexpected_keys = [key for key in parsed.keys() if key not in ALLOWED_FIELDS]
        normalized: dict[str, Any] = {}
        if unexpected_keys:
            normalized["__unexpected_fields__"] = unexpected_keys
        for field in ALLOWED_FIELDS:
            if field not in parsed:
                continue
            value = parsed[field]
            if field == "executive_summary_v2":
                if isinstance(value, list):
                    normalized[field] = [str(item).strip() for item in value if str(item).strip()]
                else:
                    normalized[field] = [str(value).strip()] if str(value).strip() else []
            else:
                normalized[field] = str(value).strip()
        return normalized

    def _validate(
        self,
        parsed: dict[str, Any],
        request: NarrativeAugmentationRequest,
    ) -> tuple[bool, str]:
        if not parsed:
            return False, "empty_update"
        unexpected = set(parsed) - set(ALLOWED_FIELDS)
        if unexpected:
            return False, "unexpected_fields"
        for field, value in parsed.items():
            if field == "executive_summary_v2":
                if not isinstance(value, list) or not value or any(not str(item).strip() for item in value):
                    return False, "empty_executive_summary"
            elif not str(value).strip():
                return False, f"empty_{field}"

        allowed_text = json.dumps(request.model_dump(), ensure_ascii=False, sort_keys=True)
        allowed_numbers = set(re.findall(r"(?<!\d)\d[\d,]*(?!\d)", allowed_text))
        allowed_upper_tokens = set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", allowed_text))
        final_score = request.deterministic_fields.get("score_breakdown", {}).get("final_score")

        for field, value in parsed.items():
            texts = value if isinstance(value, list) else [value]
            for text in texts:
                numbers = set(re.findall(r"(?<!\d)\d[\d,]*(?!\d)", text))
                if not numbers.issubset(allowed_numbers):
                    return False, "new_numeric_fact"
                upper_tokens = set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", text))
                if not upper_tokens.issubset(allowed_upper_tokens):
                    return False, "new_named_token"
                if re.search(r"(final[_ ]?score|점수)", text, flags=re.IGNORECASE):
                    if final_score is None:
                        return False, "score_reference_without_baseline"
                    if str(final_score) not in text:
                        return False, "score_mismatch"
        return True, ""

    def _fallback_result(self, failure_reason: str) -> NarrativeAugmentationResult:
        return NarrativeAugmentationResult(
            updated_fields={},
            source="deterministic_fallback",
            fields_rewritten=[],
            model="",
            prompt_version=PROMPT_VERSION,
            validation_passed=False,
            failure_reason=failure_reason,
        )
