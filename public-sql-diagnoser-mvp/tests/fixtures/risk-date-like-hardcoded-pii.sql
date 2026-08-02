SELECT
  o.order_id,
  c.customer_name,
  c.email
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE TO_CHAR(o.order_date, 'YYYYMM') = '202607'
  AND c.customer_name LIKE '%kim%'
  AND o.status IN ('PAID', 'SHIPPED', 'COMPLETED', 'CANCELLED', 'REFUNDED')
  AND c.email = 'customer@example.com';
