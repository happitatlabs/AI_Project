<%@ page language="java" %>
<form action="/orders/submit" method="post">
  <input name="orderId" />
  <c:if test="${not empty helperText}">
    <span>${helperText}</span>
  </c:if>
  <button onclick="submitOrder()">submit</button>
</form>

