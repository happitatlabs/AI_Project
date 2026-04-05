SELECT report_id, title, owner_name, created_at
FROM reports
WHERE (:keyword IS NULL OR title LIKE CONCAT('%', :keyword, '%'))
ORDER BY created_at DESC;

SELECT report_id, title, owner_name, created_at
FROM reports
WHERE report_id = :report_id;

INSERT INTO reports (title, owner_name, created_at)
VALUES (:title, :owner_name, CURRENT_TIMESTAMP);

UPDATE reports
SET title = :title,
    owner_name = :owner_name
WHERE report_id = :report_id;

DELETE FROM reports
WHERE report_id = :report_id;
