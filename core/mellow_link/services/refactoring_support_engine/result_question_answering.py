from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from mellow_link.modules.rebuild_assistant.schemas import ResultCitation, ResultQAResponse


PROMPT_VERSION = "phase3-result-qa-v1"
SUPPORTED_INTENTS = ("strategy", "priority", "evidence", "execution", "risk", "scope")


class QARewriteRequest(BaseModel):
    question: str
    audience: str = "manager"
    intent: str = "scope"
    deterministic_answer: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    referenced_sections: list[str] = Field(default_factory=list)
    grounding_pack: dict[str, Any] = Field(default_factory=dict)


class ResultQuestionAnsweringService:
    async def answer(
        self,
        *,
        project_id: str,
        result_package: dict[str, Any],
        question: str,
        audience: str = "manager",
        llm_service: Any | None = None,
    ) -> ResultQAResponse:
        normalized_audience = audience if audience in {"developer", "manager", "client"} else "manager"
        normalized_question = self._normalize_question(question)
        intent = self._classify_intent(normalized_question)
        grounding = self._retrieve_grounding(result_package=result_package, intent=intent)
        deterministic_answer = self._build_deterministic_answer(
            audience=normalized_audience,
            intent=intent,
            grounding=grounding,
        )
        citations = [ResultCitation.model_validate(item) for item in grounding.get("citations") or []]
        insufficient_grounding = bool(grounding.get("insufficient_grounding"))
        referenced_sections = list(grounding.get("referenced_sections") or [])

        if insufficient_grounding:
            return ResultQAResponse(
                answer=deterministic_answer,
                answer_mode="deterministic",
                citations=citations,
                referenced_sections=referenced_sections,
                insufficient_grounding=True,
                provenance={
                    "source": "deterministic",
                    "model": "",
                    "validation_passed": True,
                    "fallback_reason": "insufficient_grounding",
                    "intent": intent,
                    "project_id": project_id,
                },
            )

        rewrite_request = QARewriteRequest(
            question=normalized_question,
            audience=normalized_audience,
            intent=intent,
            deterministic_answer=deterministic_answer,
            citations=[item.model_dump() for item in citations],
            referenced_sections=referenced_sections,
            grounding_pack=grounding.get("grounding_pack") or {},
        )
        rewritten_answer, answer_mode, provenance = await self._maybe_ai_rewrite(
            rewrite_request=rewrite_request,
            llm_service=llm_service,
        )
        provenance["intent"] = intent
        provenance["project_id"] = project_id
        return ResultQAResponse(
            answer=rewritten_answer,
            answer_mode=answer_mode,
            citations=citations,
            referenced_sections=referenced_sections,
            insufficient_grounding=False,
            provenance=provenance,
        )

    def _normalize_question(self, question: str) -> str:
        normalized = re.sub(r"\s+", " ", (question or "").strip())
        return normalized

    def _classify_intent(self, question: str) -> str:
        lowered = question.lower()
        if any(token in lowered for token in ("리팩터링", "재설계", "refactor", "redesign", "전략", "strategy", "방향")):
            return "strategy"
        if any(token in lowered for token in ("우선", "priority", "점수", "score", "왜 먼저", "why first")):
            return "priority"
        if any(token in lowered for token in ("근거", "evidence", "증거", "출처", "어디서", "why this")):
            return "evidence"
        if any(token in lowered for token in ("실행", "단계", "plan", "stage", "어떻게 진행", "how to execute")):
            return "execution"
        if any(token in lowered for token in ("리스크", "위험", "risk", "주의", "problem")):
            return "risk"
        if any(token in lowered for token in ("범위", "scope", "슬라이스", "component", "분석 대상")):
            return "scope"
        if any(token in lowered for token in ("왜", "전략", "strategy", "refactor", "redesign", "방향")):
            return "strategy"
        return "scope"

    def _retrieve_grounding(self, *, result_package: dict[str, Any], intent: str) -> dict[str, Any]:
        authoritative = result_package.get("authoritative_payload") if isinstance(result_package, dict) else {}
        authoritative = authoritative if isinstance(authoritative, dict) else {}
        decision_summary = authoritative.get("decision_summary") or {}
        diagnosis_report = authoritative.get("diagnosis_report") or {}
        structure_snapshot = authoritative.get("structure_snapshot") or {}
        improvement_plan_bundle = authoritative.get("improvement_plan_bundle") or {}
        appendix = authoritative.get("appendix") or {}

        decisions = decision_summary.get("decisions") or []
        issues = diagnosis_report.get("issues") or []
        stages = improvement_plan_bundle.get("execution_stages") or []
        risk_checkpoints = improvement_plan_bundle.get("risk_checkpoints") or []
        evidence_index = appendix.get("evidence_index") or []

        top_decision = decisions[0] if isinstance(decisions, list) and decisions and isinstance(decisions[0], dict) else {}
        top_issue = issues[0] if isinstance(issues, list) and issues and isinstance(issues[0], dict) else {}
        top_stage = stages[0] if isinstance(stages, list) and stages and isinstance(stages[0], dict) else {}
        top_risk = risk_checkpoints[0] if isinstance(risk_checkpoints, list) and risk_checkpoints and isinstance(risk_checkpoints[0], dict) else {}
        evidence_map = {
            str(item.get("evidence_id") or ""): item
            for item in evidence_index
            if isinstance(item, dict) and str(item.get("evidence_id") or "").strip()
        }
        issue_map = {
            str(item.get("issue_id") or ""): item
            for item in issues
            if isinstance(item, dict) and str(item.get("issue_id") or "").strip()
        }

        if intent == "strategy":
            citations = self._decision_citations(top_decision, issue_map=issue_map, evidence_map=evidence_map)
            recommended_strategy = str(decision_summary.get("recommended_strategy") or "-")
            display_strategy = self._display_strategy(result_package=result_package, fallback=recommended_strategy)
            analysis_first_surface = self._uses_analysis_first_surface(result_package)
            insufficient = not bool(top_decision) or not bool(citations)
            return {
                "intent": intent,
                "recommended_strategy": recommended_strategy,
                "display_strategy": display_strategy,
                "analysis_first_surface": analysis_first_surface,
                "top_decision": top_decision,
                "top_issue": top_issue,
                "citations": citations,
                "referenced_sections": ["decision_summary", "diagnosis_report"],
                "insufficient_grounding": insufficient,
                "grounding_pack": {
                    "recommended_strategy": recommended_strategy,
                    "display_strategy": display_strategy,
                    "analysis_first_surface": analysis_first_surface,
                    "top_decision": top_decision,
                    "top_issue": top_issue,
                },
            }
        if intent == "priority":
            citations = self._decision_citations(top_decision, issue_map=issue_map, evidence_map=evidence_map)
            return {
                "intent": intent,
                "top_decision": top_decision,
                "citations": citations,
                "referenced_sections": ["decision_summary"],
                "insufficient_grounding": not bool(top_decision),
                "grounding_pack": {"top_decision": top_decision},
            }
        if intent == "evidence":
            citations = self._decision_citations(top_decision, issue_map=issue_map, evidence_map=evidence_map)
            if not citations:
                citations = self._evidence_citations(list(evidence_map.values()))
            return {
                "intent": intent,
                "top_decision": top_decision,
                "top_issue": top_issue,
                "citations": citations,
                "referenced_sections": ["appendix", "diagnosis_report"],
                "insufficient_grounding": not bool(citations),
                "grounding_pack": {
                    "top_decision": top_decision,
                    "top_issue": top_issue,
                    "citations": citations,
                },
            }
        if intent == "execution":
            citations = self._stage_citations(top_stage, top_decision=top_decision, issue_map=issue_map, evidence_map=evidence_map)
            analysis_first_surface = self._uses_analysis_first_surface(result_package)
            return {
                "intent": intent,
                "execution_stages": stages,
                "top_stage": top_stage,
                "top_decision": top_decision,
                "analysis_first_surface": analysis_first_surface,
                "citations": citations,
                "referenced_sections": ["improvement_plan_bundle"],
                "insufficient_grounding": not bool(stages),
                "grounding_pack": {
                    "execution_stages": stages,
                    "top_stage": top_stage,
                    "top_decision": top_decision,
                    "analysis_first_surface": analysis_first_surface,
                },
            }
        if intent == "risk":
            citations = self._risk_citations(top_risk, top_decision=top_decision, issue_map=issue_map, evidence_map=evidence_map)
            return {
                "intent": intent,
                "risk_checkpoints": risk_checkpoints,
                "top_risk": top_risk,
                "top_decision": top_decision,
                "citations": citations,
                "referenced_sections": ["improvement_plan_bundle", "diagnosis_report"],
                "insufficient_grounding": not bool(top_risk or citations),
                "grounding_pack": {"risk_checkpoints": risk_checkpoints, "top_risk": top_risk, "top_decision": top_decision},
            }
        coverage_summary = structure_snapshot.get("coverage_summary") or {}
        citations = self._evidence_citations(list(evidence_map.values()))
        return {
            "intent": intent,
            "structure_snapshot": structure_snapshot,
            "coverage_summary": coverage_summary,
            "citations": citations,
            "referenced_sections": ["structure_snapshot", "appendix"],
            "insufficient_grounding": not bool(structure_snapshot),
            "grounding_pack": {"structure_snapshot": structure_snapshot, "coverage_summary": coverage_summary},
        }

    def _decision_citations(
        self,
        decision: dict[str, Any],
        *,
        issue_map: dict[str, dict[str, Any]],
        evidence_map: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        decision_id = str(decision.get("decision_id") or "").strip()
        issue_ids = [str(item).strip() for item in decision.get("issue_ids") or [] if str(item).strip()]
        issue_id = issue_ids[0] if issue_ids else None
        evidence_ids = [str(item).strip() for item in decision.get("evidence_ids") or [] if str(item).strip()]
        if not evidence_ids and issue_id and issue_id in issue_map:
            evidence_ids = [str(item).strip() for item in issue_map[issue_id].get("evidence_ids") or [] if str(item).strip()]
        citations: list[dict[str, Any]] = []
        for evidence_id in evidence_ids[:2]:
            evidence = evidence_map.get(evidence_id) or {}
            citations.append(
                {
                    "decision_id": decision_id or None,
                    "issue_id": issue_id,
                    "evidence_id": evidence_id,
                    "locator": str(evidence.get("locator") or ""),
                    "excerpt": str(evidence.get("excerpt") or ""),
                }
            )
        if not citations and decision_id:
            citations.append({"decision_id": decision_id, "issue_id": issue_id})
        return citations

    def _evidence_citations(self, evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        for evidence in evidence_items[:2]:
            citations.append(
                {
                    "evidence_id": str(evidence.get("evidence_id") or ""),
                    "locator": str(evidence.get("locator") or ""),
                    "excerpt": str(evidence.get("excerpt") or ""),
                }
            )
        return citations

    def _stage_citations(
        self,
        stage: dict[str, Any],
        *,
        top_decision: dict[str, Any],
        issue_map: dict[str, dict[str, Any]],
        evidence_map: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        stage_id = str(stage.get("stage_id") or "").strip()
        citations = self._decision_citations(top_decision, issue_map=issue_map, evidence_map=evidence_map)
        if stage_id:
            citations.insert(0, {"stage_id": stage_id})
        return citations

    def _risk_citations(
        self,
        risk: dict[str, Any],
        *,
        top_decision: dict[str, Any],
        issue_map: dict[str, dict[str, Any]],
        evidence_map: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if isinstance(risk, dict):
            decision_ids = [str(item).strip() for item in risk.get("decision_ids") or [] if str(item).strip()]
            if decision_ids:
                return [{"decision_id": decision_ids[0]}]
        return self._decision_citations(top_decision, issue_map=issue_map, evidence_map=evidence_map)

    def _build_deterministic_answer(
        self,
        *,
        audience: str,
        intent: str,
        grounding: dict[str, Any],
    ) -> str:
        if grounding.get("insufficient_grounding"):
            return (
                "현재 저장된 결과 패키지 안에서 질문을 직접 뒷받침할 grounding이 부족합니다. "
                "지원 범위는 strategy, priority, evidence, execution, risk, scope입니다."
            )

        if intent == "strategy":
            internal_strategy = str(grounding.get("recommended_strategy") or "-")
            display_strategy = str(grounding.get("display_strategy") or internal_strategy or "-")
            analysis_first_surface = bool(grounding.get("analysis_first_surface"))
            top_decision = grounding.get("top_decision") or {}
            decision_type = str(top_decision.get("decision_type") or "-")
            rationale = self._terminal_sentence(str(top_decision.get("rationale") or "").strip())
            if analysis_first_surface:
                templates = {
                    "developer": (
                        f"내부 taxonomy 전략은 {internal_strategy}이고 사용자 노출 문구는 {display_strategy}입니다. "
                        f"최상위 decision type은 {decision_type}이며, 근거 설명은 {rationale}"
                    ),
                    "manager": (
                        f"우선 검토 기준은 {display_strategy}입니다. "
                        f"최상위 판단 유형은 {decision_type}이고, 근거 설명은 {rationale}"
                    ),
                    "client": (
                        f"이번 결과는 {display_strategy} 기준으로 정리했습니다. "
                        f"최상위 판단 유형은 {decision_type}이며, 주된 이유는 {rationale}"
                    ),
                }
                return templates.get(audience, templates["manager"])
            templates = {
                "developer": f"추천 전략은 {internal_strategy}입니다. 최상위 decision type은 {decision_type}이며, rationale은 {rationale}",
                "manager": f"현재 권장 전략은 {display_strategy}입니다. 최상위 판단 유형은 {decision_type}이고, 근거 설명은 {rationale}",
                "client": f"권장 방향은 {display_strategy}입니다. 최상위 판단 유형은 {decision_type}이며, 주된 이유는 {rationale}",
            }
            return templates.get(audience, templates["manager"])

        if intent == "priority":
            top_decision = grounding.get("top_decision") or {}
            score = int(top_decision.get("priority_score") or 0)
            breakdown = top_decision.get("score_breakdown") or {}
            templates = {
                "developer": (
                    f"최상위 priority score는 {score}입니다. severity component는 {int(breakdown.get('severity_component') or 0)}, "
                    f"blast radius component는 {int(breakdown.get('blast_radius_component') or 0)}, "
                    f"effort component는 {int(breakdown.get('effort_component') or 0)}입니다."
                ),
                "manager": (
                    f"최상위 우선순위 점수는 {score}입니다. severity {int(breakdown.get('severity_component') or 0)}, "
                    f"blast radius {int(breakdown.get('blast_radius_component') or 0)}, effort {int(breakdown.get('effort_component') or 0)}가 반영되었습니다."
                ),
                "client": (
                    f"최우선 항목의 점수는 {score}입니다. severity {int(breakdown.get('severity_component') or 0)}, "
                    f"blast radius {int(breakdown.get('blast_radius_component') or 0)}, effort {int(breakdown.get('effort_component') or 0)}를 기준으로 계산되었습니다."
                ),
            }
            return templates.get(audience, templates["manager"])

        if intent == "evidence":
            citations = grounding.get("citations") or []
            evidence_lines = []
            for citation in citations[:2]:
                locator = str(citation.get("locator") or "").strip()
                excerpt = str(citation.get("excerpt") or "").strip()
                if locator and excerpt:
                    evidence_lines.append(f"{locator}에서 {excerpt}")
                elif excerpt:
                    evidence_lines.append(excerpt)
                elif locator:
                    evidence_lines.append(locator)
            joined = "; ".join(evidence_lines) if evidence_lines else "연결된 evidence가 정리되어 있습니다."
            templates = {
                "developer": f"현재 답변의 직접 근거는 {joined} 입니다.",
                "manager": f"이 판단은 {joined} 기준으로 연결되어 있습니다.",
                "client": f"이 설명은 {joined} 근거를 기준으로 작성되었습니다.",
            }
            return templates.get(audience, templates["manager"])

        if intent == "execution":
            stages = grounding.get("execution_stages") or []
            top_stage = grounding.get("top_stage") or {}
            top_title = str(top_stage.get("title") or "-")
            tasks = [str(item).strip() for item in top_stage.get("tasks") or [] if str(item).strip()]
            task_text = ", ".join(tasks[:2]) if tasks else "-"
            if bool(grounding.get("analysis_first_surface")):
                templates = {
                    "developer": f"검토 단계는 {len(stages)}개입니다. 시작 단계는 {top_title}이고, 주요 확인 항목은 {task_text}입니다.",
                    "manager": f"검토 단계는 총 {len(stages)}개이며, 첫 단계는 {top_title}입니다. 시작 확인 항목은 {task_text}입니다.",
                    "client": f"검토 단계는 {len(stages)}개로 정리되어 있고, 첫 단계는 {top_title}입니다. 시작 확인 항목은 {task_text}입니다.",
                }
                return templates.get(audience, templates["manager"])
            templates = {
                "developer": f"실행 단계는 {len(stages)}개입니다. 시작 단계는 {top_title}이고, 주요 작업은 {task_text}입니다.",
                "manager": f"실행 단계는 총 {len(stages)}개이며, 첫 단계는 {top_title}입니다. 시작 작업은 {task_text}입니다.",
                "client": f"진행 단계는 {len(stages)}개로 정리되어 있고, 첫 단계는 {top_title}입니다. 시작 작업은 {task_text}입니다.",
            }
            return templates.get(audience, templates["manager"])

        if intent == "risk":
            top_risk = grounding.get("top_risk") or {}
            title = str(top_risk.get("title") or "-")
            description = str(top_risk.get("description") or "").strip() or "-"
            templates = {
                "developer": f"최상위 리스크 체크포인트는 {title}입니다. 설명은 {description}입니다.",
                "manager": f"주요 리스크 체크포인트는 {title}이며, 설명은 {description}입니다.",
                "client": f"주요 주의 사항은 {title}이며, 설명은 {description}입니다.",
            }
            return templates.get(audience, templates["manager"])

        coverage = grounding.get("coverage_summary") or {}
        templates = {
            "developer": (
                f"분석 범위는 asset {int(coverage.get('asset_count') or 0)}개, component {int(coverage.get('component_count') or 0)}개, "
                f"feature slice {int(coverage.get('slice_count') or 0)}개입니다."
            ),
            "manager": (
                f"이번 분석 범위는 자산 {int(coverage.get('asset_count') or 0)}개, 컴포넌트 {int(coverage.get('component_count') or 0)}개, "
                f"기능 슬라이스 {int(coverage.get('slice_count') or 0)}개입니다."
            ),
            "client": (
                f"검토 범위는 자산 {int(coverage.get('asset_count') or 0)}개, 컴포넌트 {int(coverage.get('component_count') or 0)}개, "
                f"기능 슬라이스 {int(coverage.get('slice_count') or 0)}개입니다."
            ),
        }
        return templates.get(audience, templates["manager"])

    def _sentence_value(self, text: str) -> str:
        normalized = " ".join(str(text or "").split()).strip()
        if not normalized:
            return "-"
        return normalized.rstrip(". ")

    def _terminal_sentence(self, text: str) -> str:
        normalized = self._sentence_value(text)
        if normalized == "-":
            return normalized
        if normalized.endswith((".", "!", "?")):
            return normalized
        return f"{normalized}."

    def _surface_wording(self, result_package: dict[str, Any]) -> dict[str, Any]:
        extensions = result_package.get("extensions") if isinstance(result_package, dict) else {}
        extensions = extensions if isinstance(extensions, dict) else {}
        governance = extensions.get("decision_governance")
        governance = governance if isinstance(governance, dict) else {}
        wording = governance.get("surface_wording")
        return wording if isinstance(wording, dict) else {}

    def _display_strategy(self, *, result_package: dict[str, Any], fallback: str) -> str:
        wording = self._surface_wording(result_package)
        display = str(wording.get("display_strategy") or "").strip()
        if display:
            return display
        governance = ((result_package.get("extensions") or {}) if isinstance(result_package, dict) else {}).get("decision_governance")
        if isinstance(governance, dict):
            outline = governance.get("document_outline")
            if isinstance(outline, dict):
                outline_strategy = str(outline.get("recommended_strategy") or "").strip()
                if outline_strategy:
                    return outline_strategy
        return fallback

    def _uses_analysis_first_surface(self, result_package: dict[str, Any]) -> bool:
        wording = self._surface_wording(result_package)
        return str(wording.get("mode") or "").strip() == "analysis_first_operational_source"

    async def _maybe_ai_rewrite(
        self,
        *,
        rewrite_request: QARewriteRequest,
        llm_service: Any | None,
    ) -> tuple[str, str, dict[str, Any]]:
        if llm_service is None or not hasattr(llm_service, "generate"):
            return (
                rewrite_request.deterministic_answer,
                "deterministic",
                {
                    "source": "deterministic",
                    "model": "",
                    "validation_passed": True,
                    "fallback_reason": "llm_service_unavailable",
                    "prompt_version": PROMPT_VERSION,
                },
            )

        try:
            raw_response = await llm_service.generate(
                prompt=self._build_prompt(rewrite_request),
                system_prompt=self._system_prompt(),
                mode="thinking",
                temperature=0.1,
                max_tokens=400,
                auto_unload=True,
            )
        except Exception as exc:
            return (
                rewrite_request.deterministic_answer,
                "deterministic",
                {
                    "source": "deterministic",
                    "model": "",
                    "validation_passed": False,
                    "fallback_reason": f"llm_generate_failed:{type(exc).__name__}",
                    "prompt_version": PROMPT_VERSION,
                },
            )

        parsed = self._parse_response(raw_response)
        if parsed is None:
            return (
                rewrite_request.deterministic_answer,
                "deterministic",
                {
                    "source": "deterministic",
                    "model": "",
                    "validation_passed": False,
                    "fallback_reason": "invalid_json_response",
                    "prompt_version": PROMPT_VERSION,
                },
            )
        valid, failure_reason = self._validate_rewrite(parsed, rewrite_request)
        if not valid:
            return (
                rewrite_request.deterministic_answer,
                "deterministic",
                {
                    "source": "deterministic",
                    "model": "",
                    "validation_passed": False,
                    "fallback_reason": failure_reason,
                    "prompt_version": PROMPT_VERSION,
                },
            )
        return (
            parsed,
            "ai_grounded",
            {
                "source": "ai",
                "model": getattr(raw_response, "model", "") or getattr(llm_service, "get_model_for_mode", lambda mode: "")("thinking"),
                "validation_passed": True,
                "fallback_reason": "",
                "prompt_version": PROMPT_VERSION,
            },
        )

    def _build_prompt(self, request: QARewriteRequest) -> str:
        payload = request.model_dump()
        return (
            "아래 grounded QA draft를 읽고 answer만 더 자연스럽게 다듬어라.\n"
            "새 사실, 새 숫자, 새 고유명사, 새 판단을 추가하지 마라.\n"
            "decision type, priority score, stage linkage, citation 연결은 절대 바꾸지 마라.\n"
            "JSON object로 {\"answer\": \"...\"}만 반환하라.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    def _system_prompt(self) -> str:
        return (
            "You are refining a grounded answer for a deterministic decision tool. "
            "Do not add facts. Do not add new numbers or named entities. "
            "Return JSON only."
        )

    def _parse_response(self, raw_response: Any) -> str | None:
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
        answer = str(parsed.get("answer") or "").strip()
        return answer or None

    def _validate_rewrite(self, answer: str, request: QARewriteRequest) -> tuple[bool, str]:
        allowed_text = json.dumps(request.model_dump(), ensure_ascii=False, sort_keys=True)
        allowed_numbers = set(re.findall(r"(?<!\d)\d[\d,]*(?!\d)", allowed_text))
        allowed_upper_tokens = set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", allowed_text))

        answer_numbers = set(re.findall(r"(?<!\d)\d[\d,]*(?!\d)", answer))
        if not answer_numbers.issubset(allowed_numbers):
            return False, "new_numeric_fact"
        answer_upper_tokens = set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", answer))
        if not answer_upper_tokens.issubset(allowed_upper_tokens):
            return False, "new_named_token"
        deterministic = request.deterministic_answer
        if not deterministic.strip():
            return False, "empty_deterministic_answer"
        if not answer.strip():
            return False, "empty_answer"
        return True, ""
