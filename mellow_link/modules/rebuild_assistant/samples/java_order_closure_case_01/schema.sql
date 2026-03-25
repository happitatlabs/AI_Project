CREATE TABLE sales_order (
    order_id VARCHAR(30) PRIMARY KEY,
    customer_id VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL,
    order_amount INTEGER NOT NULL,
    channel_code VARCHAR(20) NOT NULL,
    customer_grade VARCHAR(20) NOT NULL,
    delivery_hold_flag CHAR(1) NOT NULL DEFAULT 'N',
    order_type VARCHAR(20) NOT NULL,
    deleted_flag CHAR(1) NOT NULL DEFAULT 'N',
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE order_close_history (
    history_id BIGINT PRIMARY KEY,
    order_id VARCHAR(30) NOT NULL,
    closed_by VARCHAR(30) NOT NULL,
    close_result VARCHAR(50) NOT NULL,
    close_reason VARCHAR(255),
    created_at TIMESTAMP NOT NULL
);
