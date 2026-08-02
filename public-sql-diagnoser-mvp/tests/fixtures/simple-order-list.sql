SELECT
  o.order_id,
  o.order_date,
  o.status,
  o.total_amount,
  c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
  AND o.order_date >= DATE '2026-01-01'
ORDER BY o.order_date DESC;
