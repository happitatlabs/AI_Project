SELECT
    x.customer_id,
    x.customer_name,
    x.region,

    /* 전체 완료 주문 매출 */
    (
        SELECT SUM(z.order_total)
        FROM (
            SELECT
                o.order_id,
                (
                    SELECT SUM(
                        oi.quantity *
                        (
                            SELECT MAX(oi2.unit_price)
                            FROM order_items oi2
                            WHERE oi2.order_id = oi.order_id
                              AND oi2.product_id = oi.product_id
                        )
                    )
                    FROM order_items oi
                    WHERE oi.order_id = o.order_id
                ) AS order_total
            FROM orders o
            WHERE o.customer_id = x.customer_id
              AND o.status IN (
                  SELECT s.status_code
                  FROM (
                      SELECT 'COMPLETED' AS status_code
                  ) s
              )
        ) z
    ) AS total_sales,

    /* 최근 완료 주문일 */
    (
        SELECT MAX(a.order_date)
        FROM (
            SELECT o2.order_date
            FROM orders o2
            WHERE o2.customer_id = x.customer_id
              AND o2.status = 'COMPLETED'
              AND o2.order_id IN (
                  SELECT oi3.order_id
                  FROM order_items oi3
                  WHERE oi3.order_id = o2.order_id
              )
        ) a
    ) AS last_order_date,

    /* 최근 주문 이후 문의 */
    (
        SELECT COUNT(*)
        FROM support_tickets st
        WHERE st.customer_id = x.customer_id
          AND st.created_at > (
              SELECT MAX(o3.order_date)
              FROM orders o3
              WHERE o3.customer_id = x.customer_id
                AND o3.status = (
                    SELECT 'COMPLETED'
                    FROM (
                        SELECT 1 AS dummy
                    ) d
                )
          )
          AND EXISTS (
              SELECT 1
              FROM customers c3
              WHERE c3.customer_id = st.customer_id
                AND EXISTS (
                    SELECT 1
                    FROM orders o30
                    WHERE o30.customer_id = c3.customer_id
                      AND o30.status = 'COMPLETED'
                )
          )
    ) AS tickets_after_last_order,

    /* 성공 결제액 */
    COALESCE(
        (
            SELECT SUM(p.amount)
            FROM payments p
            WHERE p.customer_id = x.customer_id
              AND p.payment_status = 'SUCCESS'
              AND p.payment_date >= (
                  SELECT MIN(o4.order_date)
                  FROM orders o4
                  WHERE o4.customer_id = x.customer_id
                    AND o4.status = 'COMPLETED'
                    AND o4.order_id IN (
                        SELECT oi4.order_id
                        FROM order_items oi4
                        WHERE oi4.order_id IN (
                            SELECT o40.order_id
                            FROM orders o40
                            WHERE o40.customer_id = x.customer_id
                        )
                    )
              )
        ),
        (
            SELECT 0
            FROM (
                SELECT 1 AS dummy
            ) fallback_value
        )
    ) AS successful_payment_amount,

    /* 고객 상태까지 SELECT 안에서 다시 조회 */
    CASE
        WHEN (
            SELECT COUNT(*)
            FROM orders q1
            WHERE q1.customer_id = x.customer_id
              AND q1.status = 'COMPLETED'
        ) > (
            SELECT AVG(q2.cnt)
            FROM (
                SELECT COUNT(*) AS cnt
                FROM orders q3
                WHERE q3.status = 'COMPLETED'
                GROUP BY q3.customer_id
            ) q2
        )
        THEN
            CASE
                WHEN (
                    SELECT COUNT(*)
                    FROM support_tickets q4
                    WHERE q4.customer_id = x.customer_id
                ) > (
                    SELECT AVG(q5.ticket_count)
                    FROM (
                        SELECT COUNT(*) AS ticket_count
                        FROM support_tickets q6
                        GROUP BY q6.customer_id
                    ) q5
                )
                THEN 'HIGH_VALUE_BUT_NEEDS_SUPPORT'
                ELSE 'HIGH_VALUE'
            END
        ELSE 'NORMAL'
    END AS customer_type

FROM (
    SELECT *
    FROM customers c
    WHERE c.customer_id IN (
        SELECT c0.customer_id
        FROM customers c0
        WHERE EXISTS (
            SELECT 1
            FROM orders o0
            WHERE o0.customer_id = c0.customer_id
        )
    )
) x

WHERE

/* 평균보다 주문이 많은 고객 */
(
    SELECT COUNT(*)
    FROM orders b1
    WHERE b1.customer_id = x.customer_id
      AND b1.status = 'COMPLETED'
) > (
    SELECT AVG(b2.customer_order_count)
    FROM (
        SELECT
            b3.customer_id,
            COUNT(*) AS customer_order_count
        FROM orders b3
        WHERE b3.status IN (
            SELECT b4.status
            FROM (
                SELECT DISTINCT status
                FROM orders
                WHERE status = 'COMPLETED'
            ) b4
        )
        GROUP BY b3.customer_id
    ) b2
)

/* 고가 상품 구매 경험 */
AND EXISTS (
    SELECT 1
    FROM order_items d1
    WHERE d1.order_id IN (
        SELECT d2.order_id
        FROM orders d2
        WHERE d2.customer_id = x.customer_id
          AND d2.order_id IN (
              SELECT d3.order_id
              FROM order_items d3
              WHERE d3.product_id IN (
                  SELECT d4.product_id
                  FROM products d4
                  WHERE d4.price > (
                      SELECT AVG(d5.price)
                      FROM products d5
                      WHERE d5.category_id IN (
                          SELECT d6.category_id
                          FROM products d6
                          WHERE d6.product_id = d4.product_id
                      )
                  )
              )
          )
    )
)

/* 환불 문제 고객 제외 */
AND x.customer_id NOT IN (
    SELECT e1.customer_id
    FROM refunds e1
    WHERE e1.customer_id IN (
        SELECT e2.customer_id
        FROM (
            SELECT DISTINCT customer_id
            FROM refunds
        ) e2
    )
      AND e1.refund_amount > (
          SELECT AVG(e3.refund_amount)
          FROM refunds e3
          WHERE e3.customer_id IN (
              SELECT e4.customer_id
              FROM orders e4
              WHERE e4.order_date >= (
                  SELECT MIN(e5.order_date)
                  FROM orders e5
                  WHERE e5.order_date >= DATE '2025-01-01'
              )
          )
      )
)

/* 지역 평균 매출보다 높은 고객 */
AND (
    SELECT SUM(f1.quantity * f1.unit_price)
    FROM order_items f1
    WHERE f1.order_id IN (
        SELECT f2.order_id
        FROM orders f2
        WHERE f2.customer_id = x.customer_id
          AND f2.status = 'COMPLETED'
          AND EXISTS (
              SELECT 1
              FROM order_items f3
              WHERE f3.order_id = f2.order_id
          )
    )
) > (
    SELECT AVG(f4.region_customer_sales)
    FROM (
        SELECT
            f5.customer_id,
            (
                SELECT SUM(f6.quantity * f6.unit_price)
                FROM order_items f6
                WHERE f6.order_id IN (
                    SELECT f7.order_id
                    FROM orders f7
                    WHERE f7.customer_id = f5.customer_id
                      AND f7.status = 'COMPLETED'
                      AND f7.order_id IN (
                          SELECT f8.order_id
                          FROM order_items f8
                          WHERE f8.order_id = f7.order_id
                      )
                )
            ) AS region_customer_sales
        FROM customers f5
        WHERE f5.region IN (
            SELECT f9.region
            FROM customers f9
            WHERE f9.region = x.region
        )
    ) f4
)

/* 성공 결제 또는 최근 활동이라는 추가 조건 */
AND (
    EXISTS (
        SELECT 1
        FROM payments g1
        WHERE g1.customer_id = x.customer_id
          AND g1.payment_status = 'SUCCESS'
          AND g1.payment_id IN (
              SELECT g2.payment_id
              FROM payments g2
              WHERE g2.customer_id IN (
                  SELECT g3.customer_id
                  FROM customers g3
                  WHERE g3.customer_id = x.customer_id
              )
          )
    )
    OR
    (
        SELECT MAX(g4.order_date)
        FROM orders g4
        WHERE g4.customer_id = x.customer_id
    ) > (
        SELECT MAX(g5.order_date)
        FROM orders g5
        WHERE g5.order_date < DATE '2025-01-01'
    )
)

ORDER BY
    (
        SELECT SUM(h1.quantity * h1.unit_price)
        FROM order_items h1
        WHERE h1.order_id IN (
            SELECT h2.order_id
            FROM orders h2
            WHERE h2.customer_id = x.customer_id
              AND h2.status = 'COMPLETED'
        )
    ) DESC,
    x.customer_id;