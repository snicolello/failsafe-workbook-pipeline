"""Transactional worksheet decisions and the report's last-accepted view."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import duckdb

from .model import Rejection


SCHEMA = """
CREATE SEQUENCE IF NOT EXISTS attempt_ids;
CREATE TABLE IF NOT EXISTS attempts (
    id BIGINT PRIMARY KEY DEFAULT nextval('attempt_ids'),
    brand VARCHAR NOT NULL,
    tab VARCHAR NOT NULL,
    sha VARCHAR NOT NULL,
    profile_hash VARCHAR NOT NULL,
    parser_version VARCHAR NOT NULL,
    observed_at TIMESTAMP NOT NULL, -- UTC, normalized at the boundary
    category VARCHAR,
    outcome VARCHAR NOT NULL,
    cell VARCHAR,
    source_value JSON,
    message VARCHAR,
    finding JSON
);
CREATE TABLE IF NOT EXISTS accepted_records (
    attempt_id BIGINT REFERENCES attempts(id),
    item_ref VARCHAR NOT NULL,
    season VARCHAR NOT NULL,
    stage VARCHAR NOT NULL,
    target_date DATE NOT NULL,
    owner VARCHAR NOT NULL,
    lineage JSON NOT NULL,
    PRIMARY KEY (attempt_id, item_ref)
);
CREATE TABLE IF NOT EXISTS tab_heads (
    brand VARCHAR,
    tab VARCHAR,
    latest_id BIGINT NOT NULL REFERENCES attempts(id),
    accepted_id BIGINT REFERENCES attempts(id),
    PRIMARY KEY (brand, tab)
);
CREATE OR REPLACE VIEW current_report AS
    SELECT h.brand, h.tab, a.sha, r.item_ref, r.season, r.stage,
           r.target_date, r.owner, r.lineage
    FROM tab_heads h
    JOIN attempts a ON a.id = h.accepted_id
    JOIN accepted_records r ON r.attempt_id = h.accepted_id;
CREATE OR REPLACE VIEW quarantine AS
    SELECT * FROM attempts WHERE category IS NOT NULL;
"""

CORE_FIELDS = ("item_ref", "season", "stage", "target_date", "owner")


def _instant(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _source_json(value: object) -> str:
    # Excel source evidence may include a native date or datetime.
    def encode(obj):
        if isinstance(obj, date):
            return obj.isoformat()
        raise TypeError(f"Cannot serialize {type(obj).__name__}")

    return json.dumps(value, default=encode, ensure_ascii=False, allow_nan=False)


class Store:
    """One connection per writer. Readers see only committed tab decisions."""

    def __init__(self, path: str | Path):
        self.connection = duckdb.connect(str(path))
        self.connection.execute(SCHEMA)

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _latest(self, brand, tab):
        return self.connection.execute(
            """SELECT a.sha, a.profile_hash, a.parser_version, a.observed_at, h.accepted_id, a.outcome
               FROM tab_heads h JOIN attempts a ON a.id = h.latest_id
               WHERE h.brand = ? AND h.tab = ?""",
            [brand, tab],
        ).fetchone()

    def is_current(self, brand: str, tab: str, sha: str, profile_hash: str,
                   parser_version: str) -> bool:
        head = self._latest(brand, tab)
        return head is not None and head[5] != "retired" and head[:3] == (
            sha, profile_hash, parser_version
        )

    def apply(
        self, brand: str, tab: str, sha: str, profile_hash: str, parser_version: str,
        observed_at: str | datetime, *, records: Iterable[dict] | None = None,
        rejection: Rejection | None = None, finding=None, retired: bool = False,
    ) -> bool:
        """Commit one complete tab decision, or leave its previous head intact.

        A transition back to earlier bytes is a new observation. A rejection can
        advance the latest attempt pointer; only a pass advances the report pointer.
        """
        if sum((records is not None, rejection is not None, retired)) != 1:
            raise ValueError("Supply exactly one of records, rejection, or retirement")
        if not all((brand, tab, sha, profile_hash, parser_version)):
            raise ValueError("Incomplete attempt identity")
        instant = _instant(observed_at)
        db = self.connection
        db.execute("BEGIN TRANSACTION")
        try:
            head = self._latest(brand, tab)
            if head and head[:3] == (sha, profile_hash, parser_version) and (head[5] == "retired") == retired:
                db.execute("ROLLBACK")
                return False
            if head and instant < head[3]:
                raise ValueError(f"Out-of-order observation for {brand}/{tab}")
            if retired and (head is None or head[4] is not None):
                raise ValueError("Only a never-accepted tab can be retired")

            evidence = [None, "retired" if retired else "accepted", None, None, None, None]
            if rejection is not None:
                evidence = [
                    rejection.category, rejection.outcome, rejection.cell,
                    _source_json(rejection.value), rejection.message, _source_json(finding),
                ]
            attempt_id = db.execute(
                """INSERT INTO attempts
                   (brand,tab,sha,profile_hash,parser_version,observed_at,
                    category,outcome,cell,source_value,message,finding)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                [brand, tab, sha, profile_hash, parser_version, instant, *evidence],
            ).fetchone()[0]
            accepted_id = head[4] if head else None
            if records is not None:
                self._write_records(attempt_id, brand, tab, sha, records)
                accepted_id = attempt_id

            db.execute(
                """INSERT INTO tab_heads VALUES (?, ?, ?, ?)
                   ON CONFLICT (brand, tab) DO UPDATE
                   SET latest_id = excluded.latest_id, accepted_id = excluded.accepted_id""",
                [brand, tab, attempt_id, accepted_id],
            )
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        return True

    def _write_records(self, attempt_id, brand, tab, sha, records):
        batch = []
        for row in records:
            if (row["brand"], row["tab"], row["sha"]) != (brand, tab, sha):
                raise ValueError("Record source differs from its enclosing attempt")
            if any(not row[field] for field in CORE_FIELDS):
                raise ValueError("Accepted records require five populated core fields")
            if any(not row["lineage"].get(field) for field in CORE_FIELDS):
                raise ValueError("Accepted records require lineage for all five core fields")
            batch.append([attempt_id, *(row[field] for field in CORE_FIELDS),
                          _source_json(row["lineage"])])
        if not batch:
            raise ValueError("An empty candidate cannot replace accepted data")
        self.connection.executemany(
            "INSERT INTO accepted_records VALUES (?, ?, ?, ?, ?, ?, ?)", batch
        )

    def _rows(self, sql: str):
        result = self.connection.execute(sql)
        names = [column[0] for column in result.description]
        rows = []
        for values in result.fetchall():
            row = dict(zip(names, values))
            for name, value in row.items():
                if name in ("value", "finding", "lineage") and value is not None:
                    row[name] = json.loads(value)
                elif isinstance(value, datetime):
                    row[name] = value.replace(tzinfo=timezone.utc).isoformat()
                elif isinstance(value, date):
                    row[name] = value.isoformat()
            rows.append(row)
        return rows

    def current_rows(self) -> list[dict]:
        return self._rows("SELECT * FROM current_report ORDER BY brand, tab, item_ref")

    def statuses(self) -> list[dict]:
        return self._rows(
            """WITH counts AS (
                   SELECT attempt_id, count(*) AS n FROM accepted_records GROUP BY attempt_id
               )
               SELECT h.brand, h.tab,
                   CASE WHEN h.latest_id = h.accepted_id THEN 'current'
                        WHEN h.accepted_id IS NULL THEN 'quarantined' ELSE 'fallback' END AS status,
                   a.sha, p.sha AS accepted_sha, a.observed_at, p.observed_at AS accepted_at,
                   coalesce(c.n, 0) AS row_count, a.category, a.outcome, a.cell,
                   a.source_value AS value, a.message, a.finding
               FROM tab_heads h JOIN attempts a ON a.id = h.latest_id
               LEFT JOIN attempts p ON p.id = h.accepted_id
               LEFT JOIN counts c ON c.attempt_id = h.accepted_id
               WHERE a.outcome <> 'retired'
               ORDER BY h.brand, h.tab"""
        )

    def exceptions(self) -> list[dict]:
        return self._rows(
            """SELECT brand, tab, sha, profile_hash, parser_version, observed_at,
                      category, outcome, cell, source_value AS value, message, finding
               FROM quarantine ORDER BY observed_at, brand, tab, id"""
        )
