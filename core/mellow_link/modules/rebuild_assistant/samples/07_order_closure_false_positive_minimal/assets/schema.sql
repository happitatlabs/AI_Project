CREATE TABLE review_queue_item (
    item_id VARCHAR(40) PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    reviewer_id VARCHAR(40) NOT NULL,
    review_required BOOLEAN NOT NULL DEFAULT TRUE,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL
);
