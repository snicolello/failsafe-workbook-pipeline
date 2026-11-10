import json
import shutil

import openpyxl
import pytest

from databricks.export import check_local, export_files, prepare_sql
from pipeline.model import Rejection
from pipeline.run import ROOT, ingest
from pipeline.store import Store


def save(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_same_sha_returns_and_profile_changes_remain_distinct(tmp_path):
    demo = tmp_path / "demo"
    demo.mkdir()
    steps = []
    with Store(demo / "report.duckdb") as store:
        for index, (sha, profile, version, owner) in enumerate([
            ("A", "p1", "v1", None), ("A", "p2", "v1", "Rin"),
            ("B", "p2", "v1", None), ("A", "p2", "v1", "Rue"),
            ("A", "p2", "v2", "Fen"),
        ], start=1):
            timestamp = f"2026-06-0{index}T00:00:00Z"
            identity = ("test", "East", sha, profile, version, timestamp)
            if owner is None:
                store.apply(*identity, rejection=Rejection("identity_ambiguity", "A4", None, "Missing ID"))
            else:
                fields = dict(item_ref="I-1", season="Fall", stage="Cut", target_date="2027-01-01", owner=owner)
                row = dict(brand="test", tab="East", sha=sha, **fields,
                           lineage={key: f"{col}4" for key, col in zip(fields, "ABCDE")})
                store.apply(*identity, records=[row])
            name = f"step{index}"
            steps.append(dict(snapshot=name, observed_at=timestamp))
            path = demo / name
            path.mkdir()
            save(path / "status.json", store.statuses())
            save(path / "records.json", store.current_rows())
            if index == 1:
                restored = "2026-06-01T12:00:00Z"
                store.apply("test", "East", "restored", profile, version, restored, retired=True)
                assert store.statuses() == [] and len(store.exceptions()) == 1
                steps.append(dict(snapshot="unregistered-tab-removed", observed_at=restored))
                empty = demo / "unregistered-tab-removed"
                empty.mkdir()
                save(empty / "status.json", store.statuses())
                save(empty / "records.json", store.current_rows())
        save(demo / "summary.json", steps)
    export_files(demo, tmp_path)
    result = check_local(tmp_path)
    assert [r["quarantined"] for r in result] == [1, 0, 0, 0, 0, 0]
    assert [r["fallback"] for r in result] == [0, 0, 0, 1, 0, 0]
    assert [r["served_rows"] for r in result] == [0, 0, 1, 1, 1, 1]
    assert result[1]["snapshot"] == "unregistered-tab-removed" and result[1]["current"] == 0
    prepare_sql(tmp_path, tmp_path, "demo_catalog")
    sql = (tmp_path / "02_load_and_verify.sql").read_text(encoding="utf-8")
    assert "read_files('/Volumes/demo_catalog/failsafe_demo/workbook_input/" in sql
    assert "USING incoming_checkpoints" in sql

    expected = tmp_path / "expected_records.jsonl"
    expected.write_text(expected.read_text(encoding="utf-8").replace('"Rue"', '"Rin"'), encoding="utf-8")
    with pytest.raises(ValueError, match="Snapshot parity failed"):
        check_local(tmp_path)


def test_renamed_tab_leaves_status_on_restore_and_keeps_rejection_history(tmp_path):
    source = ROOT / "fixtures/run1/flintwake.xlsx"
    profile = ROOT / "profiles/flintwake.yaml"
    workbook = tmp_path / source.name
    steps = []
    with Store(tmp_path / "report.duckdb") as store:
        for index, name in enumerate(("baseline", "renamed", "restored"), 1):
            shutil.copyfile(source, workbook)
            if name == "renamed":
                book = openpyxl.load_workbook(workbook)
                book["Basin"].title = "Bay"
                book.save(workbook)
                book.close()
            timestamp = f"2026-06-0{index}T09:00:00Z"
            ingest(store, workbook, profile, timestamp)
            steps.append(dict(snapshot=name, observed_at=timestamp))
            path = tmp_path / name
            path.mkdir()
            save(path / "status.json", store.statuses())
            save(path / "records.json", store.current_rows())
        assert {e["tab"] for e in store.exceptions()} == {"Bay", "Basin"}
        save(tmp_path / "summary.json", steps)
    files = tmp_path / "upload"
    export_files(tmp_path, files)
    result = check_local(files)
    assert [s["quarantined"] for s in result] == [0, 1, 0]
    assert [s["fallback"] for s in result] == [0, 1, 0]
    events = [json.loads(line) for line in (files / "tab_events.jsonl").read_text().splitlines()]
    assert [(e["tab"], e["outcome"]) for e in events if e["tab"] == "Bay"] == [
        ("Bay", "blocked"), ("Bay", "retired"),
    ]
