from __future__ import annotations

from .schemas import AccountingPolicy


def select_active_policy(
    policies: list[AccountingPolicy],
    *,
    tx_dates: list[str],
    strict: bool,
) -> tuple[AccountingPolicy | None, list[str], list[str]]:
    warnings: list[str] = []
    ambiguous_inputs: list[str] = []
    if not policies:
        return None, warnings, ambiguous_inputs
    if len(policies) == 1:
        return policies[0], warnings, ambiguous_inputs

    date_min = min((item or "") for item in tx_dates if item) if tx_dates else ""
    date_max = max((item or "") for item in tx_dates if item) if tx_dates else ""

    def covers(policy: AccountingPolicy) -> bool:
        lower_ok = not policy.effective_from or not date_min or policy.effective_from <= date_min
        upper_ok = not policy.effective_to or not date_max or policy.effective_to >= date_max
        return lower_ok and upper_ok

    active = [policy for policy in policies if covers(policy)]
    if len(active) == 1:
        return active[0], warnings, ambiguous_inputs
    if len(active) > 1:
        ambiguous_inputs.append("multiple active policies matched transaction dates")
        if strict:
            return None, warnings, ambiguous_inputs
        selected = sorted(active, key=lambda item: (item.version, item.effective_from), reverse=True)[0]
        warnings.append(f"복수 정책이 일치해 version {selected.version} 정책을 선택했습니다.")
        return selected, warnings, ambiguous_inputs

    ambiguous_inputs.append("no active policy covers transaction dates")
    if strict:
        return None, warnings, ambiguous_inputs
    selected = sorted(policies, key=lambda item: (item.version, item.effective_from), reverse=True)[0]
    warnings.append(f"유효기간이 맞는 정책이 없어 version {selected.version} 정책을 사용했습니다.")
    return selected, warnings, ambiguous_inputs
