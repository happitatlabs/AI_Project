package demo.legacy.order;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

/**
 * Demo-only controller flow.
 * The purpose is to show how screen requests reach service and DAO calls.
 */
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    public List<Map<String, Object>> searchOrders(
            LocalDate fromDate,
            LocalDate toDate,
            String orderStatus,
            String paymentStatus,
            String deliveryStatus,
            String customerName
    ) {
        OrderSearchCondition condition = new OrderSearchCondition(
                fromDate,
                toDate,
                orderStatus,
                paymentStatus,
                deliveryStatus,
                customerName
        );
        return orderService.searchOrders(condition);
    }

    public Map<String, Object> reviewPaymentMismatch(LocalDate fromDate, LocalDate toDate) {
        return Map.of(
                "periodFrom", fromDate,
                "periodTo", toDate,
                "items", orderService.findPaymentCheckTargets(fromDate, toDate)
        );
    }

    public void markReadyToShip(long orderId, String operatorId, String adminMemo) {
        orderService.changeOrderStatus(
                orderId,
                "PAID",
                "READY_TO_SHIP",
                "READY",
                operatorId,
                adminMemo
        );
    }

    public void manualStatusAdjust(
            long orderId,
            String currentStatus,
            String nextStatus,
            String operatorId,
            String adminMemo
    ) {
        orderService.manualStatusAdjust(orderId, currentStatus, nextStatus, operatorId, adminMemo);
    }
}

record OrderSearchCondition(
        LocalDate fromDate,
        LocalDate toDate,
        String orderStatus,
        String paymentStatus,
        String deliveryStatus,
        String customerName
) {
}
