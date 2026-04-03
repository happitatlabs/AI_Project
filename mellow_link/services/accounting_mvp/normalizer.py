from __future__ import annotations

from .schemas import AccountingTransaction


def normalize_transactions(transactions: list[AccountingTransaction]) -> list[AccountingTransaction]:
    normalized: list[AccountingTransaction] = []
    for item in transactions:
        normalized.append(
            item.model_copy(
                update={
                    "tx_type": item.tx_type.upper(),
                    "currency": item.currency.upper(),
                    "fx_account_id": (item.fx_account_id or "DEFAULT").strip() or "DEFAULT",
                    "occurred_at": (item.occurred_at or "").strip(),
                }
            )
        )
    return sorted(normalized, key=lambda value: (value.occurred_at, value.tx_id))
