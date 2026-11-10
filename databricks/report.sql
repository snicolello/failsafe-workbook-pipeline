-- Shared SQL. Offline checks execute these same views over the exported events.
CREATE OR REPLACE VIEW tab_decisions AS
SELECT attempt_id, brand, tab, sha, observed_at, COUNT(*) AS row_count,
       'accepted' AS outcome, CAST(NULL AS STRING) AS category,
       CAST(NULL AS STRING) AS cell, CAST(NULL AS STRING) AS source_json,
       CAST(NULL AS STRING) AS message, CAST(NULL AS STRING) AS finding_json
FROM accepted
GROUP BY attempt_id, brand, tab, sha, observed_at
UNION ALL
SELECT attempt_id, brand, tab, sha, observed_at, 0 AS row_count,
       outcome, category, cell, source_json, message, finding_json
FROM quarantine
UNION ALL
SELECT attempt_id, brand, tab, sha, observed_at, 0 AS row_count,
       'retired' AS outcome, NULL AS category, NULL AS cell, NULL AS source_json,
       NULL AS message, NULL AS finding_json
FROM retirements;

CREATE OR REPLACE VIEW snapshot_heads AS
SELECT s.snapshot, d.brand, d.tab, MAX(d.attempt_id) AS latest_id,
       MAX(CASE WHEN d.outcome = 'accepted' THEN d.attempt_id END) AS accepted_id
FROM checkpoints s
JOIN tab_decisions d ON d.attempt_id <= s.through_id
GROUP BY s.snapshot, d.brand, d.tab;

CREATE OR REPLACE VIEW snapshot_status AS
SELECT h.snapshot, h.brand, h.tab,
       CASE WHEN h.accepted_id IS NULL THEN 'quarantined'
            WHEN h.latest_id = h.accepted_id THEN 'current'
            ELSE 'fallback' END AS status,
       d.sha, a.sha AS accepted_sha, d.observed_at, a.observed_at AS accepted_at,
       COALESCE(a.row_count, 0) AS row_count, d.category, d.outcome, d.cell,
       d.source_json, d.message, d.finding_json
FROM snapshot_heads h
JOIN tab_decisions d ON h.latest_id = d.attempt_id
LEFT JOIN tab_decisions a ON h.accepted_id = a.attempt_id
WHERE d.outcome <> 'retired';

CREATE OR REPLACE VIEW snapshot_report AS
SELECT h.snapshot, r.brand, r.tab, r.sha, r.item_ref, r.season, r.stage,
       r.target_date, r.owner, r.lineage_json
FROM snapshot_heads h JOIN accepted r ON r.attempt_id = h.accepted_id;

CREATE OR REPLACE VIEW current_report AS
SELECT brand, tab, sha, item_ref, season, stage, target_date, owner, lineage_json
FROM snapshot_report
WHERE snapshot = (SELECT snapshot FROM checkpoints ORDER BY through_id DESC, snapshot DESC LIMIT 1);
