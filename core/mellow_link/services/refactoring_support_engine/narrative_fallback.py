from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from mellow_link.modules.rebuild_assistant.schemas import RecommendedOption, RetainedContract

from .narrative_axis import NarrativeAxisResolver


@dataclass
class DeterministicNarrativeBundle:
    narrative_axis: str
    report_purpose: str
    report_scope: list[str]
    report_questions: list[str]
    primary_judgment_reason: str
    one_line_conclusion: str
    executive_summary_v2: list[str] = field(default_factory=list)
    core_business_rules: list[str] = field(default_factory=list)
    retained_contracts: list[RetainedContract] = field(default_factory=list)


class DeterministicNarrativeBuilder:
    def __init__(self) -> None:
        self.axis_resolver = NarrativeAxisResolver()

    def build(
        self,
        *,
        prepared,
        diagnosis,
        decisions,
        improvement,
        confidence: float,
        extensions: dict[str, Any],
    ) -> DeterministicNarrativeBundle:
        accounting = extensions.get("accounting") if isinstance(extensions, dict) else None
        governance = extensions.get("decision_governance") if isinstance(extensions, dict) else None
        narrative_axis = self.axis_resolver.select_axis(
            prepared,
            diagnosis.grounded_business_rules,
            diagnosis.retained_contracts,
            decisions.primary_judgment,
        )
        core_business_rules = self.axis_resolver.prioritize_rule_texts(
            narrative_axis,
            diagnosis.grounded_business_rules,
            diagnosis.core_business_rules,
        )
        retained_contracts = self.axis_resolver.prioritize_contracts(
            narrative_axis,
            diagnosis.retained_contracts,
        )

        if isinstance(accounting, dict):
            return self._build_accounting_bundle(
                narrative_axis=narrative_axis,
                accounting=accounting,
                decisions=decisions,
                core_business_rules=core_business_rules,
                retained_contracts=retained_contracts,
            )
        return self._build_general_bundle(
            prepared=prepared,
            decisions=decisions,
            improvement=improvement,
            confidence=confidence,
            narrative_axis=narrative_axis,
            core_business_rules=core_business_rules,
            retained_contracts=retained_contracts,
            governance=governance if isinstance(governance, dict) else {},
        )

    def _build_general_bundle(
        self,
        *,
        prepared,
        decisions,
        improvement,
        confidence: float,
        narrative_axis: str,
        core_business_rules: list[str],
        retained_contracts: list[RetainedContract],
        governance: dict[str, Any],
    ) -> DeterministicNarrativeBundle:
        report_purpose, report_scope, report_questions = self._general_report_metadata(narrative_axis)
        concept = self._primary_concept(prepared)
        concept_label = self._concept_label(concept, narrative_axis)
        subject = self._subject_phrase(concept_label)
        subject_topic = self._attach_topic_particle(subject)
        lead_rule = self._normalize_conclusion_rule_anchor(core_business_rules[0] if core_business_rules else "")
        if any(token in lead_rule for token in ("필요합니다", "해야", "분리", "유지")) or len(lead_rule) > 28:
            lead_rule = ""
        option_text = self._option_label(improvement.recommended_option)
        axis_phrase = self._axis_phrase(narrative_axis) or lead_rule
        top_decision = decisions.decision_summary.decisions[0] if decisions.decision_summary.decisions else None
        grounding = governance.get("recommendation_grounding") if isinstance(governance, dict) else {}
        grounding_level = str((grounding or {}).get("level") or "")
        insufficient_grounding = bool((grounding or {}).get("insufficient_grounding"))
        document_outline = governance.get("document_outline") if isinstance(governance, dict) else {}
        next_step = str((document_outline or {}).get("next_step") or "").strip()

        if insufficient_grounding:
            primary_reason = "직접 확인된 구조 근거가 부족해 현재 결과는 검토용 판단 문서 초안으로 유지합니다."
        elif top_decision is None and narrative_axis == "query_filter":
            primary_reason = "직접 확인된 강한 구조 결정은 없지만 조회 조건과 필터 조합 신호가 가장 뚜렷하게 확인됐습니다."
        else:
            primary_reason = self._primary_reason(decisions, top_decision)

        if insufficient_grounding:
            one_line = (
                f"{subject_topic} 직접 확인된 구조 근거가 부족하므로 현재 단계에서는 구조 이전 전략을 확정하지 않고 "
                "관련 코드, 화면, 데이터 근거를 먼저 확인해야 합니다."
            )
        elif getattr(prepared, "scope_limited", False):
            one_line = f"{subject_topic} 단일 범위로 제한해 정책, 화면, 데이터 계약을 단계적으로 분리해야 합니다."
        elif top_decision is None and narrative_axis == "query_filter":
            one_line = "조회/필터 기능은 현재 자산 기준으로 조회 조건, 필터 조합, 결과 목록 구성을 한곳에서 정리하는 방향을 우선 검토하는 편이 적절합니다."
        else:
            anchor = lead_rule or axis_phrase or "직접 확인된 핵심 규칙"
            action_plan = self._action_plan_phrase(narrative_axis)
            if grounding_level == "limited":
                one_line = f"{subject_topic} 현재 확인된 {anchor}를 기준으로 {action_plan}하는 안을 우선 검토해야 합니다."
            elif narrative_axis in {
                "validation",
                "workflow",
                "state_transition",
                "access_control",
                "query_filter",
                "amount_threshold",
            }:
                one_line = f"{subject_topic} {anchor}를 기준으로 {action_plan}해야 합니다."
            else:
                one_line = self._fallback_conclusion(subject, confidence)

        if insufficient_grounding:
            executive_summary = [
                f"문제: {subject}의 구조와 의존성을 직접 판단할 근거가 부족합니다.",
                "영향: 현재 단계에서 전략을 단정하면 잘못된 책임 경계를 기준안으로 고정할 수 있습니다.",
                f"조치: 현재 결과는 {option_text or '추천안'}을 포함하더라도 검토용 초안으로만 유지하고 전략 확정은 보류해야 합니다.",
                f"다음 단계: {self._ensure_period(next_step or '누락된 레거시 코드와 운영 근거를 먼저 확보합니다.')}",
            ]
        elif top_decision is None and narrative_axis == "query_filter":
            executive_summary = [
                "조회/필터 기능은 현재 자산 기준으로 조회 조건, 필터 조합, 정렬 및 결과 목록 구성을 한 모델로 정리하는 방향을 우선 검토하는 편이 적절합니다.",
                "구조 재설계가 필요하다는 강한 신호는 직접 확인되지 않았습니다.",
                f"따라서 {option_text}을 파일럿 기준안으로 검토하는 수준이 적절합니다.",
            ]
        else:
            problem = self._problem_summary(subject, narrative_axis, top_decision)
            impact = self._impact_summary(narrative_axis, top_decision)
            action = self._summary_action_sentence(
                grounding_level=grounding_level,
                option_text=option_text,
                narrative_axis=narrative_axis,
            )
            executive_summary = [
                f"문제: {problem}",
                f"영향: {impact}",
                f"조치: {action}",
            ]
            if next_step:
                executive_summary.append(f"다음 단계: {self._ensure_period(next_step)}")
            elif grounding_level == "limited":
                executive_summary.append("다음 단계: 누락된 구조 근거를 보강한 뒤 검토안을 실행 후보로 승격할지 다시 판단합니다.")
            elif getattr(prepared, "missing_context", None):
                executive_summary.append("다음 단계: 추가 운영 확인이 필요한 항목을 별도 확인 목록으로 분리해 후속 검증합니다.")

        return DeterministicNarrativeBundle(
            narrative_axis=narrative_axis,
            report_purpose=report_purpose,
            report_scope=report_scope,
            report_questions=report_questions,
            primary_judgment_reason=primary_reason,
            one_line_conclusion=one_line,
            executive_summary_v2=executive_summary[:4],
            core_business_rules=core_business_rules,
            retained_contracts=retained_contracts,
        )

    def _build_accounting_bundle(
        self,
        *,
        narrative_axis: str,
        accounting: dict[str, Any],
        decisions,
        core_business_rules: list[str],
        retained_contracts: list[RetainedContract],
    ) -> DeterministicNarrativeBundle:
        report_purpose, report_scope, report_questions = self._accounting_report_metadata(accounting)
        summary_sentence = str(accounting.get("summary_sentence") or "").strip()
        calc_status = accounting.get("calculation_status") or {}
        fx_calc = accounting.get("fx_calculation") or {}
        voucher_review = accounting.get("voucher_review") or {}
        analysis = accounting.get("accounting_analysis") or {}
        warnings = self._collect_accounting_warnings(accounting)
        method_label = self._method_label(str(fx_calc.get("method") or analysis.get("recommended_method") or ""))
        amount_text = self._amount_text(fx_calc.get("realized_gain_loss_krw"))
        voucher_summary = self._voucher_summary(voucher_review)
        warning_text = self._humanize_accounting_issue(warnings[0]) if warnings else ""
        warning_label = self._accounting_issue_label(warnings[0]) if warnings else ""
        failure_text = self._humanize_accounting_issue(
            str(calc_status.get("blocking_issue") or fx_calc.get("failure_reason") or "")
        )
        failure_label = self._accounting_issue_label(
            str(calc_status.get("blocking_issue") or fx_calc.get("failure_reason") or "")
        )

        if not bool(calc_status.get("can_calculate")):
            one_line = f"회계 계산을 수행할 수 없습니다. {failure_text}"
            executive_summary = [
                report_purpose,
                "현재 입력 기준으로는 회계 계산을 수행할 수 없습니다.",
                f"주요 사유는 {failure_label or failure_text.rstrip('.')}입니다.",
                "필수 입력이 보완되면 재계산이 가능합니다.",
            ]
            primary_reason = f"계산 상태가 blocked이며 주요 차단 사유는 {failure_text.rstrip('.')}입니다."
        elif warnings:
            one_line = (
                f"회계 기능은 {method_label} 기준으로 계산을 수행했지만 {warning_label} 때문에 결과를 검토용 초안으로 유지해야 합니다."
            )
            executive_summary = [
                report_purpose or "이 문서는 외환 거래의 환차손익 계산 결과와 적용 회계 방식을 검토한 결과입니다.",
                summary_sentence or f"현재 기준 계산 방식은 {method_label}이며, 산출된 환차손익은 {amount_text}입니다.",
                f"추가 확인이 필요한 경고는 {warning_label}입니다.",
                voucher_summary,
            ]
            primary_reason = f"계산 결과는 확보됐지만 {warning_label} 때문에 검토용 초안 상태로 유지하는 편이 적절합니다."
        else:
            one_line = f"회계 기능은 {method_label} 기준으로 계산을 수행했고 현재 환차손익은 {amount_text}입니다."
            executive_summary = [
                report_purpose or "이 문서는 외환 거래의 환차손익 계산 결과와 적용 회계 방식을 검토한 결과입니다.",
                summary_sentence or f"현재 기준 계산 방식은 {method_label}이며, 산출된 환차손익은 {amount_text}입니다.",
                voucher_summary,
            ]
            primary_reason = f"회계 계산 결과와 전표 검토 근거를 함께 확인했고 현재 기준 계산 방식은 {method_label}입니다."

        if decisions.decision_summary.decisions:
            primary_reason = self._primary_reason(decisions, decisions.decision_summary.decisions[0], default=primary_reason)

        return DeterministicNarrativeBundle(
            narrative_axis=narrative_axis,
            report_purpose=report_purpose,
            report_scope=report_scope,
            report_questions=report_questions,
            primary_judgment_reason=primary_reason,
            one_line_conclusion=one_line,
            executive_summary_v2=[item for item in executive_summary if item][:4],
            core_business_rules=core_business_rules,
            retained_contracts=retained_contracts,
        )

    def _primary_reason(self, decisions, top_decision, default: str = "") -> str:
        if top_decision is None:
            return default or "상위 구조 이슈와 증거를 기준으로 개선 방향을 정리했습니다."
        score = top_decision.score_breakdown.get("final_score", top_decision.priority_score)
        decision_rule = top_decision.explainability.decision_rule
        return f"{top_decision.rationale} 우선순위 점수는 {score}이며, {decision_rule}"

    def _primary_concept(self, prepared) -> str:
        concepts = list(getattr(getattr(prepared, "signals", None), "concepts", []) or [])
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
        for item in concepts:
            text = str(item or "").strip()
            if text:
                return concept_map.get(text.lower(), text)
        goal = str(getattr(prepared, "goal", "") or "").strip()
        if goal:
            normalized = re.sub(r"\s+", " ", goal).strip()
            return normalized[:18]
        return "이 기능"

    def _axis_phrase(self, narrative_axis: str) -> str:
        mapping = {
            "workflow": "승인 트리거와 승인 단계 구조",
            "state_transition": "상태 전이 규칙과 처리 가능 상태",
            "access_control": "권한 체계와 승인 주체",
            "validation": "차단 조건과 검증 순서",
            "query_filter": "조회 조건과 필터 조합",
            "amount_threshold": "금액 기준과 한도 정책",
        }
        return mapping.get(narrative_axis, "")

    def _concept_label(self, concept: str, narrative_axis: str) -> str:
        stripped = (concept or "").strip()
        lowered = stripped.lower()
        if narrative_axis == "query_filter" and not any(token in lowered for token in ("조회", "검색", "filter", "query")):
            return "조회/필터"
        return stripped or "이"

    def _subject_phrase(self, concept_label: str) -> str:
        stripped = (concept_label or "").strip()
        if not stripped or stripped == "이":
            return "이 기능"
        if stripped == "조회/필터":
            return "조회/필터 기능"
        if stripped.endswith(("기능", "구조", "흐름", "화면", "영역", "정책", "모듈")):
            return stripped
        return f"{stripped} 기능"

    def _action_plan_phrase(self, narrative_axis: str) -> str:
        mapping = {
            "validation": "차단 조건, 검증 순서, 저장 전 검증을 검증 계층과 처리 흐름으로 분리",
            "workflow": "승인 트리거, 승인 단계, 예외 처리 경로를 워크플로우 계층으로 분리",
            "state_transition": "상태 전이, 처리 가능 상태, 전이 조건을 정책 계층으로 분리",
            "access_control": "승인 권한, 승인 주체, 부서 책임을 권한 정책 계층으로 분리",
            "query_filter": "조회 조건, 필터 조합, 결과 목록 구성을 조회 모델로 분리",
            "amount_threshold": "금액 구간, 한도 정책, 고액 처리 경계를 정책 계층으로 분리",
        }
        return mapping.get(narrative_axis, "정책, 화면, 데이터 계약을 책임 경계에 맞춰 분리")

    def _problem_summary(self, subject: str, narrative_axis: str, top_decision) -> str:
        if narrative_axis == "validation":
            return f"현재 자산에서는 {subject}의 차단 조건과 저장 전 검증이 한 흐름에 묶여 있습니다."
        if narrative_axis == "workflow":
            return f"현재 자산에서는 {subject}의 승인 흐름과 예외 처리 경계가 한 경로에 얽혀 있습니다."
        if narrative_axis == "state_transition":
            return f"현재 자산에서는 {subject}의 상태 전이 판단과 처리 흐름이 같은 경로에 섞여 있습니다."
        if narrative_axis == "access_control":
            return f"현재 자산에서는 {subject}의 권한 판단과 처리 경로가 같은 흐름에 얽혀 있습니다."
        if narrative_axis == "query_filter":
            return f"현재 자산에서는 {subject}의 조회 조건, 필터 조합, 결과 구성이 한 경로에 묶여 있습니다."
        if narrative_axis == "amount_threshold":
            return f"현재 자산에서는 {subject}의 금액 기준과 후속 처리 경계가 같은 흐름에 섞여 있습니다."
        if top_decision is not None and top_decision.decision_type == "redesign":
            return f"현재 자산에서는 {subject}의 책임 경계가 섞여 있어 구조 재정의가 필요합니다."
        return f"현재 자산에서는 {subject}의 핵심 규칙과 처리 흐름 경계가 충분히 분리되지 않았습니다."

    def _impact_summary(self, narrative_axis: str, top_decision) -> str:
        if narrative_axis == "validation":
            return "이 상태가 유지되면 예외 누락과 저장 경로 재작업 위험이 커집니다."
        if narrative_axis == "workflow":
            return "이 상태가 유지되면 승인 단계 누락과 예외 경로 불일치 위험이 커집니다."
        if narrative_axis == "state_transition":
            return "이 상태가 유지되면 예외 전이 누락과 상태 정합성 오류가 발생할 수 있습니다."
        if narrative_axis == "access_control":
            return "이 상태가 유지되면 승인 주체와 부서 책임이 다시 섞여 운영 혼선이 커질 수 있습니다."
        if narrative_axis == "query_filter":
            return "이 상태가 유지되면 조회 결과 정합성과 필터 조합 일관성이 흔들릴 수 있습니다."
        if narrative_axis == "amount_threshold":
            return "이 상태가 유지되면 한도 초과 처리와 고액 처리 경계가 일관되지 않게 적용될 수 있습니다."
        if top_decision is not None and top_decision.decision_type == "redesign":
            return "이 상태가 유지되면 경계 충돌이 계속 누적되어 후속 분리 비용이 커질 수 있습니다."
        return "이 상태가 유지되면 핵심 규칙이 여러 계층에 흩어져 후속 분리 비용이 커질 수 있습니다."

    def _summary_action_sentence(
        self,
        *,
        grounding_level: str,
        option_text: str,
        narrative_axis: str,
    ) -> str:
        action_plan = self._action_plan_phrase(narrative_axis)
        if grounding_level == "limited":
            action_tail = self._limited_action_tail(narrative_axis)
            if option_text:
                return f"{self._attach_object_particle(option_text)} 우선 검토안으로 두고 {action_plan}{action_tail}"
            return f"{action_plan}하는 안을 우선 검토해야 합니다."
        if option_text:
            return f"{self._attach_object_particle(option_text)} 우선안으로 두고 {action_plan}해야 합니다."
        return f"{action_plan}해야 합니다."

    def _limited_action_tail(self, narrative_axis: str) -> str:
        mapping = {
            "validation": "하는 방향을 먼저 검증해야 합니다.",
            "workflow": "하는 구조를 우선 구체화해야 합니다.",
            "state_transition": "하는 구조를 우선 구체화해야 합니다.",
            "access_control": "하는 구조를 우선 정리해야 합니다.",
            "query_filter": "하는 구조를 우선 점검해야 합니다.",
            "amount_threshold": "하는 구조를 우선 정리해야 합니다.",
        }
        return mapping.get(narrative_axis, "하는 구조를 우선 정리해야 합니다.")

    def _ensure_period(self, text: str) -> str:
        stripped = (text or "").strip()
        if not stripped:
            return ""
        if stripped[-1] in ".!?":
            return stripped
        return stripped + "."

    def _option_label(self, recommended_option: RecommendedOption | None) -> str:
        if recommended_option is None or not (recommended_option.name or "").strip():
            return "정책 중심 분리안"
        return recommended_option.name.strip()

    def _attach_object_particle(self, text: str) -> str:
        stripped = (text or "").strip()
        if not stripped:
            return "기준안"
        if re.search(r"[0-9A-Za-z]$", stripped):
            return f"{stripped}을"
        return f"{stripped}을"

    def _attach_topic_particle(self, text: str) -> str:
        stripped = (text or "").strip()
        if not stripped:
            return stripped
        last = stripped[-1]
        code = ord(last)
        if 0xAC00 <= code <= 0xD7A3:
            has_batchim = (code - 0xAC00) % 28 != 0
            return stripped + ("은" if has_batchim else "는")
        return stripped + "는"

    def _fallback_conclusion(self, concept: str, confidence: float) -> str:
        if confidence < 0.45:
            return f"{concept} 기능은 추가 구조 근거를 먼저 확보한 뒤 정책, 화면, 데이터 계약을 단계적으로 분리하는 것이 필요합니다."
        return f"{concept} 기능은 핵심 업무 규칙을 기준으로 정책, 화면, 데이터 계약을 단계적으로 분리하는 것이 필요합니다."

    def _normalize_conclusion_rule_anchor(self, text: str) -> str:
        normalized = (text or "").strip()
        normalized = re.sub(r"\s*규칙이 직접 확인되었습니다\.?$", "", normalized)
        normalized = re.sub(r"\s*을 기준으로 .*", "", normalized)
        normalized = re.sub(r"\s*를 기준으로 .*", "", normalized)
        normalized = re.sub(r"\s*을 검증해야 합니다\.?$", "", normalized)
        normalized = re.sub(r"\s*를 검증해야 합니다\.?$", "", normalized)
        normalized = re.sub(r"\s*을 유지해야 합니다\.?$", "", normalized)
        normalized = re.sub(r"\s*를 유지해야 합니다\.?$", "", normalized)
        normalized = normalized.rstrip(". ")
        return normalized

    def _general_report_metadata(self, narrative_axis: str) -> tuple[str, list[str], list[str]]:
        mapping: dict[str, tuple[str, list[str], list[str]]] = {
            "query_filter": (
                "조회 조건, 필터 조합, 정렬 및 결과 구성 규칙을 분석하기 위한 보고서입니다.",
                ["조회 조건", "필터 조합", "정렬 기준", "결과 구성 규칙"],
                [
                    "어떤 조회 조건이 핵심 규칙을 결정하는가?",
                    "필터와 정렬은 어떤 기준으로 조합되는가?",
                    "결과 목록 구성 규칙은 어디서 통제되는가?",
                ],
            ),
            "amount_threshold": (
                "금액 기준, 한도 정책, 경계 조건을 분석하기 위한 보고서입니다.",
                ["금액 기준", "한도 정책", "구간 경계", "후속 처리 경계"],
                [
                    "어떤 금액 기준과 한도 정책이 적용되는가?",
                    "구간별 경계 조건은 어떻게 나뉘는가?",
                    "한도 초과 시 어떤 후속 처리 규칙이 적용되는가?",
                ],
            ),
            "workflow": (
                "승인 트리거, 승인 단계, 예외 처리 흐름을 분석하기 위한 보고서입니다.",
                ["승인 트리거", "승인 주체", "승인 단계", "예외 처리 흐름"],
                [
                    "어떤 조건에서 승인 흐름이 시작되는가?",
                    "승인 단계와 의사결정 게이트는 어떻게 구성되는가?",
                    "예외 승인 또는 보류 흐름은 어떻게 처리되는가?",
                ],
            ),
            "access_control": (
                "권한 체계, 승인 주체, 조직별 처리 범위를 분석하기 위한 보고서입니다.",
                ["권한 체계", "승인 주체", "조직별 처리 범위", "예외 승인 규칙"],
                [
                    "누가 어떤 조건에서 처리가 가능한가?",
                    "승인 주체와 조직별 심사 경로는 어떻게 나뉘는가?",
                    "예외 승인 규칙은 어디서 통제되는가?",
                ],
            ),
            "state_transition": (
                "상태 전이 규칙과 처리 흐름을 분석하기 위한 보고서입니다.",
                ["상태 전이 규칙", "처리 가능 상태", "전이 조건", "후속 처리 흐름"],
                [
                    "어떤 상태 전이가 허용되는가?",
                    "처리 가능 상태와 차단 상태는 무엇인가?",
                    "전이 이후 후속 처리 흐름은 어떻게 이어지는가?",
                ],
            ),
            "validation": (
                "입력 검증, 저장 전 차단 조건, 예외 처리 기준을 분석하기 위한 보고서입니다.",
                ["입력 검증", "저장 전 차단 조건", "검증 순서", "예외 처리 기준"],
                [
                    "어떤 차단 조건과 검증 규칙이 적용되는가?",
                    "저장 전 검증 순서는 어떻게 구성되는가?",
                    "예외 처리 기준은 어디서 통제되는가?",
                ],
            ),
        }
        return mapping.get(
            narrative_axis,
            (
                "레거시 기능의 핵심 업무 규칙과 전환 구조를 분석하기 위한 보고서입니다.",
                ["핵심 업무 규칙", "유지 계약", "전환 구조"],
                [
                    "이 기능의 핵심 규칙은 무엇인가?",
                    "어떤 계약을 유지해야 하는가?",
                    "전환 시 우선 분리해야 할 구조는 무엇인가?",
                ],
            ),
        )

    def _accounting_report_metadata(self, accounting: dict[str, Any]) -> tuple[str, list[str], list[str]]:
        del accounting
        return (
            "외환 거래의 환차손익을 계산하고, 적용된 회계 방식과 전표 정합성을 함께 검토하기 위한 보고서입니다.",
            ["외화 거래 데이터", "환율 데이터", "회계 정책", "전표 검토 결과"],
            [
                "이 거래에서 환차익 또는 환차손은 얼마인가?",
                "어떤 계산 방식이 적용되었는가?",
                "전표와 계산 결과는 일치하는가?",
            ],
        )

    def _collect_accounting_warnings(self, accounting: dict[str, Any]) -> list[str]:
        validation = accounting.get("input_validation") or {}
        fx_calc = accounting.get("fx_calculation") or {}
        voucher_review = accounting.get("voucher_review") or {}
        candidates = []
        candidates.extend(str(item or "").strip() for item in (validation.get("ambiguous_inputs") or []))
        candidates.extend(str(item or "").strip() for item in (fx_calc.get("warnings") or []))
        candidates.extend(str(item or "").strip() for item in (validation.get("warnings") or []))
        candidates.extend(str(item or "").strip() for item in (voucher_review.get("warnings") or []))
        output: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            key = re.sub(r"\s+", " ", item).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output

    def _voucher_summary(self, voucher_review: dict[str, Any]) -> str:
        status = str(voucher_review.get("status") or "").strip().lower()
        if status == "completed":
            balance_ok = voucher_review.get("balance_ok")
            policy_ok = voucher_review.get("policy_consistent")
            if balance_ok is False or policy_ok is False:
                return "전표 검토 결과 차변·대변 또는 정책 일치 여부에 추가 확인이 필요합니다."
            return "전표 검토 결과 차변·대변과 정책 기준이 모두 일치합니다."
        if status == "input_missing":
            return "전표 검토는 입력 부족으로 아직 완료되지 않았습니다."
        failure_reason = str(voucher_review.get("failure_reason") or "").strip()
        if failure_reason:
            return f"전표 검토는 {self._humanize_accounting_issue(failure_reason).rstrip('.')} 때문에 완료되지 않았습니다."
        return "전표 검토 결과는 후속 확인 대상으로 두는 편이 적절합니다."

    def _amount_text(self, value: Any) -> str:
        if value is None:
            return "산출 금액"
        try:
            return f"{int(value):,}원"
        except Exception:
            return str(value)

    def _method_label(self, method: str) -> str:
        mapping = {
            "MOVING_AVERAGE": "이동평균법",
            "FIFO": "선입선출법",
            "SPECIFIC_ID": "개별식별법",
        }
        return mapping.get((method or "").strip().upper(), (method or "").strip() or "회계 방식")

    def _humanize_accounting_issue(self, value: str) -> str:
        text = (value or "").strip()
        if not text:
            return "추가 입력 확인이 필요합니다."
        mapping = {
            "all required inputs present": "필수 입력이 모두 제공되었습니다.",
            "voucher_review requires vouchers and account_mappings": "전표 데이터와 계정 매핑이 없어 전표 검토를 수행할 수 없습니다.",
            "missing exchange_rates": "환율 데이터가 누락되었습니다.",
            "missing required inputs: transactions": "거래 데이터가 누락되었습니다.",
            "missing required inputs: exchange_rates": "환율 데이터가 누락되었습니다.",
            "missing required inputs: policies": "회계 정책 데이터가 누락되었습니다.",
            "missing required inputs: vouchers": "전표 데이터가 누락되었습니다.",
            "missing required inputs: account_mappings": "계정 매핑이 누락되었습니다.",
            "multiple active policies matched transaction dates": "복수 정책이 거래일과 동시에 일치해 적용 정책을 확정할 수 없습니다.",
            "no active policy covers transaction dates": "거래일을 포괄하는 활성 정책이 없습니다.",
            "ambiguous exchange rate": "복수 환율 후보가 있어 적용 환율을 바로 확정할 수 없습니다.",
        }
        if text in mapping:
            return mapping[text]
        lowered = text.lower()
        if text.startswith("invalid accounting payload schema:"):
            if "occurred_at" in lowered:
                return "거래일(occurred_at) 입력이 누락되었습니다."
            if "rate_date" in lowered:
                return "환율 기준일(rate_date) 입력이 누락되었습니다."
            if "currency" in lowered:
                return "통화(currency) 입력이 누락되었습니다."
        if text.startswith("invalid accounting payload json:"):
            return "회계 입력 JSON 형식이 올바르지 않습니다."
        if "exchange rate" in lowered:
            return "환율 선택 근거가 불명확합니다."
        if "policy" in lowered:
            return "적용할 회계 정책을 확정할 수 없습니다."
        if "lot" in lowered:
            return "lot/source 지정이 없어 계산을 확정할 수 없습니다."
        return text.rstrip(".") + "."

    def _accounting_issue_label(self, value: str) -> str:
        text = (value or "").strip()
        mapping = {
            "missing exchange_rates": "환율 데이터 누락",
            "missing required inputs: exchange_rates": "환율 데이터 누락",
            "missing required inputs: transactions": "거래 데이터 누락",
            "missing required inputs: policies": "회계 정책 데이터 누락",
            "missing required inputs: vouchers": "전표 데이터 누락",
            "missing required inputs: account_mappings": "계정 매핑 누락",
            "ambiguous exchange rate": "복수 환율 경고",
        }
        if text in mapping:
            return mapping[text]
        humanized = self._humanize_accounting_issue(text).rstrip(".")
        if humanized.endswith("가 누락되었습니다"):
            return humanized.replace("가 누락되었습니다", " 누락").strip()
        return humanized

    def _has_accounting_fx_result(self, fx_calculation: dict[str, Any]) -> bool:
        if fx_calculation.get("status") == "completed":
            return True
        if fx_calculation.get("realized_gain_loss_krw") is not None:
            return True
        return False

    def _has_accounting_voucher_review(self, voucher_review: dict[str, Any]) -> bool:
        status = str(voucher_review.get("status") or "").strip().lower()
        if status in {"completed", "input_missing"}:
            return True
        return bool(voucher_review.get("review_points") or voucher_review.get("mismatches"))

    def _has_accounting_analysis_result(self, analysis: dict[str, Any]) -> bool:
        return bool(analysis.get("candidate_methods") or analysis.get("recommended_method") or analysis.get("reasons"))
