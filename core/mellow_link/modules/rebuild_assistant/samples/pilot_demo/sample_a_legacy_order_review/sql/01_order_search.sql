-- 주문 조회 화면 조건 검색 SQL.
-- Controller: OrderController.searchOrders
-- Repository: OrderRepository.searchOrders

SELECT
    o.ORDER_ID,
    o.ORDER_NO,
    o.ORDER_STATUS,
    o.ORDER_AMOUNT,
    o.ORDERED_AT,
    c.CUSTOMER_NAME,
    c.CUSTOMER_GRADE,
    p.PAYMENT_STATUS,
    p.INTERFACE_RESULT,
    d.DELIVERY_STATUS,
    d.CARRIER_CODE,
    d.INVOICE_NO,
    o.ADMIN_MEMO,
    o.LAST_MODIFIED_BY,
    o.LAST_MODIFIED_AT
FROM LEGACY_ORDER o
JOIN LEGACY_CUSTOMER c
    ON c.CUSTOMER_ID = o.CUSTOMER_ID
LEFT JOIN LEGACY_PAYMENT p
    ON p.ORDER_ID = o.ORDER_ID
LEFT JOIN LEGACY_DELIVERY d
    ON d.ORDER_ID = o.ORDER_ID
WHERE o.ORDERED_AT >= :fromDate
  AND o.ORDERED_AT < :toDate + 1
  AND (:orderStatus IS NULL OR o.ORDER_STATUS = :orderStatus)
  AND (:paymentStatus IS NULL OR p.PAYMENT_STATUS = :paymentStatus)
  AND (:deliveryStatus IS NULL OR d.DELIVERY_STATUS = :deliveryStatus)
  AND (:customerName IS NULL OR c.CUSTOMER_NAME LIKE '%' || :customerName || '%')
ORDER BY o.ORDERED_AT DESC, o.ORDER_ID DESC;
