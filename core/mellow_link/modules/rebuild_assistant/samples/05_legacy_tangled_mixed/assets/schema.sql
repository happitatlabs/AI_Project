CREATE TABLE reports (
    report_id BIGINT PRIMARY KEY,
    claim_id BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL,
    amount DECIMAL(18,2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    requester_id VARCHAR(40),
    deleted_flag CHAR(1) NOT NULL,
    delivery_hold_flag CHAR(1) NOT NULL
);

CREATE TABLE claim_adjustments (
    adjustment_id BIGINT PRIMARY KEY,
    claim_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL
);
