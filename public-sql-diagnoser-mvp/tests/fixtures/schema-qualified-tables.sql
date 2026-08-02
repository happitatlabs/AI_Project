SELECT
  o.order_id,
  c.customer_name,
  o.total_amount
FROM public.orders o
JOIN crm.customers c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID';
