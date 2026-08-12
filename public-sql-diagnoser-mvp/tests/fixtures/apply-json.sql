SELECT o.order_id, j.sku, j.quantity
FROM sales.orders o
OUTER APPLY OPENJSON(o.items_json)
WITH (
  sku nvarchar(64) '$.sku',
  quantity int '$.quantity'
) j;
