SELECT
  p.product_id,
  p.product_name,
  COUNT(DISTINCT oi.order_id) AS order_count,
  SUM(oi.quantity) AS sold_quantity,
  SUM(oi.quantity * oi.unit_price) AS total_sales_amount
FROM order_items oi
JOIN products p
  ON p.product_id = oi.product_id
WHERE oi.order_date >= DATE '2026-01-01'
GROUP BY
  p.product_id,
  p.product_name
ORDER BY total_sales_amount DESC;
