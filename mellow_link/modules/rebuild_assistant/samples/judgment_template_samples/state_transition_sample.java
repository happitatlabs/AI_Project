if (order.getStatus().equals("PAID") || order.getStatus().equals("READY")) {
    if (!order.isDeliveryHold()) {
        order.setStatus("COMPLETED");
    }
}