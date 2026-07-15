package demo.legacy.order;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

/**
 * Demo-only service flow.
 * Business rules, status transition checks, manual correction, and SQL calls
 * are intentionally mixed to represent a small legacy modernization target.
 */
public class OrderService {
    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public List<Map<String, Object>> searchOrders(OrderSearchCondition condition) {
        if (condition.fromDate() == null || condition.toDate() == null) {
            throw new IllegalArgumentException("search period is required");
        }
        return orderRepository.searchOrders(condition);
    }

    public List<Map<String, Object>> findPaymentCheckTargets(LocalDate fromDate, LocalDate toDate) {
        return orderRepository.findPaymentCheckTargets(fromDate, toDate);
    }

    public List<Map<String, Object>> findDeliveryPendingTargets() {
        return orderRepository.findDeliveryPendingTargets();
    }

    public void changeOrderStatus(
            long orderId,
            String currentOrderStatus,
            String nextOrderStatus,
            String nextDeliveryStatus,
            String operatorId,
            String adminMemo
    ) {
        if (!isAllowedTransition(currentOrderStatus, nextOrderStatus)) {
            throw new IllegalStateException("blocked transition: " + currentOrderStatus + " -> " + nextOrderStatus);
        }

        boolean updateDelivery = nextDeliveryStatus != null;
        int updated = orderRepository.updateOrderAndDeliveryStatus(
                orderId,
                currentOrderStatus,
                nextOrderStatus,
                nextDeliveryStatus,
                updateDelivery,
                operatorId,
                adminMemo
        );

        if (updated == 0) {
            throw new IllegalStateException("order status was changed by another process");
        }
    }

    public void manualStatusAdjust(
            long orderId,
            String currentStatus,
            String nextStatus,
            String operatorId,
            String adminMemo
    ) {
        // Legacy behavior: manager correction bypasses normal transition rules.
        // It only leaves a free-text memo on the order row.
        orderRepository.updateOrderAndDeliveryStatus(
                orderId,
                currentStatus,
                nextStatus,
                null,
                false,
                operatorId,
                "[MANUAL] " + adminMemo
        );
    }

    private boolean isAllowedTransition(String currentStatus, String nextStatus) {
        if ("RECEIVED".equals(currentStatus) && "PAID".equals(nextStatus)) {
            return true;
        }
        if ("PAID".equals(currentStatus) && "READY_TO_SHIP".equals(nextStatus)) {
            return true;
        }
        if ("READY_TO_SHIP".equals(currentStatus) && "SHIPPED".equals(nextStatus)) {
            return true;
        }
        if ("SHIPPED".equals(currentStatus) && "DELIVERED".equals(nextStatus)) {
            return true;
        }
        return "RECEIVED".equals(currentStatus) && "CANCELLED".equals(nextStatus);
    }
}
