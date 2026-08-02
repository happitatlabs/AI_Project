export type SqlPreset = {
  id: string;
  label: string;
  sql: string;
};

export const SQL_PRESETS: SqlPreset[] = [
  {
    id: "simple-order-list",
    label: "단순 주문 목록 조회",
    sql: `SELECT
  o.order_id,
  o.order_date,
  o.status,
  o.total_amount,
  c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
  AND o.order_date >= DATE '2026-01-01'
ORDER BY o.order_date DESC;`,
  },
  {
    id: "product-sales-summary",
    label: "상품별 매출 집계",
    sql: `SELECT
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
HAVING SUM(oi.quantity * oi.unit_price) >= 100000
ORDER BY total_sales_amount DESC;`,
  },
  {
    id: "customer-ranking",
    label: "고객 순위 분석",
    sql: `SELECT
  c.customer_id,
  c.customer_name,
  SUM(o.total_amount) AS total_sales,
  RANK() OVER (
    ORDER BY SUM(o.total_amount) DESC
  ) AS sales_rank
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY
  c.customer_id,
  c.customer_name;`,
  },
  {
    id: "cte-monthly-sales",
    label: "CTE 기반 월별 매출 분석",
    sql: `WITH paid_orders AS (
  SELECT
    o.order_id,
    o.customer_id,
    DATE_TRUNC('month', o.order_date) AS order_month,
    o.total_amount
  FROM orders o
  WHERE o.status IN ('PAID', 'SHIPPED')
),
monthly_sales AS (
  SELECT
    customer_id,
    order_month,
    COUNT(*) AS order_count,
    SUM(total_amount) AS monthly_sales
  FROM paid_orders
  GROUP BY customer_id, order_month
)
SELECT
  ms.customer_id,
  ms.order_month,
  ms.order_count,
  ms.monthly_sales,
  SUM(ms.monthly_sales) OVER (
    PARTITION BY ms.customer_id
    ORDER BY ms.order_month
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
  ) AS cumulative_sales
FROM monthly_sales ms
WHERE ms.monthly_sales >= 100000
ORDER BY ms.order_month DESC;`,
  },
  {
    id: "insert-select-batch",
    label: "INSERT INTO SELECT 배치 SQL",
    sql: `INSERT INTO monthly_order_snapshot (
  snapshot_month,
  order_id,
  customer_id,
  total_amount,
  created_at
)
SELECT
  DATE_TRUNC('month', o.order_date) AS snapshot_month,
  o.order_id,
  o.customer_id,
  o.total_amount,
  CURRENT_TIMESTAMP AS created_at
FROM orders o
WHERE o.order_date >= DATE '2026-06-01'
  AND o.order_date < DATE '2026-07-01'
  AND o.status IN ('PAID', 'SHIPPED');`,
  },
  {
    id: "union-orders",
    label: "UNION 결과 결합 SQL",
    sql: `SELECT
  o.order_id,
  o.customer_id,
  'ONLINE' AS order_channel
FROM online_orders o
WHERE o.status = 'PAID'
UNION ALL
SELECT
  s.order_id,
  s.customer_id,
  'STORE' AS order_channel
FROM store_orders s
WHERE s.status = 'PAID';`,
  },
];
