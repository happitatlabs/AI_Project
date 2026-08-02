SELECT
  c.customer_id,
  c.customer_name
FROM customers c
WHERE EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
    AND o.status = 'PAID'
);
