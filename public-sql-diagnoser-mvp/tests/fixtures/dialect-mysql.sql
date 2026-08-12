SELECT `customer_id`, JSON_EXTRACT(`payload`, '$.tier') AS customer_tier
FROM `sales_orders`
WHERE `payload` IS NOT NULL
LIMIT 100;
