public class OrderTransitionService {
    public String advance(Order order) {
        String nextState = "APPROVED";
        if (order.getState().equals("READY")) {
            order.setState(nextState);
        }
        if (order.getState().equals("APPROVED")) {
            order.setState("COMPLETED");
        }
        return order.getStatus();
    }
}
