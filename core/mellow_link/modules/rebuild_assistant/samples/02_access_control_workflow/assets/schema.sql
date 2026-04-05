CREATE TABLE claims (
    claim_id BIGINT PRIMARY KEY,
    amount DECIMAL(18,2) NOT NULL,
    dept_code VARCHAR(30) NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE claim_approvals (
    approval_id BIGINT PRIMARY KEY,
    claim_id BIGINT NOT NULL,
    actor_role VARCHAR(30) NOT NULL,
    action VARCHAR(30) NOT NULL
);
