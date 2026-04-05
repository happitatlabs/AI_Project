SELECT claim_id, amount, dept_code, status
FROM claims
WHERE amount >= 10000000
  AND dept_code = 'CLAIM_AUDIT';

UPDATE claims
SET status = :next_status
WHERE claim_id = :claim_id
  AND status = :current_status;
