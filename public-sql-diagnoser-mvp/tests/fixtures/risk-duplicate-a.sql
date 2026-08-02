SELECT
  order_id,
  customer_id
FROM orders
WHERE status = 'PAID'
  AND order_date >= DATE '2026-01-01';
