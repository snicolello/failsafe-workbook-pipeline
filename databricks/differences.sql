-- Full-row, duplicate-sensitive comparisons, including JSON-encoded source locations.
CREATE OR REPLACE TEMP VIEW missing_records AS
SELECT * FROM expected_records EXCEPT ALL SELECT * FROM snapshot_report;
CREATE OR REPLACE TEMP VIEW extra_records AS
SELECT * FROM snapshot_report EXCEPT ALL SELECT * FROM expected_records;
CREATE OR REPLACE TEMP VIEW missing_statuses AS
SELECT * FROM expected_status EXCEPT ALL SELECT * FROM snapshot_status;
CREATE OR REPLACE TEMP VIEW extra_statuses AS
SELECT * FROM snapshot_status EXCEPT ALL SELECT * FROM expected_status;

CREATE OR REPLACE TEMP VIEW snapshot_differences AS
SELECT snapshot, 'missing_record' AS mismatch FROM missing_records
UNION ALL SELECT snapshot, 'extra_record' FROM extra_records
UNION ALL SELECT snapshot, 'missing_status' FROM missing_statuses
UNION ALL SELECT snapshot, 'extra_status' FROM extra_statuses;
