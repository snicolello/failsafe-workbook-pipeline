"""Real DuckDB integration tests exercising the tab acceptance boundary."""

import duckdb
import pytest

from pipeline.model import Rejection
from pipeline.store import Store


def row(tab, sha, item="SW-12"):
    fields = dict(item_ref=item, season="Fall", stage="Cut", target_date="2026-11-12",
                  owner="Rin")
    return dict(brand="sedge", tab=tab, sha=sha, **fields,
                lineage={key: f"{col}5" for key, col in zip(fields, "ABCDE")})


def accept(db, tab, sha, day, *, profile="p1", version="v1"):
    return db.apply("sedge", tab, sha, profile, version, day, records=[row(tab, sha)])


def reject(db, tab, sha, day):
    return db.apply("sedge", tab, sha, "p1", "v1", day,
                    rejection=Rejection("unrecognized_value", "C5", "maybe", "Unknown stage"),
                    finding={"quote": "maybe"})


def test_sibling_refresh_and_cold_quarantine_survive_restart(tmp_path):
    path = tmp_path / "history.duckdb"
    with Store(path) as db:
        accept(db, "North", "baseline", "2026-11-10")
        accept(db, "South", "baseline", "2026-11-10")
        reject(db, "North", "changed", "2026-11-11")
        reject(db, "East", "changed", "2026-11-11")
        accept(db, "South", "changed", "2026-11-11")
        assert reject(db, "North", "changed", "2026-11-12") is False

    with Store(path) as db:
        statuses = {s["tab"]: s for s in db.statuses()}
        assert statuses["North"]["status"] == "fallback"
        assert statuses["North"]["accepted_at"] == "2026-11-10T00:00:00+00:00"
        assert statuses["North"]["observed_at"] == "2026-11-11T00:00:00+00:00"
        assert statuses["East"]["status"] == "quarantined"
        assert statuses["East"]["accepted_sha"] is None
        assert statuses["East"]["row_count"] == 0
        assert statuses["South"]["status"] == "current"
        assert [(r["tab"], r["sha"]) for r in db.current_rows()] == [
            ("North", "baseline"), ("South", "changed")
        ]
        assert len(db.exceptions()) == 2
        assert all(e["finding"] == {"quote": "maybe"} and e["value"] == "maybe"
                   and e["outcome"] == "triaged" for e in db.exceptions())


def test_replay_identity_and_reintroduced_bytes():
    with Store(":memory:") as db:
        assert accept(db, "North", "A", "2026-11-10")
        assert db.is_current("sedge", "North", "A", "p1", "v1")
        assert not accept(db, "North", "A", "2026-11-11")
        assert accept(db, "North", "B", "2026-11-11")
        with pytest.raises(ValueError, match="Out-of-order"):
            accept(db, "North", "A", "2026-11-10")
        assert db.current_rows()[0]["sha"] == "B"
        assert accept(db, "North", "A", "2026-11-12")
        assert db.current_rows()[0]["sha"] == "A"
        assert accept(db, "North", "A", "2026-11-12", profile="p2")
        assert accept(db, "North", "A", "2026-11-12", profile="p2", version="v2")
        assert db.connection.execute("SELECT count(*) FROM attempts").fetchone() == (5,)


def test_mid_write_failure_rolls_back_history_and_rows(tmp_path):
    path = tmp_path / "atomic.duckdb"
    with Store(path) as db:
        accept(db, "North", "accepted", "2026-11-10")
        # DuckDB inserts the first candidate row before the primary key rejects the second.
        duplicate = row("North", "broken")
        with pytest.raises(duckdb.ConstraintException):
            db.apply("sedge", "North", "broken", "p1", "v1", "2026-11-11",
                     records=[duplicate, duplicate])

    with Store(path) as db:
        assert db.connection.execute("SELECT count(*) FROM attempts").fetchone() == (1,)
        assert db.connection.execute("SELECT count(*) FROM accepted_records").fetchone() == (1,)
        assert db.current_rows() == [row("North", "accepted")]
        assert db.statuses()[0]["status"] == "current"
        assert accept(db, "North", "repaired", "2026-11-12")


def test_repair_of_first_rejection_replaces_status_and_preserves_finding():
    with Store(":memory:") as db:
        reject(db, "North", "A", "2026-11-10")
        assert accept(db, "North", "A", "2026-11-11", profile="p2")
        assert db.statuses()[0]["status"] == "current"
        assert len(db.current_rows()) == len(db.exceptions()) == 1
