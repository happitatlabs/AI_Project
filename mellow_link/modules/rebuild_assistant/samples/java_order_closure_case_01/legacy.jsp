<%
String orderId = request.getParameter("orderId");
String userRole = (String) session.getAttribute("userRole");
String channelCode = request.getParameter("channelCode");
String status = request.getParameter("status");
int amount = Integer.parseInt(request.getParameter("amount"));

if ("CLOSED".equals(status) || "CANCELLED".equals(status)) {
    out.println("이미 마감되었거나 취소된 주문입니다.");
    return;
}

if (!"HQ".equals(userRole) && !"BRANCH".equals(userRole)) {
    out.println("마감 권한이 없습니다.");
    return;
}

if ("AGENCY".equals(channelCode) && amount >= 5000000 && !"HQ".equals(userRole)) {
    out.println("대리점 고액 주문은 본사만 마감할 수 있습니다.");
    return;
}
%>
<html>
<body>
    <h1>주문 마감</h1>
    <div>주문번호: <%= orderId %></div>
    <div>현재상태: <%= status %></div>
    <button>마감 실행</button>
</body>
</html>
