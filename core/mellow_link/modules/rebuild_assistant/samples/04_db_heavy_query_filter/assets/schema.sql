CREATE TABLE requests (
    request_id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    category VARCHAR(30) NOT NULL,
    requester_id VARCHAR(40) NOT NULL,
    hidden_flag CHAR(1) NOT NULL,
    request_date DATE NOT NULL
);

CREATE TABLE archived_requests (
    request_id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    category VARCHAR(30) NOT NULL,
    requester_id VARCHAR(40) NOT NULL,
    hidden_flag CHAR(1) NOT NULL,
    request_date DATE NOT NULL
);
