UPDATE orders
SET status = 'COMPLETED'
WHERE order_id = ?
  AND status IN ('PAID', 'READY')
  AND delivery_hold_flag = 'N';