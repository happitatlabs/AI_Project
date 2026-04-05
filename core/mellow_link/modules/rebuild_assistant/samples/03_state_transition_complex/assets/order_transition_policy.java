public class OrderTransitionPolicy {
    public String nextState(Order order) {
        String nextState = "APPROVED";
        if (order.getState().equals("READY")) {
            order.setState(nextState);
        }
        if (order.getState().equals("APPROVED")) {
            order.setState("COMPLETED");
        }
        return order.getState();
    }
}
