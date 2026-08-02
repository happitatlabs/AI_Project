SELECT
  ot."Order ID",
  ct."Customer Name",
  ot."Status"
FROM "Order Table" ot
JOIN [Customer Table] ct
  ON ct.[Customer ID] = ot."Customer ID"
WHERE ot."Status" = 'PAID -- literal marker';
