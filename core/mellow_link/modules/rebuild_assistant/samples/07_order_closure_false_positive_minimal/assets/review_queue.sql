SELECT
    item_id,
    title,
    reviewer_id,
    review_required,
    display_order
FROM review_queue_item
WHERE review_required = :review_required
ORDER BY display_order, created_at DESC;
