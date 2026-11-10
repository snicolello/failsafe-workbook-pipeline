WITH counts AS (
    SELECT snapshot, SUM(row_count) AS served_rows,
           COUNT(CASE WHEN status = 'current' THEN 1 END) AS current_tabs,
           COUNT(CASE WHEN status = 'fallback' THEN 1 END) AS fallback_tabs,
           COUNT(CASE WHEN status = 'quarantined' THEN 1 END) AS quarantined_tabs
    FROM snapshot_status GROUP BY snapshot
), discrepancies AS (
    SELECT snapshot, COUNT(*) AS differences FROM snapshot_differences GROUP BY snapshot
)
SELECT c.snapshot, COALESCE(r.served_rows, 0) AS served_rows, COALESCE(r.current_tabs, 0) AS current_tabs,
       COALESCE(r.fallback_tabs, 0) AS fallback_tabs, COALESCE(r.quarantined_tabs, 0) AS quarantined_tabs,
       COALESCE(d.differences, 0) AS differing_rows_or_statuses
FROM checkpoints c LEFT JOIN counts r ON r.snapshot = c.snapshot
LEFT JOIN discrepancies d ON d.snapshot = c.snapshot ORDER BY c.through_id, c.snapshot;
