SELECT
  o.order_id,
  o.status_cd,
  CASE
    WHEN o.status_cd = 'P' THEN '결제완료'
    WHEN o.status_cd = 'S' THEN '배송중'
    WHEN o.status_cd = 'C' THEN '완료'
    ELSE '확인필요'
  END AS status_label
FROM orders o
WHERE o.use_yn = 'Y';
