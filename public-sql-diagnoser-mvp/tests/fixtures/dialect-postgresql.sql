SELECT DISTINCT ON (customer_id)
  customer_id,
  order_id,
  metadata->>'tier' AS customer_tier
FROM sales.orders
WHERE metadata::jsonb ? 'tier'
ORDER BY customer_id, order_date DESC;
