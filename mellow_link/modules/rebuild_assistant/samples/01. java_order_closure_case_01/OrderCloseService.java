public class OrderCloseService {

    public String closeOrder(Order order, String userRole, String currentHour) {
        if ("CLOSED".equals(order.getStatus()) || "CANCELLED".equals(order.getStatus())) {
            return "already_closed";
        }

        if (!"HQ".equals(userRole) && !"BRANCH".equals(userRole)) {
            return "forbidden";
        }

        if ("VIP".equals(order.getCustomerGrade())
                && ("22".equals(currentHour) || "23".equals(currentHour) || "00".equals(currentHour))) {
            return "vip_night_block";
        }

        if ("AGENCY".equals(order.getChannelCode())
                && order.getOrderAmount() >= 5000000
                && !"HQ".equals(userRole)) {
            return "agency_high_amount_hq_only";
        }

        if ("Y".equals(order.getDeliveryHoldFlag())) {
            return "delivery_hold_release_required";
        }

        if ("EXPORT".equals(order.getOrderType()) && order.getOrderAmount() >= 7000000) {
            order.setStatus("REVIEW_REQUIRED");
            return "export_review_required";
        }

        order.setStatus("CLOSED");
        return "closed";
    }
}
