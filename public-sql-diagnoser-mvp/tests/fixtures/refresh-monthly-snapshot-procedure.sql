CREATE PROCEDURE refresh_monthly_order_snapshot AS
BEGIN
  INSERT INTO monthly_order_snapshot (
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
    AND o.status IN ('PAID', 'SHIPPED');
END;
