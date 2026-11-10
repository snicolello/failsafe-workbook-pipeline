# Replaying the report in Unity Catalog

The prepared target stores accepted records and quarantined attempts in separate Delta tables. The latest published checkpoint determines which records the report serves. Local rehearsal reproduced all six saved reports, including both repair steps, with zero record or tab-status differences. **Live Databricks verification is pending.** [Local query results](local-expected.json)

## Prepare the files locally

From the repository root, run the synthetic demo and export its history. Replace `portfolio` with an existing catalog approved for the demo.

```sh
uv run python -m pipeline demo
uv run python -m databricks.export --demo build/demo --output build/databricks --catalog portfolio
```

The exporter writes five JSONL files to `build/databricks/upload/`. Three contain accepted records, tab events (rejections and retirements), and snapshot checkpoints. The other two contain each saved local report and its tab statuses. It also writes two SQL scripts for the named catalog. The second script contains the SHA-256 of each verified input file. Keep the generated scripts and upload files together.

## Run in a workspace

1. Use a Unity Catalog SQL warehouse and a catalog where you can create the dedicated `failsafe_demo` schema, volume, tables, and views. Read `01_setup.sql` and run it. It creates a managed volume called `workbook_input`. [Managed volumes](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-create-volume)
2. Upload the five unmodified JSONL files directly into `/Volumes/<catalog>/failsafe_demo/workbook_input/`. Complete the upload before running the load. Use one loader and one source replay in this dedicated schema.
3. Run `02_load_and_verify.sql` in order in a single SQL session. Stop at any failed statement. The script verifies each file digest, reads JSON with explicit field types, and checks incoming keys and existing history before merging. [File reads](https://docs.databricks.com/aws/en/sql/language-manual/functions/read_files) · [SHA-256](https://docs.databricks.com/aws/en/sql/language-manual/functions/sha2)
4. Run the same load script a second time. Save the final query result from the warehouse, together with the SQL warehouse/runtime version and export revision. Expect six snapshots and zero differences on both passes. Investigate any difference in `missing_records`, `extra_records`, `missing_statuses`, and `extra_statuses` within that session. The saved local counts are in the [expected results](local-expected.json).

## Inspect the contract

The accepted-record merge key includes brand, tab, item reference and workbook SHA, plus the source decision's `attempt_id`. That last field distinguishes a profile or parser repair of the same workbook and a return to previously observed bytes. The exported profile hash and parser version explain which contract accepted a record. Attempt IDs are ordered within a single local replay database. Existing history must agree with the incoming export before an append. [Merge SQL](merge.sql) · [Delta merge semantics](https://docs.databricks.com/aws/en/delta/merge)

The loader merges data and evidence first, then publishes checkpoint watermarks. For each tab at each checkpoint the views identify both the latest decision and the latest accepted decision. A rejection updates the visible status while the report continues serving its prior accepted rows. A first-time rejection has no accepted rows. When an unexpected, never-accepted tab disappears, its retirement removes it from current status and retains the historical rejection in quarantine. [Report views](report.sql)

```sql
SELECT * FROM current_report ORDER BY brand, tab, item_ref;
SELECT brand, tab, status, sha, accepted_sha, accepted_at, row_count, category
FROM snapshot_status WHERE snapshot = 'run2' ORDER BY brand, tab;
SELECT brand, tab, sha, cell, source_json, finding_json FROM quarantine ORDER BY attempt_id;
```

The comparison uses both directions of `EXCEPT ALL` on full records and tab statuses. It checks multiplicity, dates, values, source addresses, SHAs, fallback times, and rejection evidence. It also compares the final current-report view with the last saved report. The offline rehearsal merges the source twice in DuckDB and runs the same report and comparison SQL prepared for the warehouse. The results query retains checkpoints with zero visible tabs. Warehouse-specific volume access, JSONL ingestion, Delta behavior, and the workspace result capture are the remaining verification steps. [Comparison SQL](differences.sql) · [Results query](results.sql)
