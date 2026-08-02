UPDATE orders
SET status = 'CANCELLED';

DELETE FROM order_items;
