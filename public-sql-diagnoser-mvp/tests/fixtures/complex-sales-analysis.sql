WITH recent_orders AS (
  SELECT
    o.order_id,
    o.customer_id,
    o.order_date,
    o.status,
    o.total_amount,
    c.grade AS customer_grade,
    c.joined_at,
    r.region_name,
    DATE_TRUNC('month', o.order_date) AS order_month
  FROM orders o
  JOIN customers c
    ON c.customer_id = o.customer_id
  LEFT JOIN regions r
    ON r.region_id = c.region_id
  WHERE o.order_date >= CURRENT_DATE - INTERVAL '12 months'
    AND o.status IN ('PAID', 'SHIPPED', 'COMPLETED')
),

order_items_summary AS (
  SELECT
    oi.order_id,
    COUNT(*) AS item_count,
    SUM(oi.quantity) AS total_quantity,
    SUM(oi.quantity * oi.unit_price) AS item_gross_amount,
    SUM(oi.quantity * oi.unit_price * COALESCE(oi.discount_rate, 0)) AS discount_amount
  FROM order_items oi
  GROUP BY oi.order_id
),

customer_monthly_sales AS (
  SELECT
    ro.customer_id,
    ro.customer_grade,
    ro.region_name,
    ro.order_month,
    COUNT(DISTINCT ro.order_id) AS order_count,
    SUM(ro.total_amount) AS monthly_sales,
    SUM(ois.item_count) AS item_count,
    SUM(ois.total_quantity) AS total_quantity,
    SUM(ois.discount_amount) AS discount_amount
  FROM recent_orders ro
  JOIN order_items_summary ois
    ON ois.order_id = ro.order_id
  GROUP BY
    ro.customer_id,
    ro.customer_grade,
    ro.region_name,
    ro.order_month
),

ranked_customers AS (
  SELECT
    cms.*,
    SUM(cms.monthly_sales) OVER (
      PARTITION BY cms.customer_id
      ORDER BY cms.order_month
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_sales,

    AVG(cms.monthly_sales) OVER (
      PARTITION BY cms.customer_id
      ORDER BY cms.order_month
      ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg_3m_sales,

    LAG(cms.monthly_sales) OVER (
      PARTITION BY cms.customer_id
      ORDER BY cms.order_month
    ) AS prev_month_sales,

    RANK() OVER (
      PARTITION BY cms.order_month
      ORDER BY cms.monthly_sales DESC
    ) AS monthly_sales_rank
  FROM customer_monthly_sales cms
)

SELECT
  rc.order_month,
  rc.customer_id,
  rc.customer_grade,
  COALESCE(rc.region_name, 'UNKNOWN') AS region_name,
  rc.order_count,
  rc.monthly_sales,
  rc.prev_month_sales,

  CASE
    WHEN rc.prev_month_sales IS NULL THEN NULL
    WHEN rc.prev_month_sales = 0 THEN NULL
    ELSE ROUND(
      ((rc.monthly_sales - rc.prev_month_sales) / rc.prev_month_sales) * 100,
      2
    )
  END AS sales_growth_rate_percent,

  rc.moving_avg_3m_sales,
  rc.cumulative_sales,
  rc.item_count,
  rc.total_quantity,
  rc.discount_amount,
  rc.monthly_sales_rank,

  CASE
    WHEN rc.monthly_sales_rank <= 10 THEN 'TOP_10'
    WHEN rc.monthly_sales >= 1000000 THEN 'HIGH_VALUE'
    WHEN rc.order_count >= 3 THEN 'REPEAT_BUYER'
    ELSE 'NORMAL'
  END AS customer_segment

FROM ranked_customers rc
WHERE rc.monthly_sales >= 100000
ORDER BY
  rc.order_month DESC,
  rc.monthly_sales_rank ASC;
