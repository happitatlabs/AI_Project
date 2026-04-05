from __future__ import annotations

from .schemas import (
    AccountingPolicy,
    AccountingVoucher,
    AccountMapping,
    FxCalculationResult,
    SourceTaggedMessage,
    VoucherReviewResult,
)


def review_vouchers(
    vouchers: list[AccountingVoucher],
    account_mappings: list[AccountMapping],
    *,
    fx_result: FxCalculationResult,
    policy: AccountingPolicy | None,
    strict: bool,
) -> VoucherReviewResult:
    if not vouchers or not account_mappings:
        return VoucherReviewResult(
            status="input_missing",
            failure_reason="전표 데이터와 계정 매핑이 없어 전표 검토를 수행할 수 없습니다.",
        )

    tolerance = float(policy.tolerance_krw if policy else 1.0)
    review_points: list[SourceTaggedMessage] = []
    mismatches: list[SourceTaggedMessage] = []
    mapping_by_purpose = {item.purpose: item.account_code for item in account_mappings}

    balance_ok = True
    for voucher in vouchers:
        debit_total = sum(line.amount_krw for line in voucher.lines if line.side == "debit")
        credit_total = sum(line.amount_krw for line in voucher.lines if line.side == "credit")
        if abs(debit_total - credit_total) > tolerance:
            balance_ok = False
            mismatches.append(
                SourceTaggedMessage(
                    message=f"{voucher.voucher_id} 전표는 차변/대변이 일치하지 않습니다.",
                    source_tags=["voucher"],
                    source_refs=[f"voucher:{voucher.voucher_id}"],
                )
            )
        else:
            review_points.append(
                SourceTaggedMessage(
                    message=f"{voucher.voucher_id} 전표는 차변/대변 균형이 맞습니다.",
                    source_tags=["voucher"],
                    source_refs=[f"voucher:{voucher.voucher_id}"],
                )
            )
        for line in voucher.lines:
            if line.amount_fc is None or line.rate_used is None:
                continue
            expected = round(line.amount_fc * line.rate_used)
            if abs(expected - line.amount_krw) > tolerance:
                mismatches.append(
                    SourceTaggedMessage(
                        message=f"{voucher.voucher_id} 전표의 {line.account_code} 라인은 환산금액이 맞지 않습니다.",
                        source_tags=["voucher", "exchange_rate"],
                        source_refs=[f"voucher:{voucher.voucher_id}:{line.account_code}"],
                    )
                )

    policy_consistent = True
    gain_account = mapping_by_purpose.get("FX_GAIN")
    loss_account = mapping_by_purpose.get("FX_LOSS")
    flat_codes = {line.account_code for voucher in vouchers for line in voucher.lines}
    if fx_result.status == "completed" and fx_result.realized_gain_loss_krw:
        if fx_result.realized_gain_loss_krw > 0 and gain_account and gain_account not in flat_codes:
            policy_consistent = False
            mismatches.append(
                SourceTaggedMessage(
                    message="환차익 계정이 전표에 반영되지 않았습니다.",
                    source_tags=["account_mapping", "voucher"],
                    source_refs=[f"account_mapping:{gain_account}"],
                )
            )
        if fx_result.realized_gain_loss_krw < 0 and loss_account and loss_account not in flat_codes:
            policy_consistent = False
            mismatches.append(
                SourceTaggedMessage(
                    message="환차손 계정이 전표에 반영되지 않았습니다.",
                    source_tags=["account_mapping", "voucher"],
                    source_refs=[f"account_mapping:{loss_account}"],
                )
            )

    basis = []
    if policy is not None:
        basis.append(f"policy {policy.policy_id} / {policy.fx_cost_method}")
    if gain_account:
        basis.append(f"FX_GAIN -> {gain_account}")
    if loss_account:
        basis.append(f"FX_LOSS -> {loss_account}")

    return VoucherReviewResult(
        status="completed",
        balance_ok=balance_ok,
        review_points=review_points,
        mismatches=mismatches,
        basis=basis,
        policy_consistent=policy_consistent,
    )
