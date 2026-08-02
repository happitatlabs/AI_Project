SELECT
  c.customer_id,
  c.customer_name,
  (
    SELECT COUNT(*)
    FROM orders o
    WHERE o.customer_id = c.customer_id
  ) AS order_count
FROM customers c
WHERE c.use_yn = 'Y';
