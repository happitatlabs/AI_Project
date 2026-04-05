SELECT request_id, title, category, requester_id, hidden_flag
FROM requests
WHERE (:category IS NULL OR category = :category)
  AND (:keyword IS NULL OR title LIKE CONCAT('%', :keyword, '%'))
  AND (:requester_id IS NULL OR requester_id = :requester_id)
  AND hidden_flag = 'N'
ORDER BY request_date DESC;

SELECT request_id, title, category, requester_id, hidden_flag
FROM archived_requests
WHERE (:category IS NULL OR category = :category)
  AND (:keyword IS NULL OR title LIKE CONCAT('%', :keyword, '%'))
  AND (:requester_id IS NULL OR requester_id = :requester_id)
  AND hidden_flag = 'N'
ORDER BY request_date DESC;
