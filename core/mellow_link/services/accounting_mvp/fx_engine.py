from __future__ import annotations

from collections import defaultdict

from .normalizer import normalize_transactions
from .schemas import (
    AccountingPolicy,
    AccountingTransaction,
    ExchangeRateRecord,
    FxCalculationResult,
    FxCalculationStep,
)


_INCOMING_TYPES = {"BUY_FX", "RECEIVE"}
_OUTGOING_TYPES = {"SELL_FX", "PAY"}


def calculate_fx(
    transactions: list[AccountingTransaction],
    exchange_rates: list[ExchangeRateRecord],
    *,
    policy: AccountingPolicy | None,
    strict: bool,
) -> FxCalculationResult:
    if policy is None:
        return FxCalculationResult(status="failed", failure_reason="policy selection failed")

    normalized = normalize_transactions(transactions)
    if policy.fx_cost_method == "MOVING_AVERAGE":
        return _calculate_moving_average(normalized, exchange_rates, policy, strict)
    if policy.fx_cost_method == "FIFO":
        return _calculate_fifo(normalized, exchange_rates, policy, strict)
    return _calculate_specific_id(normalized, exchange_rates, policy, strict)


def _calculate_moving_average(
    transactions: list[AccountingTransaction],
    exchange_rates: list[ExchangeRateRecord],
    policy: AccountingPolicy,
    strict: bool,
) -> FxCalculationResult:
    steps: list[FxCalculationStep] = []
    warnings: list[str] = []
    applied_rates: list[dict] = []
    state: dict[str, dict[str, float]] = defaultdict(lambda: {"qty": 0.0, "cost": 0.0})
    realized_total = 0

    for tx in transactions:
        rate_value, rate_tags, rate_refs, rate_warning, rate_error = _resolve_rate(tx, exchange_rates, strict=strict)
        if rate_warning:
            warnings.append(rate_warning)
        if rate_error:
            return FxCalculationResult(
                status="failed",
                method=policy.fx_cost_method,
                detail_steps=steps,
                applied_rates=applied_rates,
                warnings=_dedupe(warnings),
                failure_reason=rate_error,
            )

        group_key = f"{tx.currency}:{tx.fx_account_id}"
        amount_krw = int(round(tx.amount_krw if tx.amount_krw is not None else tx.amount_fc * rate_value))
        applied_rates.append({"tx_id": tx.tx_id, "currency": tx.currency, "rate": rate_value, "source_tags": rate_tags, "source_refs": rate_refs})

        if tx.tx_type in _INCOMING_TYPES:
            state[group_key]["qty"] += tx.amount_fc
            state[group_key]["cost"] += amount_krw
            avg_rate = state[group_key]["cost"] / state[group_key]["qty"] if state[group_key]["qty"] else 0.0
            steps.append(
                FxCalculationStep(
                    message=f"{tx.tx_id} 거래를 평균단가 재고에 반영했습니다.",
                    formula="new_avg = cumulative_cost / cumulative_qty",
                    inputs={"amount_fc": tx.amount_fc, "amount_krw": amount_krw, "rate": rate_value},
                    output={"cumulative_qty": state[group_key]["qty"], "cumulative_cost": int(round(state[group_key]["cost"])), "average_rate": round(avg_rate, 4)},
                    source_tags=["transaction", *rate_tags],
                    source_refs=[f"transaction:{tx.tx_id}", *rate_refs],
                )
            )
            continue

        if tx.tx_type not in _OUTGOING_TYPES:
            warnings.append(f"지원하지 않는 거래 유형을 건너뛰었습니다: {tx.tx_type}")
            continue

        if state[group_key]["qty"] < tx.amount_fc:
            return FxCalculationResult(
                status="failed",
                method=policy.fx_cost_method,
                detail_steps=steps,
                applied_rates=applied_rates,
                warnings=_dedupe(warnings),
                failure_reason=f"insufficient foreign currency balance for {tx.tx_id}",
            )

        carrying_rate = state[group_key]["cost"] / state[group_key]["qty"] if state[group_key]["qty"] else 0.0
        carrying_cost = int(round(tx.amount_fc * carrying_rate))
        realized_total += amount_krw - carrying_cost
        state[group_key]["qty"] -= tx.amount_fc
        state[group_key]["cost"] -= carrying_cost
        steps.append(
            FxCalculationStep(
                message=f"{tx.tx_id} 거래의 환차손익을 계산했습니다.",
                formula="realized = settlement_krw - carrying_cost",
                inputs={"amount_fc": tx.amount_fc, "settlement_krw": amount_krw, "carrying_rate": round(carrying_rate, 4)},
                output={"carrying_cost": carrying_cost, "realized_gain_loss_krw": amount_krw - carrying_cost},
                source_tags=["transaction", *rate_tags],
                source_refs=[f"transaction:{tx.tx_id}", *rate_refs],
            )
        )

    return FxCalculationResult(
        status="completed",
        method=policy.fx_cost_method,
        realized_gain_loss_krw=int(realized_total),
        detail_steps=steps,
        applied_rates=applied_rates,
        source_summary=_build_source_summary(applied_rates),
        warnings=_dedupe(warnings),
    )


def _calculate_fifo(
    transactions: list[AccountingTransaction],
    exchange_rates: list[ExchangeRateRecord],
    policy: AccountingPolicy,
    strict: bool,
) -> FxCalculationResult:
    steps: list[FxCalculationStep] = []
    warnings: list[str] = []
    applied_rates: list[dict] = []
    lots: dict[str, list[dict[str, float | str]]] = defaultdict(list)
    realized_total = 0

    for tx in transactions:
        rate_value, rate_tags, rate_refs, rate_warning, rate_error = _resolve_rate(tx, exchange_rates, strict=strict)
        if rate_warning:
            warnings.append(rate_warning)
        if rate_error:
            return FxCalculationResult(
                status="failed",
                method=policy.fx_cost_method,
                detail_steps=steps,
                applied_rates=applied_rates,
                warnings=_dedupe(warnings),
                failure_reason=rate_error,
            )

        group_key = f"{tx.currency}:{tx.fx_account_id}"
        amount_krw = int(round(tx.amount_krw if tx.amount_krw is not None else tx.amount_fc * rate_value))
        applied_rates.append({"tx_id": tx.tx_id, "currency": tx.currency, "rate": rate_value, "source_tags": rate_tags, "source_refs": rate_refs})

        if tx.tx_type in _INCOMING_TYPES:
            lots[group_key].append({"lot_id": tx.tx_id, "remaining_fc": tx.amount_fc, "unit_cost": amount_krw / tx.amount_fc if tx.amount_fc else 0.0})
            steps.append(
                FxCalculationStep(
                    message=f"{tx.tx_id} 거래를 FIFO lot로 적재했습니다.",
                    formula="unit_cost = amount_krw / amount_fc",
                    inputs={"amount_fc": tx.amount_fc, "amount_krw": amount_krw},
                    output={"lot_id": tx.tx_id, "unit_cost": round(amount_krw / tx.amount_fc if tx.amount_fc else 0.0, 4)},
                    source_tags=["transaction", *rate_tags],
                    source_refs=[f"transaction:{tx.tx_id}", *rate_refs],
                )
            )
            continue

        if tx.tx_type not in _OUTGOING_TYPES:
            warnings.append(f"지원하지 않는 거래 유형을 건너뛰었습니다: {tx.tx_type}")
            continue

        remaining = tx.amount_fc
        carrying_cost = 0
        while remaining > 0:
            if not lots[group_key]:
                return FxCalculationResult(
                    status="failed",
                    method=policy.fx_cost_method,
                    detail_steps=steps,
                    applied_rates=applied_rates,
                    warnings=_dedupe(warnings),
                    failure_reason=f"insufficient FIFO lots for {tx.tx_id}",
                )
            current = lots[group_key][0]
            consume = min(remaining, float(current["remaining_fc"]))
            carrying_cost += int(round(consume * float(current["unit_cost"])))
            current["remaining_fc"] = float(current["remaining_fc"]) - consume
            remaining -= consume
            if float(current["remaining_fc"]) <= 0:
                lots[group_key].pop(0)
        realized = amount_krw - carrying_cost
        realized_total += realized
        steps.append(
            FxCalculationStep(
                message=f"{tx.tx_id} 거래를 FIFO 기준으로 평가했습니다.",
                formula="realized = settlement_krw - fifo_carrying_cost",
                inputs={"amount_fc": tx.amount_fc, "settlement_krw": amount_krw},
                output={"carrying_cost": carrying_cost, "realized_gain_loss_krw": realized},
                source_tags=["transaction", *rate_tags],
                source_refs=[f"transaction:{tx.tx_id}", *rate_refs],
            )
        )

    return FxCalculationResult(
        status="completed",
        method=policy.fx_cost_method,
        realized_gain_loss_krw=int(realized_total),
        detail_steps=steps,
        applied_rates=applied_rates,
        source_summary=_build_source_summary(applied_rates),
        warnings=_dedupe(warnings),
    )


def _calculate_specific_id(
    transactions: list[AccountingTransaction],
    exchange_rates: list[ExchangeRateRecord],
    policy: AccountingPolicy,
    strict: bool,
) -> FxCalculationResult:
    if any(tx.tx_type in _OUTGOING_TYPES and not tx.source_lot_ids for tx in transactions):
        return FxCalculationResult(
            status="failed",
            method=policy.fx_cost_method,
            failure_reason="SPECIFIC_ID requires source_lot_ids for outgoing transactions",
            warnings=["lot/source 지정이 없어 SPECIFIC_ID 계산을 수행할 수 없습니다."],
        )
    fifo_result = _calculate_fifo(transactions, exchange_rates, policy, strict)
    if fifo_result.status == "completed":
        fifo_result.warnings.append("SPECIFIC_ID는 source_lot_ids를 요구하지만 현재 MVP에서는 지정 lot를 순차 lot로 확인합니다.")
    return fifo_result


def _resolve_rate(
    tx: AccountingTransaction,
    exchange_rates: list[ExchangeRateRecord],
    *,
    strict: bool,
) -> tuple[float, list[str], list[str], str, str]:
    if tx.rate is not None:
        return float(tx.rate), ["transaction"], [f"transaction:{tx.tx_id}:rate"], "", ""

    tx_date = (tx.occurred_at or "")[:10]
    exact = [item for item in exchange_rates if item.currency == tx.currency and item.rate_date == tx_date]
    if len(exact) == 1:
        rate = float(exact[0].rate)
        return rate, ["exchange_rate"], [f"exchange_rate:{tx.currency}:{tx_date}"], "", ""
    if len(exact) > 1:
        if strict:
            return 0.0, [], [], "", f"ambiguous exchange rate for {tx.tx_id}"
        selected = sorted(exact, key=lambda item: (item.rate_type, item.rate))[0]
        return float(selected.rate), ["exchange_rate", "inferred"], [f"exchange_rate:{tx.currency}:{tx_date}"], "복수 환율이 있어 첫 번째 환율을 사용했습니다.", ""

    prior = sorted(
        [item for item in exchange_rates if item.currency == tx.currency and item.rate_date <= tx_date],
        key=lambda item: item.rate_date,
        reverse=True,
    )
    if prior:
        if strict:
            return 0.0, [], [], "", f"missing exact exchange rate for {tx.tx_id}"
        selected = prior[0]
        return float(selected.rate), ["exchange_rate", "inferred"], [f"exchange_rate:{tx.currency}:{selected.rate_date}"], "정확한 거래일 환율이 없어 직전 환율을 사용했습니다.", ""
    return 0.0, [], [], "", f"missing exchange rate for {tx.tx_id}"


def _build_source_summary(applied_rates: list[dict]) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for item in applied_rates:
        for tag in item.get("source_tags") or []:
            counts[str(tag)] += 1
    return [f"{tag} source used {count}회" for tag, count in sorted(counts.items())]


def _dedupe(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output
