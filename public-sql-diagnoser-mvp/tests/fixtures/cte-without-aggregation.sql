WITH active_customers AS (
  SELECT
    c.customer_id,
    c.customer_name,
    c.grade
  FROM customers c
  WHERE c.use_yn = 'Y'
),
recent_orders AS (
  SELECT
    o.order_id,
    o.customer_id,
    o.order_date,
    o.status
  FROM orders o
  JOIN active_customers ac
    ON ac.customer_id = o.customer_id
  WHERE o.order_date >= DATE '2026-01-01'
)
SELECT
  ro.order_id,
  ac.customer_name,
  ac.grade,
  ro.order_date,
  ro.status
FROM recent_orders ro
JOIN active_customers ac
  ON ac.customer_id = ro.customer_id
WHERE ro.status = 'PAID';
