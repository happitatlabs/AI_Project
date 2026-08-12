SELECT o.order_id, item->>'sku' AS sku, item->>'quantity' AS quantity
FROM sales.orders o
CROSS JOIN LATERAL jsonb_array_elements(o.items_json) AS item
WHERE o.items_json IS NOT NULL;
