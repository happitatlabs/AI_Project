SELECT customer_id, jan_sales, feb_sales, mar_sales
FROM (
  SELECT customer_id, EXTRACT(MONTH FROM order_date) AS month_no, total_amount
  FROM sales.orders
) source_data
PIVOT (
  SUM(total_amount) FOR month_no IN (1 AS jan_sales, 2 AS feb_sales, 3 AS mar_sales)
);
