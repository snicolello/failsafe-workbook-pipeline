"""Export the synthetic replay and prepare executable Unity Catalog SQL."""

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import duckdb


HERE = Path(__file__).resolve().parent
DECISION = "attempt_id BIGINT, brand STRING, tab STRING, sha STRING, profile_hash STRING, parser_version STRING, observed_at TIMESTAMP"
RECORD = "brand STRING, tab STRING, sha STRING, item_ref STRING, season STRING, stage STRING, target_date DATE, owner STRING, lineage_json STRING"
STATUS = ("brand STRING, tab STRING, status STRING, sha STRING, accepted_sha STRING, "
          "observed_at TIMESTAMP, accepted_at TIMESTAMP, row_count BIGINT, category STRING, "
          "outcome STRING, cell STRING, source_json STRING, message STRING, finding_json STRING")
SCHEMAS = {
    "incoming_accepted": DECISION + ", item_ref STRING, season STRING, stage STRING, target_date DATE, owner STRING, lineage_json STRING",
    "tab_events": DECISION + ", category STRING, outcome STRING, cell STRING, source_json STRING, message STRING, finding_json STRING",
    "incoming_checkpoints": "snapshot STRING, through_id BIGINT",
    "expected_records": "snapshot STRING, " + RECORD,
    "expected_status": "snapshot STRING, " + STATUS,
}
TABLES = {
    "accepted": SCHEMAS["incoming_accepted"],
    "quarantine": SCHEMAS["tab_events"],
    "retirements": DECISION,
    "checkpoints": SCHEMAS["incoming_checkpoints"],
}
EVENTS = """
CREATE OR REPLACE TEMP VIEW incoming_quarantine AS
SELECT * FROM tab_events WHERE category IS NOT NULL;
CREATE OR REPLACE TEMP VIEW incoming_retirements AS
SELECT attempt_id, brand, tab, sha, profile_hash, parser_version, observed_at
FROM tab_events WHERE outcome = 'retired';
"""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(db, sql):
    result = db.execute(sql)
    fields = [column[0] for column in result.description]
    for values in result.fetchall():
        row = dict(zip(fields, values))
        row["observed_at"] = row["observed_at"].replace(tzinfo=timezone.utc).isoformat()
        for key in ("lineage_json", "source_json", "finding_json"):
            if row.get(key) is not None:
                row[key] = canonical(json.loads(row[key]))
        if "target_date" in row:
            row["target_date"] = row["target_date"].isoformat()
        yield row


def _write_jsonl(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(canonical(row) + "\n")


def export_files(demo, output):
    """Export history from one serialized demo database and its six saved reports."""
    output.mkdir(parents=True, exist_ok=True)
    summary = _read(demo / "summary.json")
    with duckdb.connect(str(demo / "report.duckdb"), read_only=True) as db:
        source = "a.id AS attempt_id, a.brand, a.tab, a.sha, a.profile_hash, a.parser_version, a.observed_at"
        passed = _rows(db, f"""
            SELECT {source}, r.item_ref, r.season, r.stage, r.target_date, r.owner, r.lineage AS lineage_json
            FROM accepted_records r JOIN attempts a ON a.id = r.attempt_id
            ORDER BY a.id, r.item_ref""")
        _write_jsonl(output / "incoming_accepted.jsonl", passed)
        events = _rows(db, f"""
            SELECT {source}, a.category, a.outcome, a.cell, a.source_value AS source_json,
                   a.message, a.finding AS finding_json
            FROM attempts a WHERE outcome <> 'accepted' ORDER BY a.id""")
        _write_jsonl(output / "tab_events.jsonl", events)
        checkpoints = []
        expected_records = []
        expected_status = []
        for step in summary:
            name = step["snapshot"]
            instant = datetime.fromisoformat(step["observed_at"]).astimezone(timezone.utc).replace(tzinfo=None)
            through = db.execute("SELECT MAX(id) FROM attempts WHERE observed_at <= ?", [instant]).fetchone()[0]
            checkpoints.append({"snapshot": name, "through_id": through or 0})
            for row in _read(demo / name / "records.json"):
                row["lineage_json"] = canonical(row.pop("lineage"))
                expected_records.append({"snapshot": name, **row})
            for status in _read(demo / name / "status.json"):
                for old, new in (("value", "source_json"), ("finding", "finding_json")):
                    value = status.pop(old)
                    status[new] = canonical(value) if status["category"] is not None else None
                expected_status.append({"snapshot": name, **status})
        _write_jsonl(output / "incoming_checkpoints.jsonl", checkpoints)
        _write_jsonl(output / "expected_records.jsonl", expected_records)
        _write_jsonl(output / "expected_status.jsonl", expected_status)


def _columns(schema):
    return [field.split() for field in schema.split(", ")]


def prepare_sql(files, output, catalog):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", catalog):
        raise ValueError("Use an existing catalog with a simple SQL identifier")
    scope = f"USE CATALOG {catalog};\nUSE SCHEMA failsafe_demo;\nSET TIME ZONE 'UTC';\n"
    setup = (f"USE CATALOG {catalog};\nCREATE SCHEMA IF NOT EXISTS failsafe_demo;\n" + scope
             + "CREATE VOLUME IF NOT EXISTS workbook_input;\n")
    for table, schema in TABLES.items():
        setup += f"CREATE TABLE IF NOT EXISTS {table} ({schema}) USING DELTA;\n"
    (output / "01_setup.sql").write_text(setup, encoding="utf-8")
    load = scope
    for name, schema in SCHEMAS.items():
        path = f"/Volumes/{catalog}/failsafe_demo/workbook_input/{name}.jsonl"
        columns = ", ".join(c[0] for c in _columns(schema))
        load += (f"CREATE OR REPLACE TEMP VIEW {name} AS SELECT {columns}\n"
                 f"FROM read_files('{path}', format => 'json', schema => '{schema}', "
                 "mode => 'FAILFAST', schemaEvolutionMode => 'none');\n")
        payload = (files / f"{name}.jsonl").read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        load += (f"SELECT assert_true(COUNT(*) = 1 AND MAX(sha2(content, 256)) = '{digest}', "
                 f"'The uploaded {name} file differs from the verified export')\n"
                 f"FROM read_files('{path}', format => 'binaryFile');\n")
    # Each export is a complete, immutable history. Existing data must be its exact prefix.
    load += EVENTS
    keys = {"accepted": "attempt_id, item_ref", "quarantine": "attempt_id",
            "retirements": "attempt_id", "checkpoints": "snapshot"}
    for table, key in keys.items():
        source = "incoming_" + table
        load += (f"SELECT assert_true(COUNT(*) = 0, 'Duplicate {table} keys') FROM "
                 f"(SELECT {key} FROM {source} GROUP BY {key} HAVING COUNT(*) > 1) duplicates;\n"
                 f"SELECT assert_true(COUNT(*) = 0, 'Existing {table} history conflicts with export') "
                 f"FROM (SELECT * FROM {table} EXCEPT ALL SELECT * FROM {source}) conflicts;\n")
    for file in ("merge.sql", "report.sql", "differences.sql"):
        load += "\n" + (HERE / file).read_text(encoding="utf-8")
    load += """
SELECT assert_true(COUNT(*) = 0, 'Snapshot parity failed. Inspect snapshot_differences.') FROM snapshot_differences;
WITH counts AS (
    SELECT snapshot, COUNT(*) AS served_rows FROM snapshot_report GROUP BY snapshot
), discrepancies AS (
    SELECT snapshot, COUNT(*) AS n FROM snapshot_differences GROUP BY snapshot
)
SELECT c.snapshot, COALESCE(r.served_rows, 0) AS served_rows, COALESCE(d.n, 0) AS differing_rows_or_statuses
FROM checkpoints c LEFT JOIN counts r ON r.snapshot = c.snapshot
LEFT JOIN discrepancies d ON d.snapshot = c.snapshot ORDER BY c.through_id;
"""
    (output / "02_load_and_verify.sql").write_text(load, encoding="utf-8")


def check_local(files):
    """Run identical merge/view/diff SQL on DuckDB, using explicit JSONL types."""
    with duckdb.connect() as db:
        for name, schema in SCHEMAS.items():
            path = str(files / f"{name}.jsonl").replace("'", "''")
            types = ", ".join(f"'{col}':'{kind}'" for col, kind in _columns(schema))
            db.execute(f"CREATE TEMP VIEW {name} AS SELECT * FROM read_json('{path}', "
                       f"format='newline_delimited', columns={{{types}}})")
        db.execute(EVENTS)
        for table, schema in TABLES.items():
            db.execute(f"CREATE TABLE {table} ({schema})")
        merge = (HERE / "merge.sql").read_text(encoding="utf-8")
        db.execute(merge)
        db.execute(merge)
        for file in ("report.sql", "differences.sql"):
            db.execute((HERE / file).read_text(encoding="utf-8"))
        differences = db.execute("SELECT snapshot, mismatch, COUNT(*) FROM snapshot_differences GROUP BY 1, 2").fetchall()
        if differences:
            raise ValueError(f"Snapshot parity failed: {differences}")
        result = db.execute("""
            SELECT c.snapshot, COALESCE(SUM(row_count), 0), COUNT(*) FILTER (WHERE status = 'current'),
                   COUNT(*) FILTER (WHERE status = 'fallback'), COUNT(*) FILTER (WHERE status = 'quarantined')
            FROM checkpoints c LEFT JOIN snapshot_status s ON s.snapshot = c.snapshot
            GROUP BY c.snapshot, c.through_id ORDER BY c.through_id""").fetchall()
        return [dict(zip(("snapshot", "served_rows", "current", "fallback", "quarantined"), row),
                     differing_rows_or_statuses=0) for row in result]


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--demo", type=Path, default=Path("build/demo"))
    cli.add_argument("--output", type=Path, default=Path("build/databricks"))
    cli.add_argument("--catalog", default="portfolio")
    args = cli.parse_args()
    files = args.output / "upload"
    export_files(args.demo, files)
    result = check_local(files)
    prepare_sql(files, args.output, args.catalog)
    output = {"engine": "DuckDB local rehearsal", "merge_passes": 2, "snapshots": result}
    (args.output / "local-results.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"{len(result)} snapshots matched after two merges. SQL and upload files: {args.output}")


if __name__ == "__main__":
    main()
