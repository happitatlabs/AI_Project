SELECT
  o.order_id,
  c.customer_name
FROM orders o, customers c
WHERE o.customer_id = c.customer_id
  AND o.status = 'PAID';
