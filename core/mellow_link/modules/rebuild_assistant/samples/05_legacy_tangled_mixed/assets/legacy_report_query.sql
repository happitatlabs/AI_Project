SELECT COUNT(*)
FROM claim_adjustments
WHERE claim_id = :claim_id
  AND status = 'PENDING';

UPDATE reports
SET status = 'COMPLETED'
WHERE report_id = :report_id
  AND status IN ('PAID', 'READY')
  AND delivery_hold_flag = 'N';

SELECT report_id, title, status, requester_id
FROM reports
WHERE (:status IS NULL OR status = :status)
  AND (:keyword IS NULL OR title LIKE CONCAT('%', :keyword, '%'))
  AND deleted_flag = 'N';
