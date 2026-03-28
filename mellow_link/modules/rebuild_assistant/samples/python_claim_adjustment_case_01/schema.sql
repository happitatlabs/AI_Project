CREATE TABLE insurance_claim (
    claim_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    branch_code TEXT NOT NULL,
    status TEXT NOT NULL,
    claim_amount INTEGER NOT NULL,
    is_urgent TEXT NOT NULL DEFAULT 'N',
    accident_type TEXT NOT NULL,
    deleted_flag TEXT NOT NULL DEFAULT 'N',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE claim_adjustment_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL,
    adjusted_by TEXT NOT NULL,
    approval_role TEXT NOT NULL,
    adjustment_amount INTEGER NOT NULL,
    adjustment_reason TEXT,
    created_at TEXT NOT NULL
);
