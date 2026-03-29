-- SQL Amount Limit Example
SELECT
  order_id,
  order_amount,
  CASE
    WHEN order_amount <= 50000 THEN 'SMALL'
    WHEN order_amount > 50000 AND order_amount <= 300000 THEN 'MEDIUM'
    WHEN order_amount > 300000 THEN 'LARGE'
  END AS amount_grade
FROM purchase_order
WHERE order_amount > 0
  AND order_amount <= limit_amount;
