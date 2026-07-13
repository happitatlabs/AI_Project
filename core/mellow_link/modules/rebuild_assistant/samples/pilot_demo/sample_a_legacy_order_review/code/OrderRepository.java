package demo.legacy.order;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

/**
 * Demo-only DAO facade.
 * Each method maps to a SQL file in ../sql to make provenance explicit.
 */
public class OrderRepository {
    private final LegacySqlClient sqlClient;

    public OrderRepository(LegacySqlClient sqlClient) {
        this.sqlClient = sqlClient;
    }

    public List<Map<String, Object>> searchOrders(OrderSearchCondition condition) {
        return sqlClient.query(
                "sql/01_order_search.sql",
                Map.of(
                        "fromDate", condition.fromDate(),
                        "toDate", condition.toDate(),
                        "orderStatus", condition.orderStatus(),
                        "paymentStatus", condition.paymentStatus(),
                        "deliveryStatus", condition.deliveryStatus(),
                        "customerName", condition.customerName()
                )
        );
    }

    public List<Map<String, Object>> loadDailySummary(LocalDate fromDate, LocalDate toDate) {
        return sqlClient.query(
                "sql/02_order_summary.sql",
                Map.of("fromDate", fromDate, "toDate", toDate)
        );
    }

    public int updateOrderAndDeliveryStatus(
            long orderId,
            String currentOrderStatus,
            String nextOrderStatus,
            String nextDeliveryStatus,
            boolean updateDelivery,
            String operatorId,
            String adminMemo
    ) {
        return sqlClient.update(
                "sql/03_order_status_update.sql",
                Map.of(
                        "orderId", orderId,
                        "currentOrderStatus", currentOrderStatus,
                        "nextOrderStatus", nextOrderStatus,
                        "nextDeliveryStatus", nextDeliveryStatus,
                        "updateDelivery", updateDelivery ? "Y" : "N",
                        "operatorId", operatorId,
                        "adminMemo", adminMemo
                )
        );
    }

    public List<Map<String, Object>> findPaymentCheckTargets(LocalDate fromDate, LocalDate toDate) {
        return sqlClient.query(
                "sql/04_payment_check.sql",
                Map.of("fromDate", fromDate, "toDate", toDate)
        );
    }

    public List<Map<String, Object>> findDeliveryPendingTargets() {
        return sqlClient.query("sql/05_delivery_pending.sql", Map.of());
    }
}

interface LegacySqlClient {
    List<Map<String, Object>> query(String sqlPath, Map<String, Object> params);

    int update(String sqlPath, Map<String, Object> params);
}
