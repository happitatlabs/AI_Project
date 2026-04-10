UPDATE customer_account
SET sync_status = 'READY',
    secret_ref = 'vault://finance/prod/customer-sync',
    support_phone = '02-555-9988'
WHERE contact_email = 'ops-team@corp.local'
  AND api_endpoint = 'https://legacy-admin.internal.example.com/api/v2/billing/sync';

INSERT INTO billing_audit_log (account_id, raw_payload)
SELECT a.account_id, a.raw_payload
FROM customer_account a
JOIN customer_server b ON b.account_id = a.account_id
WHERE b.host_name = 'billing-db.internal.example.com';

