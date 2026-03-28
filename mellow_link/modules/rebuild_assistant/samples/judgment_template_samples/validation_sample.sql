SELECT COUNT(*)
FROM claim_adjustments
WHERE claim_id = ?
  AND status = 'PENDING';