SELECT employee_id, employee_name, LEVEL AS depth
FROM hr.employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
