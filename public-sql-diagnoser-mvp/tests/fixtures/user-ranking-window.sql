SELECT
  u.user_id,
  u.user_name,
  u.login_count,
  RANK() OVER (
    ORDER BY u.login_count DESC
  ) AS login_rank,
  ROW_NUMBER() OVER (
    ORDER BY u.created_at ASC
  ) AS signup_order
FROM users u
WHERE u.use_yn = 'Y';
