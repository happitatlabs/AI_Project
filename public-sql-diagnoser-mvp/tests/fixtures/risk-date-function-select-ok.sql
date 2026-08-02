SELECT
  DATE_TRUNC('month', order_date) AS order_month,
  COUNT(*) AS order_count
FROM orders
WHERE order_date >= DATE '2026-01-01'
GROUP BY DATE_TRUNC('month', order_date);
