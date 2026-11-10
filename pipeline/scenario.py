"""Replay the four source deliveries in a fresh database using fixed observation times."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from .board import render_board
from .run import ROOT, ingest
from .store import Store


def _write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _recorded_finding(brand, tab, sha, rejection, default):
    path = ROOT / "demo/reviews" / f"{brand}.json"
    if path.is_file():
        event = json.loads(path.read_text(encoding="utf-8"))
        expected = [brand, tab, sha, rejection.category, rejection.cell, rejection.value]
        if [event[key] for key in ("brand", "tab", "sha", "category", "cell", "value")] == expected:
            return {**default, **event["finding"], "review_status": "recorded session replay"}
    return default


def replay(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    fixtures = ROOT / "fixtures"
    profiles = {p.stem: p for p in (ROOT / "profiles").glob("*.yaml")}
    steps = (
        ("run1", "Run 1 · All eight brands load", "2026-06-01T09:00:00Z", "run1", None),
        ("run2", "Run 2 · Two tabs serve last accepted data", "2026-06-02T09:00:00Z", "run2", None),
        ("run2-repaired", "Run 2 · Header repair", "2026-06-02T12:00:00Z", "run2", ("flintwake", "repairs")),
        ("run3", "Run 3 · An item spans two rows", "2026-06-03T09:00:00Z", "run3", None),
        ("run3-repaired", "Run 3 · Paired rows recovered", "2026-06-03T12:00:00Z", "run3", ("copper-rill", "repairs")),
        ("run4", "Run 4 · A ninth brand joins", "2026-06-04T09:00:00Z", "run4", ("gale-stitch", "onboarding")),
    )
    summary = []
    with TemporaryDirectory(dir=output) as scratch:
        database = Path(scratch) / "report.duckdb"
        with Store(database) as store:
            for key, title, timestamp, revision, change in steps:
                if change:
                    name, folder = change
                    profiles[name] = fixtures / folder / f"{name}.yaml"
                for path in sorted((fixtures / revision).glob("*.xlsx")):
                    ingest(store, path, profiles[path.stem], timestamp, reviewer=_recorded_finding)
                statuses, records = store.statuses(), store.current_rows()
                destination = output / key
                destination.mkdir(exist_ok=True)
                render_board(statuses, records, destination / "board.html", title=title, as_of=timestamp)
                for filename, data in (("status", statuses), ("records", records), ("exceptions", store.exceptions())):
                    _write(destination / f"{filename}.json", data)
                counts = {state: sum(s["status"] == state for s in statuses)
                          for state in ("current", "fallback", "quarantined")}
                summary.append({"snapshot": key, "observed_at": timestamp,
                                "rows": len(records), **counts})
                print(f"{key:<15} {len(records)} rows | {counts['current']} current | "
                      f"{counts['fallback']} on fallback | {counts['quarantined']} without history")
        os.replace(database, output / "report.duckdb")
    _write(output / "summary.json", summary)
    print(f"Open {(output / 'run2/board.html').resolve()}")
    return summary
