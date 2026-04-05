UPDATE orders
SET state = 'APPROVED'
WHERE order_id = :order_id
  AND state = 'READY';

UPDATE orders
SET state = 'COMPLETED'
WHERE order_id = :order_id
  AND state = 'APPROVED';
