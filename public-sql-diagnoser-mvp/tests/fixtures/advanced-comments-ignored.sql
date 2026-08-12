-- MERGE INTO fake.target USING fake.source ON (...)
/* PIVOT (SUM(amount)) UNION ALL EXECUTE IMMEDIATE 'SELECT ...' */
SELECT order_id, status
FROM sales.orders
WHERE note = 'UNPIVOT APPLY LATERAL JSON ARRAY';
