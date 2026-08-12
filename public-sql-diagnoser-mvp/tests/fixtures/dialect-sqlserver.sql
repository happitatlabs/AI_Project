SELECT TOP (100) WITH TIES
  [customer_id],
  [total_amount]
FROM [sales_orders]
ORDER BY ROW_NUMBER() OVER (PARTITION BY [customer_id] ORDER BY [order_date] DESC);
