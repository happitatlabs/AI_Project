SELECT
  order_id,
  customer_id
FROM orders
WHERE status = 'SHIPPED'
  AND order_date >= DATE '2026-02-01';
