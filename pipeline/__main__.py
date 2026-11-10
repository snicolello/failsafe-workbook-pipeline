"""Run from the repository root with python -m pipeline."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from .board import render_board
from .run import ingest
from .store import Store


def main():
    cli = argparse.ArgumentParser(description="Process synthetic WIP workbooks and write a status board.")
    commands = cli.add_subparsers(dest="command", required=True)
    load = commands.add_parser("ingest", help="Process a workbook using its profile")
    load.add_argument("workbook", type=Path)
    load.add_argument("profile", type=Path)
    load.add_argument("--db", type=Path, default=Path("build/current.duckdb"))
    load.add_argument("--board", type=Path, default=Path("build/status.html"))
    load.add_argument("--claude", action="store_true", help="Send exception excerpts to the local Claude CLI")
    demo = commands.add_parser("demo", help="Replay the four-run recruiting demonstration")
    demo.add_argument("--output", type=Path, default=Path("build/demo"))
    opts = cli.parse_args()
    if opts.command == "demo":
        from .scenario import replay
        replay(opts.output)
        return
    opts.db.parent.mkdir(parents=True, exist_ok=True)
    opts.board.parent.mkdir(parents=True, exist_ok=True)
    reviewer = None
    if opts.claude:
        from .review import claude_review
        reviewer = claude_review
    with Store(opts.db) as store:
        now = datetime.now(timezone.utc).isoformat()
        count = ingest(store, opts.workbook, opts.profile, now, reviewer=reviewer)
        records = store.current_rows()
        render_board(store.statuses(), records, opts.board, as_of=now)
        print(f"{count} tab decisions written | {len(records)} rows served | {opts.board.resolve()}")


if __name__ == "__main__":
    main()
