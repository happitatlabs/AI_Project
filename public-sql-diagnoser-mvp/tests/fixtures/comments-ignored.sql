-- SELECT * FROM fake_orders fo JOIN fake_customers fc ON fc.id = fo.customer_id WHERE fo.status = 'FAKE'
SELECT
  o.order_id,
  o.status,
  'literal -- keep this text' AS memo
FROM orders o
/* JOIN fake_payments fp ON fp.order_id = o.order_id
   WHERE fp.amount > 0
   GROUP BY fp.order_id */
WHERE o.status = 'PAID'
  AND o.memo = '/* not a block comment */';
