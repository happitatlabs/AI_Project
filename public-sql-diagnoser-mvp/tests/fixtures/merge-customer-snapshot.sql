MERGE INTO reporting.customer_snapshot target
USING (
  SELECT customer_id, status, updated_at
  FROM crm.customers_delta
) source
ON (target.customer_id = source.customer_id)
WHEN MATCHED THEN UPDATE SET
  target.status = source.status,
  target.updated_at = source.updated_at
WHEN NOT MATCHED THEN INSERT (customer_id, status, updated_at)
VALUES (source.customer_id, source.status, source.updated_at);
