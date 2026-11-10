-- Full-row, duplicate-sensitive comparisons, including JSON-encoded source locations.
CREATE OR REPLACE TEMP VIEW missing_records AS
SELECT * FROM expected_records EXCEPT ALL SELECT * FROM snapshot_report;
CREATE OR REPLACE TEMP VIEW extra_records AS
SELECT * FROM snapshot_report EXCEPT ALL SELECT * FROM expected_records;
CREATE OR REPLACE TEMP VIEW missing_statuses AS
SELECT * FROM expected_status EXCEPT ALL SELECT * FROM snapshot_status;
CREATE OR REPLACE TEMP VIEW extra_statuses AS
SELECT * FROM snapshot_status EXCEPT ALL SELECT * FROM expected_status;

CREATE OR REPLACE TEMP VIEW last_checkpoint AS
SELECT snapshot FROM checkpoints ORDER BY through_id DESC, snapshot DESC LIMIT 1;
CREATE OR REPLACE TEMP VIEW expected_current AS
SELECT brand, tab, sha, item_ref, season, stage, target_date, owner, lineage_json
FROM expected_records WHERE snapshot = (SELECT snapshot FROM last_checkpoint);
CREATE OR REPLACE TEMP VIEW missing_current AS
SELECT * FROM expected_current EXCEPT ALL SELECT * FROM current_report;
CREATE OR REPLACE TEMP VIEW extra_current AS
SELECT * FROM current_report EXCEPT ALL SELECT * FROM expected_current;

CREATE OR REPLACE TEMP VIEW snapshot_differences AS
SELECT snapshot, 'missing_record' AS mismatch FROM missing_records
UNION ALL SELECT snapshot, 'extra_record' FROM extra_records
UNION ALL SELECT snapshot, 'missing_status' FROM missing_statuses
UNION ALL SELECT snapshot, 'extra_status' FROM extra_statuses
UNION ALL SELECT snapshot, 'missing_current' FROM missing_current CROSS JOIN last_checkpoint
UNION ALL SELECT snapshot, 'extra_current' FROM extra_current CROSS JOIN last_checkpoint;
