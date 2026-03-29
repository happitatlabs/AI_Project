-- SQL Query Filter Example
SELECT request_id, title, status, requester_id, request_date
FROM service_request
WHERE deleted_flag = 'N'
  AND status IN ('REQUESTED', 'IN_REVIEW')
  AND request_date BETWEEN :startDate AND :endDate
  AND (
    requester_id = :loginUserId
    OR dept_id = :loginDeptId
  )
  AND title LIKE CONCAT('%', :keyword, '%');
