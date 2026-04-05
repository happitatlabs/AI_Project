from __future__ import annotations

from .schemas import AccountingInputBundle, AccountingInputValidation


def validate_accounting_input(
    bundle: AccountingInputBundle | None,
    *,
    parse_error: str = "",
) -> AccountingInputValidation:
    if parse_error:
        return AccountingInputValidation(
            status="failed",
            strict=True,
            failure_reason=parse_error,
        )

    if bundle is None:
        return AccountingInputValidation(
            status="failed",
            strict=True,
            failure_reason="accounting payload not available",
        )

    missing_required_inputs: list[str] = []
    warnings: list[str] = []
    if not bundle.transactions:
        missing_required_inputs.append("transactions")
    if not bundle.exchange_rates:
        missing_required_inputs.append("exchange_rates")
    if not bundle.policies:
        missing_required_inputs.append("policies")
    if not bundle.vouchers:
        warnings.append("voucher_review를 수행할 vouchers 입력이 없습니다.")
    if not bundle.account_mappings:
        warnings.append("voucher_review를 수행할 account_mappings 입력이 없습니다.")

    status = "passed"
    failure_reason = ""
    if missing_required_inputs:
        status = "failed"
        failure_reason = f"missing required inputs: {', '.join(missing_required_inputs)}"
    elif warnings:
        status = "warning"

    return AccountingInputValidation(
        status=status,
        strict=bundle.strict,
        missing_required_inputs=missing_required_inputs,
        warnings=warnings,
        failure_reason=failure_reason,
    )
