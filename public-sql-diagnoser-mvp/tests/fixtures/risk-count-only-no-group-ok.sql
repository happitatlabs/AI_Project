SELECT COUNT(*) AS order_count
FROM orders
WHERE status = 'PAID';
