SELECT
    c.claim_id,
    c.status,
    c.claim_amount,
    c.branch_code,
    c.is_urgent,
    c.accident_type
FROM insurance_claim c
WHERE c.claim_id = :claim_id
  AND c.deleted_flag = 'N'
  AND (
        c.status IN ('REVIEW', 'ESCALATED')
        OR (c.is_urgent = 'Y' AND c.status = 'PENDING')
      )
  AND (
        :user_role = 'HQ_REVIEWER'
        OR (:user_role = 'BRANCH_MANAGER' AND c.claim_amount < 3000000)
      );
