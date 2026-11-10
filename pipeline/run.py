"""Compare the observed tabs with the contract, then publish each independent decision."""

import hashlib
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from .cleanup import read_source
from .model import Rejection
from .parser import parse_tab, validate_profile
from .store import Store

ROOT = Path(__file__).resolve().parents[1]
PARSER_VERSION = "2"


def load_profile(path):
    profile = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "profiles/schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(profile)
    validate_profile(profile)
    return profile


def ingest(store: Store, workbook, profile_path, observed_at, *, reviewer=None):
    """Return the number of decisions written. Refuse a profile belonging to another source."""
    workbook = Path(workbook)
    profile = load_profile(profile_path)
    brand = profile["brand"]
    if workbook.stem != brand:
        raise ValueError(f"Expected {brand}.xlsx for this profile")
    encoded = json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
    fingerprint = hashlib.sha256(encoded).hexdigest()
    sha, book, failure = read_source(workbook)
    previous = {s["tab"]: s for s in store.statuses() if s["brand"] == brand}
    expected = set(profile["tabs"])
    observed = set(book.sheetnames if book else ())
    tabs = sorted(expected | observed | set(previous))
    changed = 0
    try:
        for tab in tabs:
            prior = previous.get(tab, {})
            args = (brand, tab, sha, fingerprint, PARSER_VERSION, observed_at)
            if book and tab not in expected | observed and prior["accepted_sha"] is None:
                # A now-absent, uncontracted tab with no accepted history has left the feed.
                changed += store.apply(*args, retired=True)
                continue
            if store.is_current(brand, tab, sha, fingerprint, PARSER_VERSION):
                continue
            try:
                if failure is not None:
                    raise failure
                if tab not in book.sheetnames:
                    raise Rejection("structural_drift", "@title", tab, "Expected worksheet is absent.")
                if tab not in expected:
                    raise Rejection("structural_drift", "@title", tab, "Worksheet needs a profile.")
                records = parse_tab(book[tab], profile, sha)
            except Rejection as rejected:
                accepted_sha = prior.get("accepted_sha")
                finding = {
                    "reviewer": "deterministic",
                    "sha_comparison": "unchanged" if sha == accepted_sha else "different" if accepted_sha else "first observation",
                    "cell": rejected.cell, "quote": str(rejected.value),
                    "explanation": rejected.message,
                }
                if sha == prior.get("sha"):
                    finding["review_status"] = "Unchanged since previous attempt"
                elif reviewer and sha != accepted_sha:
                    try:
                        finding = reviewer(brand, tab, sha, rejected, finding)
                    except Exception as exc:
                        # Optional commentary cannot interrupt a tab decision or sibling load.
                        finding["review_status"] = f"Review unavailable ({type(exc).__name__})"
                changed += store.apply(*args, rejection=rejected, finding=finding)
            else:
                changed += store.apply(*args, records=records)
    finally:
        if book:
            book.close()
    return changed
