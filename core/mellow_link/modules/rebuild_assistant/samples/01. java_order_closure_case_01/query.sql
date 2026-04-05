SELECT
    o.order_id,
    o.status,
    o.order_amount,
    o.channel_code,
    o.customer_grade,
    o.delivery_hold_flag,
    o.order_type
FROM sales_order o
WHERE o.order_id = :order_id
  AND o.deleted_flag = 'N'
  AND o.status IN ('PAID', 'READY', 'REVIEW_REQUIRED')
  AND (
        :user_role = 'HQ'
        OR (:user_role = 'BRANCH' AND o.channel_code <> 'AGENCY')
      );
