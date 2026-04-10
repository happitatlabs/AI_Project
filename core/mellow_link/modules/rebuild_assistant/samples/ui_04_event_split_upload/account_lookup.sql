SELECT a.account_name
FROM customer_account a
WHERE a.account_id = :account_id
ORDER BY a.account_name ASC;

