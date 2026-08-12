DELETE FROM staging.order_errors e
USING sales.orders o
WHERE e.order_id = o.order_id
  AND o.status = 'CANCELLED';
