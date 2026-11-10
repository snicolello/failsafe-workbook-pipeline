"""Replay a profile proposal against real workbooks without changing saved state."""

import argparse
import hashlib
import json
from pathlib import Path

from .run import ROOT, ingest, load_profile
from .store import Store


def _snapshot(sources, profiles):
    # Both sides start empty. Counts measure what this input set can accept today.
    with Store(":memory:") as store:
        for brand, workbook in sorted(sources.items()):
            if brand in profiles:
                ingest(store, workbook, profiles[brand], "2000-01-01")
        rows = {(r["brand"], r["tab"], r["item_ref"]): r for r in store.current_rows()}
        tabs = {(s["brand"], s["tab"]): s for s in store.statuses()}
    return rows, tabs


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preview(workbook, candidate, *, profiles_dir=ROOT / "profiles", controls_dir=ROOT / "fixtures/run1"):
    """Use the candidate for its named brand only, then compare every report value and locator."""
    brand = load_profile(candidate)["brand"]
    if workbook.stem != brand:
        raise ValueError(f"Expected {brand}.xlsx for this candidate")
    profiles = {p.stem: p for p in profiles_dir.glob("*.yaml")}
    sources = {p.stem: p for p in controls_dir.glob("*.xlsx")}
    if not sources:
        raise ValueError(f"No control workbooks in {controls_dir}")
    sources[brand] = workbook
    missing = (sources.keys() - {brand}) - profiles.keys()
    if missing:
        raise ValueError(f"Missing control profiles for {', '.join(sorted(missing))}")

    # Detect changing files, including the candidate being reviewed, during replay.
    inputs = {*sources.values(), *profiles.values(), candidate}
    before_hashes = {path: _sha(path) for path in inputs}
    old, old_tabs = _snapshot(sources, profiles)
    new, new_tabs = _snapshot(sources, {**profiles, brand: candidate})
    if any(_sha(path) != digest for path, digest in before_hashes.items()):
        raise ValueError("Input changed during preview. Repeat with stable files.")

    changes = []
    for key in sorted(old.keys() | new.keys()):
        if old.get(key) != new.get(key):
            changes.append({"brand": key[0], "tab": key[1], "item_ref": key[2],
                            "before": old.get(key), "after": new.get(key)})
    comparisons = []
    for key in sorted(old_tabs.keys() | new_tabs.keys()):
        comparisons.append({"brand": key[0], "tab": key[1], "before": old_tabs.get(key),
                            "after": new_tabs.get(key)})
    unaffected = {}
    for control in sorted(sources.keys() - {brand}):
        changed_tabs = [t["tab"] for t in comparisons
                        if t["brand"] == control and t["before"] != t["after"]]
        changed_rows = sum(c["brand"] == control for c in changes)
        unaffected[control] = {
            "sha": before_hashes[sources[control]],
            "identical": not changed_rows and not changed_tabs,
            "changed_rows": changed_rows, "changed_tabs": changed_tabs,
        }
    return {
        "brand": brand, "workbook_sha": before_hashes[workbook],
        "previous_profile_sha": before_hashes.get(profiles.get(brand)),
        "candidate_profile_sha": before_hashes[candidate],
        "row_counts": {"before": len(old), "after": len(new)},
        "tabs": comparisons, "row_changes": changes, "other_brands": unaffected,
    }


def summary(report):
    counts = report["row_counts"]
    changes = report["row_changes"]
    added = sum(delta["before"] is None for delta in changes)
    removed = sum(delta["after"] is None for delta in changes)
    print(f"{report['brand']} | workbook SHA-256 {report['workbook_sha']}")
    print(f"Candidate profile SHA-256 {report['candidate_profile_sha']}")
    print(f"Accepted rows across input set: {counts['before']} -> {counts['after']} "
          f"({added} added, {len(changes) - added - removed} changed, {removed} removed)")
    for pair in report["tabs"]:
        if pair["brand"] != report["brand"]:
            continue
        states = []
        for side in ("before", "after"):
            tab = pair[side]
            if tab is None:
                states.append("unregistered")
            elif tab["category"]:
                states.append(f"{tab['category']} at {tab['cell']} = {tab['value']!r}")
            else:
                states.append(f"{tab['row_count']} accepted")
        print(f"  {pair['tab']}: {states[0]} -> {states[1]}")
    for delta in changes:
        previous, proposed = delta["before"], delta["after"]
        fields = list((proposed or previous)["lineage"])
        if previous and proposed:
            fields = [f for f in fields if previous[f] != proposed[f]
                      or previous["lineage"][f] != proposed["lineage"][f]]
        def describe(row):
            if not row:
                return "absent"
            return ", ".join(f"{f}={row[f]!r} ({row['lineage'][f]})" for f in fields)
        print(f"  {delta['tab']}/{delta['item_ref']}: {describe(previous)} -> {describe(proposed)}")
    print("Other brands:")
    for name, comparison in report["other_brands"].items():
        print(f"  {name}: {'identical' if comparison['identical'] else 'changed'}")


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("workbook", type=Path)
    cli.add_argument("candidate", type=Path)
    cli.add_argument("--profiles", type=Path, default=ROOT / "profiles",
                     help="Directory containing the before profiles")
    cli.add_argument("--controls", type=Path, default=ROOT / "fixtures/run1",
                     help="Directory of control workbooks; the target overrides its own copy")
    cli.add_argument("--json", action="store_true", help="Print full structured comparison")
    args = cli.parse_args()
    result = preview(args.workbook, args.candidate, profiles_dir=args.profiles, controls_dir=args.controls)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        summary(result)


if __name__ == "__main__":
    main()
