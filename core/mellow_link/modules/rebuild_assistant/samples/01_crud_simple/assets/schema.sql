CREATE TABLE reports (
    report_id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    owner_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
