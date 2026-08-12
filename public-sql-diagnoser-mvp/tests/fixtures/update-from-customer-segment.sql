UPDATE sales.orders o
SET customer_segment = c.segment
FROM crm.customers c
WHERE o.customer_id = c.customer_id
  AND o.order_date >= DATE '2026-01-01';
