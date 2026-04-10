SELECT o.order_id, o.status_code, o.memo_text
FROM legacy_orders o
JOIN customer_profile p ON p.customer_id = o.customer_id
WHERE o.status_code = 'READY'
  AND p.contact_email = 'ops.order@example.com'
ORDER BY o.created_at DESC;

