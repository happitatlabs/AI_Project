SELECT
  o.order_id,
  c.customer_name,
  p.payment_status,
  s.shipment_status,
  r.region_name,
  cp.coupon_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
JOIN payments p
  ON p.order_id = o.order_id
JOIN shipments s
  ON s.order_id = o.order_id
JOIN regions r
  ON r.region_id = c.region_id
JOIN coupons cp
  ON cp.coupon_id = o.coupon_id
WHERE o.status = 'PAID';
