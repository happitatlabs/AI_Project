SELECT
    c.customer_id,
    c.customer_name,
    c.region,

    /* ① 고객의 전체 완료 주문 매출 */
    (
        SELECT SUM(
            (
                SELECT SUM(oi.quantity * oi.unit_price)
                FROM order_items oi
                WHERE oi.order_id = o.order_id
            )
        )
        FROM orders o
        WHERE o.customer_id = c.customer_id
          AND o.status = 'COMPLETED'
    ) AS total_sales,

    /* ② 최근 완료 주문일 */
    (
        SELECT MAX(o2.order_date)
        FROM orders o2
        WHERE o2.customer_id = c.customer_id
          AND o2.status = 'COMPLETED'
    ) AS last_order_date,

    /* ③ 최근 주문 이후 발생한 문의 수 */
    (
        SELECT COUNT(*)
        FROM support_tickets st
        WHERE st.customer_id = c.customer_id
          AND st.created_at > (
              SELECT MAX(o3.order_date)
              FROM orders o3
              WHERE o3.customer_id = c.customer_id
                AND o3.status = 'COMPLETED'
          )
    ) AS tickets_after_last_order,

    /* ④ 성공 결제 총액 */
    (
        SELECT SUM(p.amount)
        FROM payments p
        WHERE p.customer_id = c.customer_id
          AND p.payment_status = 'SUCCESS'
          AND p.payment_date >= (
              SELECT MIN(o4.order_date)
              FROM orders o4
              WHERE o4.customer_id = c.customer_id
                AND o4.status = 'COMPLETED'
          )
    ) AS successful_payment_amount

FROM customers c

/* ⑤ 평균보다 주문이 많은 고객 */
WHERE (
    SELECT COUNT(*)
    FROM orders o5
    WHERE o5.customer_id = c.customer_id
      AND o5.status = 'COMPLETED'
) > (
    SELECT AVG(customer_order_count)
    FROM (
        SELECT COUNT(*) AS customer_order_count
        FROM orders o6
        WHERE o6.status = 'COMPLETED'
        GROUP BY o6.customer_id
    ) order_stats
)

/* ⑥ 고가 상품 구매 경험 존재 */
AND EXISTS (
    SELECT 1
    FROM order_items oi2
    WHERE oi2.order_id IN (
        SELECT o7.order_id
        FROM orders o7
        WHERE o7.customer_id = c.customer_id
          AND o7.status = 'COMPLETED'
    )
      AND oi2.product_id IN (
          SELECT p2.product_id
          FROM products p2
          WHERE p2.price > (
              SELECT AVG(p3.price)
              FROM products p3
              WHERE p3.category_id = p2.category_id
          )
      )
)

/* ⑦ 환불 문제가 심한 고객 제외 */
AND c.customer_id NOT IN (
    SELECT r.customer_id
    FROM refunds r
    WHERE r.refund_amount > (
        SELECT AVG(r2.refund_amount)
        FROM refunds r2
        WHERE r2.customer_id IN (
            SELECT o8.customer_id
            FROM orders o8
            WHERE o8.order_date >= DATE '2025-01-01'
        )
    )
)

/* ⑧ 해당 지역 평균 매출보다 높은 고객만 */
AND (
    SELECT SUM(oi3.quantity * oi3.unit_price)
    FROM order_items oi3
    WHERE oi3.order_id IN (
        SELECT o9.order_id
        FROM orders o9
        WHERE o9.customer_id = c.customer_id
          AND o9.status = 'COMPLETED'
    )
) > (
    SELECT AVG(region_customer_sales)
    FROM (
        SELECT
            (
                SELECT SUM(oi4.quantity * oi4.unit_price)
                FROM order_items oi4
                WHERE oi4.order_id IN (
                    SELECT o11.order_id
                    FROM orders o11
                    WHERE o11.customer_id = c2.customer_id
                      AND o11.status = 'COMPLETED'
                )
            ) AS region_customer_sales
        FROM customers c2
        WHERE c2.region = c.region
    ) region_stats
)

ORDER BY total_sales DESC;