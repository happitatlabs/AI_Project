SELECT *
FROM (
  SELECT customer_id
  FROM (
    SELECT customer_id
    FROM (
      SELECT customer_id
      FROM (
        SELECT customer_id
        FROM sales.orders
        WHERE status = 'PAID'
      ) level_four
    ) level_three
  ) level_two
) level_one;
