"""Refresh the checked-in evidence from the local replay, e.g. python -m demo.save_snapshots."""

import json
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from pipeline.run import ROOT
from pipeline.scenario import replay


def save(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination) as temp:
        working = Path(temp)
        runs = replay(working)
        copyfile(working / "summary.json", destination / "summary.json")
        for run in runs:
            key = run["snapshot"]
            target = destination / key
            target.mkdir(exist_ok=True)
            for name in ("board.html", "status.json", "exceptions.json"):
                copyfile(working / key / name, target / name)
            records = json.loads((working / key / "records.json").read_text(encoding="utf-8"))
            with (target / "accepted.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
                for row in records:
                    stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    save(ROOT / "demo/snapshots")
