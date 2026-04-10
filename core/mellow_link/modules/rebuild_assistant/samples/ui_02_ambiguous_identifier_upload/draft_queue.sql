SELECT status_text
FROM draft_queue
WHERE note_text LIKE '%hold%'
ORDER BY created_at DESC;

