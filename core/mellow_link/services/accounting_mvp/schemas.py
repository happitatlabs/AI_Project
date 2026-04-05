from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


AccountingMethod = Literal["MOVING_AVERAGE", "FIFO", "SPECIFIC_ID"]
SourceTag = Literal["policy", "transaction", "exchange_rate", "account_mapping", "voucher", "inferred"]


class AccountingTransaction(BaseModel):
    tx_id: str
    tx_type: str
    occurred_at: str
    currency: str
    amount_fc: float
    rate: float | None = None
    amount_krw: float | None = None
    fx_account_id: str = "DEFAULT"
    source_lot_ids: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("tx_id", "occurred_at", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("tx_type", mode="before")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return (value or "").strip().upper()

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return (value or "").strip().upper()


class VoucherLine(BaseModel):
    account_code: str
    side: Literal["debit", "credit"]
    amount_krw: float
    amount_fc: float | None = None
    currency: str = ""
    rate_used: float | None = None
    source_tx_ids: list[str] = Field(default_factory=list)

    @field_validator("account_code", mode="before")
    @classmethod
    def strip_account_code(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return (value or "").strip().upper()


class AccountingVoucher(BaseModel):
    voucher_id: str
    occurred_at: str = ""
    description: str = ""
    lines: list[VoucherLine] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if value.get("lines"):
            return value
        debit = value.get("debit")
        credit = value.get("credit")
        if debit is None and credit is None:
            return value

        source_tx_ids = list(value.get("source_tx_ids") or [])
        normalized = dict(value)
        lines: list[dict[str, Any]] = []
        if debit is not None:
            lines.append(
                {
                    "account_code": str(value.get("debit_account_code") or "AUTO_DEBIT"),
                    "side": "debit",
                    "amount_krw": debit,
                    "source_tx_ids": source_tx_ids,
                }
            )
        if credit is not None:
            lines.append(
                {
                    "account_code": str(value.get("credit_account_code") or "AUTO_CREDIT"),
                    "side": "credit",
                    "amount_krw": credit,
                    "source_tx_ids": source_tx_ids,
                }
            )
        normalized["lines"] = lines
        return normalized

    @field_validator("voucher_id", "occurred_at", "description", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return (value or "").strip()


class ExchangeRateRecord(BaseModel):
    currency: str
    rate_date: str
    rate: float
    rate_type: str = "spot"

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return (value or "").strip().upper()

    @field_validator("rate_date", "rate_type", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return (value or "").strip()


class AccountMapping(BaseModel):
    purpose: str
    account_code: str
    description: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if not normalized.get("purpose"):
            legacy_type = str(normalized.get("type") or "").strip().upper()
            type_mapping = {
                "GAIN": "FX_GAIN",
                "LOSS": "FX_LOSS",
            }
            normalized["purpose"] = type_mapping.get(legacy_type, legacy_type or "GENERAL")
        if not normalized.get("account_code"):
            normalized["account_code"] = normalized.get("account") or ""
        return normalized

    @field_validator("purpose", mode="before")
    @classmethod
    def normalize_purpose(cls, value: str) -> str:
        return (value or "").strip().upper()

    @field_validator("account_code", "description", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return (value or "").strip()


class AccountingPolicy(BaseModel):
    policy_id: str = "default"
    fx_cost_method: AccountingMethod = "MOVING_AVERAGE"
    effective_from: str = ""
    effective_to: str = ""
    version: int = 1
    tolerance_krw: float = 1.0

    @field_validator("policy_id", "effective_from", "effective_to", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("fx_cost_method", mode="before")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if normalized not in {"MOVING_AVERAGE", "FIFO", "SPECIFIC_ID"}:
            raise ValueError("unsupported fx_cost_method")
        return normalized


class AccountingInputBundle(BaseModel):
    transactions: list[AccountingTransaction] = Field(default_factory=list)
    vouchers: list[AccountingVoucher] = Field(default_factory=list)
    exchange_rates: list[ExchangeRateRecord] = Field(default_factory=list)
    account_mappings: list[AccountMapping] = Field(default_factory=list)
    policies: list[AccountingPolicy] = Field(default_factory=list)
    strict: bool = True


class SourceTaggedMessage(BaseModel):
    message: str
    source_tags: list[SourceTag] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class FxCalculationStep(BaseModel):
    message: str
    formula: str = ""
    inputs: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    source_tags: list[SourceTag] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class AccountingInputValidation(BaseModel):
    status: Literal["passed", "warning", "failed"] = "passed"
    strict: bool = True
    missing_required_inputs: list[str] = Field(default_factory=list)
    ambiguous_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failure_reason: str = ""


class CalculationStatus(BaseModel):
    can_calculate: bool = False
    reason: str = ""
    blocking_issue: str = ""


class AccountingAnalysisResult(BaseModel):
    candidate_methods: list[AccountingMethod] = Field(default_factory=list)
    recommended_method: AccountingMethod | str = ""
    reasons: list[SourceTaggedMessage] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class FxCalculationResult(BaseModel):
    status: Literal["completed", "failed", "skipped"] = "skipped"
    method: AccountingMethod | str = ""
    realized_gain_loss_krw: int | None = None
    detail_steps: list[FxCalculationStep] = Field(default_factory=list)
    applied_rates: list[dict[str, Any]] = Field(default_factory=list)
    source_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failure_reason: str = ""


class VoucherReviewResult(BaseModel):
    status: Literal["completed", "failed", "skipped", "input_missing"] = "skipped"
    balance_ok: bool | None = None
    review_points: list[SourceTaggedMessage] = Field(default_factory=list)
    mismatches: list[SourceTaggedMessage] = Field(default_factory=list)
    basis: list[str] = Field(default_factory=list)
    policy_consistent: bool | None = None
    warnings: list[str] = Field(default_factory=list)
    failure_reason: str = ""


class AccountingExtension(BaseModel):
    input_validation: AccountingInputValidation = Field(default_factory=AccountingInputValidation)
    calculation_status: CalculationStatus = Field(default_factory=CalculationStatus)
    accounting_analysis: AccountingAnalysisResult = Field(default_factory=AccountingAnalysisResult)
    fx_calculation: FxCalculationResult = Field(default_factory=FxCalculationResult)
    voucher_review: VoucherReviewResult = Field(default_factory=VoucherReviewResult)
    summary_sentence: str = ""
