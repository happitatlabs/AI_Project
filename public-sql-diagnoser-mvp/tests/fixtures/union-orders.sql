SELECT
  o.order_id,
  o.customer_id,
  'ONLINE' AS order_channel
FROM online_orders o
WHERE o.status = 'PAID'
UNION ALL
SELECT
  s.order_id,
  s.customer_id,
  'STORE' AS order_channel
FROM store_orders s
WHERE s.status = 'PAID';
