SELECT
  c.customer_id,
  c.customer_name,
  SUM(o.total_amount) AS total_sales
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY
  c.customer_id,
  c.customer_name
HAVING SUM(o.total_amount) >= 1000000;
