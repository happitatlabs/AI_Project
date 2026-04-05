from __future__ import annotations

import re

from .fx_engine import calculate_fx
from .policy import select_active_policy
from .schemas import (
    AccountingAnalysisResult,
    AccountingExtension,
    AccountingInputBundle,
    CalculationStatus,
    FxCalculationResult,
    SourceTaggedMessage,
)
from .validation import validate_accounting_input
from .voucher_review import review_vouchers


class AccountingMvpService:
    def build_extension(
        self,
        *,
        accounting_input: AccountingInputBundle | None,
        context_text: str,
        accounting_input_error: str = "",
    ) -> AccountingExtension:
        validation = validate_accounting_input(accounting_input, parse_error=accounting_input_error)
        strict = accounting_input.strict if accounting_input else True

        selected_policy = None
        policy_warnings: list[str] = []
        ambiguous_inputs = list(validation.ambiguous_inputs)
        if validation.status != "failed" and accounting_input is not None:
            selected_policy, policy_warnings, policy_ambiguity = select_active_policy(
                accounting_input.policies,
                tx_dates=[tx.occurred_at[:10] for tx in accounting_input.transactions],
                strict=strict,
            )
            ambiguous_inputs.extend(policy_ambiguity)
        validation.ambiguous_inputs = self._dedupe(ambiguous_inputs)
        validation.warnings = self._dedupe(validation.warnings + policy_warnings)
        if validation.ambiguous_inputs and strict and validation.status != "failed":
            validation.status = "failed"
            validation.failure_reason = validation.ambiguous_inputs[0]

        analysis = self._build_accounting_analysis(accounting_input, context_text, selected_policy)

        if validation.status == "failed":
            calc_status = self._build_failed_status(validation.failure_reason)
            fx_result = FxCalculationResult(status="failed", method=analysis.recommended_method, failure_reason=validation.failure_reason)
            voucher_result = review_vouchers([], [], fx_result=fx_result, policy=selected_policy, strict=strict)
            return AccountingExtension(
                input_validation=validation,
                calculation_status=calc_status,
                accounting_analysis=analysis,
                fx_calculation=fx_result,
                voucher_review=voucher_result,
                summary_sentence=self._build_failure_summary(calc_status.blocking_issue),
            )

        calc_status = CalculationStatus(can_calculate=True, reason="all required inputs present")
        fx_result = calculate_fx(
            accounting_input.transactions,
            accounting_input.exchange_rates,
            policy=selected_policy,
            strict=strict,
        )
        if fx_result.status != "completed":
            calc_status = self._build_failed_status(fx_result.failure_reason or "fx calculation failed")

        voucher_result = review_vouchers(
            accounting_input.vouchers,
            accounting_input.account_mappings,
            fx_result=fx_result,
            policy=selected_policy,
            strict=strict,
        )
        if voucher_result.status == "failed":
            voucher_result.warnings.append(voucher_result.failure_reason)

        summary_sentence = (
            self._build_success_summary(analysis.recommended_method or fx_result.method, fx_result.realized_gain_loss_krw)
            if calc_status.can_calculate and fx_result.status == "completed"
            else self._build_failure_summary(calc_status.blocking_issue)
        )
        return AccountingExtension(
            input_validation=validation,
            calculation_status=calc_status,
            accounting_analysis=analysis,
            fx_calculation=fx_result,
            voucher_review=voucher_result,
            summary_sentence=summary_sentence,
        )

    def _build_accounting_analysis(
        self,
        accounting_input: AccountingInputBundle | None,
        context_text: str,
        selected_policy,
    ) -> AccountingAnalysisResult:
        candidates: list[str] = []
        reasons: list[SourceTaggedMessage] = []
        evidence_refs: list[str] = []
        normalized = (context_text or "").lower()

        if accounting_input and accounting_input.policies:
            for policy in accounting_input.policies:
                if policy.fx_cost_method not in candidates:
                    candidates.append(policy.fx_cost_method)
            reasons.append(
                SourceTaggedMessage(
                    message=f"정책 입력에서 {accounting_input.policies[0].fx_cost_method} 방식이 확인되었습니다.",
                    source_tags=["policy"],
                    source_refs=[f"policy:{policy.policy_id}" for policy in accounting_input.policies],
                )
            )
            evidence_refs.extend(f"policy:{policy.policy_id}" for policy in accounting_input.policies)

        token_map = {
            "fifo": "FIFO",
            "moving average": "MOVING_AVERAGE",
            "weighted average": "MOVING_AVERAGE",
            "specific id": "SPECIFIC_ID",
        }
        for token, method in token_map.items():
            if token in normalized and method not in candidates:
                candidates.append(method)
                reasons.append(
                    SourceTaggedMessage(
                        message=f"코드/자산 문맥에서 {method} 신호가 확인되었습니다.",
                        source_tags=["inferred"],
                        source_refs=["safe_bundle:context"],
                    )
                )
                evidence_refs.append("safe_bundle:context")

        recommended = selected_policy.fx_cost_method if selected_policy is not None else (candidates[0] if candidates else "")
        return AccountingAnalysisResult(
            candidate_methods=candidates,
            recommended_method=recommended,
            reasons=reasons,
            evidence_refs=self._dedupe(evidence_refs),
        )

    def _build_success_summary(self, method: str, realized_gain_loss_krw: int | None) -> str:
        numeric = int(realized_gain_loss_krw or 0)
        return f"이 시스템은 {self._method_label(method)}을 사용하며, 현재 기준 환차익은 {numeric:,}원입니다."

    def _build_failure_summary(self, blocking_issue: str) -> str:
        issue = (blocking_issue or "필수 회계 입력이 누락되었습니다.").strip()
        return f"회계 계산을 수행할 수 없습니다. {self._humanize_blocking_issue(issue)}"

    def _build_failed_status(self, blocking_issue: str) -> CalculationStatus:
        return CalculationStatus(can_calculate=False, blocking_issue=blocking_issue)

    def _humanize_blocking_issue(self, issue: str) -> str:
        mapping = {
            "missing required inputs: transactions": "거래 데이터가 누락되었습니다.",
            "missing required inputs: exchange_rates": "환율 데이터가 누락되었습니다.",
            "missing required inputs: policies": "회계 정책 데이터가 누락되었습니다.",
            "missing exchange_rates": "환율 데이터가 누락되었습니다.",
        }
        if issue in mapping:
            return mapping[issue]
        if issue.startswith("missing required inputs:"):
            missing = issue.split(":", 1)[1].strip()
            return f"필수 입력이 누락되었습니다. ({missing})"
        if "exchange rate" in issue.lower():
            return "환율 선택 근거가 불명확합니다."
        if "policy" in issue.lower():
            return "적용할 회계 정책을 확정할 수 없습니다."
        if "lot" in issue.lower():
            return "lot/source 지정이 없어 계산을 확정할 수 없습니다."
        return issue.rstrip(".") + "."

    def _method_label(self, method: str) -> str:
        mapping = {
            "MOVING_AVERAGE": "이동평균법",
            "FIFO": "선입선출법",
            "SPECIFIC_ID": "개별식별법",
        }
        return mapping.get((method or "").upper(), method or "회계 방식")

    def _dedupe(self, items: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for item in items:
            key = re.sub(r"\s+", " ", item).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output


def build_accounting_extension(
    *,
    accounting_input: AccountingInputBundle | None,
    context_text: str,
    accounting_input_error: str = "",
) -> AccountingExtension:
    return AccountingMvpService().build_extension(
        accounting_input=accounting_input,
        context_text=context_text,
        accounting_input_error=accounting_input_error,
    )
