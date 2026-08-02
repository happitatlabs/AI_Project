CREATE VIEW sales_dashboard AS
SELECT
  o.order_id,
  o.order_date,
  o.total_amount,
  c.customer_id,
  c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID';
