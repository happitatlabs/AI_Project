SELECT customer_id, status_name, status_count
FROM reporting.customer_status_counts
UNPIVOT (
  status_count FOR status_name IN (new_count, active_count, closed_count)
) unpivoted;
