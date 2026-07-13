-- 주문 상태 갱신 SQL.
-- 상태 변경 이력 테이블이 없어 이전 상태와 변경 사유가 별도 row로 남지 않는다.

UPDATE LEGACY_ORDER
   SET ORDER_STATUS = :nextOrderStatus,
       ADMIN_MEMO = CASE
           WHEN :adminMemo IS NULL THEN ADMIN_MEMO
           ELSE :adminMemo
       END,
       LAST_MODIFIED_BY = :operatorId,
       LAST_MODIFIED_AT = SYSDATE
 WHERE ORDER_ID = :orderId
   AND ORDER_STATUS = :currentOrderStatus;

UPDATE LEGACY_DELIVERY
   SET DELIVERY_STATUS = :nextDeliveryStatus,
       CARRIER_CODE = NVL(:carrierCode, CARRIER_CODE),
       INVOICE_NO = NVL(:invoiceNo, INVOICE_NO),
       READY_AT = CASE WHEN :nextDeliveryStatus = 'READY' THEN SYSDATE ELSE READY_AT END,
       SHIPPED_AT = CASE WHEN :nextDeliveryStatus = 'SHIPPED' THEN SYSDATE ELSE SHIPPED_AT END,
       DELIVERED_AT = CASE WHEN :nextDeliveryStatus = 'DELIVERED' THEN SYSDATE ELSE DELIVERED_AT END
 WHERE ORDER_ID = :orderId
   AND (:updateDelivery = 'Y');
