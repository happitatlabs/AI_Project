SELECT *
FROM claims
WHERE amount >= 10000000
  AND dept_code = 'CLAIM_AUDIT';