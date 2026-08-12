WITH RECURSIVE org_tree AS (
  SELECT employee_id, manager_id, employee_name, 0 AS depth
  FROM hr.employees
  WHERE manager_id IS NULL
  UNION ALL
  SELECT child.employee_id, child.manager_id, child.employee_name, parent.depth + 1
  FROM hr.employees child
  JOIN org_tree parent ON child.manager_id = parent.employee_id
)
SELECT employee_id, employee_name, depth
FROM org_tree
ORDER BY depth, employee_id;
