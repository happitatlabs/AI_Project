-- repository schema for orders state transitions
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    state VARCHAR(30) NOT NULL
);
