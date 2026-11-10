"""Exercise representative workbooks as a reader would receive them."""

from datetime import date, datetime
from hashlib import sha256
from pathlib import Path

import pytest
import yaml
from openpyxl import load_workbook

from fixtures.generate import generate
from pipeline.model import Rejection
from pipeline.parser import FIELDS, parse_tab


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
PROFILES = ROOT / "profiles"


def read_profile(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def read_tab(path, tab, profile):
    book = load_workbook(path)
    try:
        return parse_tab(book[tab], profile, sha256(path.read_bytes()).hexdigest())
    finally:
        book.close()


def test_checked_in_sources_are_reproducible(tmp_path):
    generate(tmp_path)
    expected = {p.relative_to(FIXTURES) for p in FIXTURES.glob("run*/*.xlsx")}
    assert len(expected) == 14
    assert {p.relative_to(tmp_path) for p in tmp_path.glob("run*/*.xlsx")} == expected
    for name in expected:
        assert (tmp_path / name).read_bytes() == (FIXTURES / name).read_bytes(), str(name)


def test_all_baseline_layouts_resolve_each_value_to_its_source():
    sources = sorted((FIXTURES / "run1").glob("*.xlsx"))
    assert len(sources) == 8
    for path in sources:
        profile = read_profile(PROFILES / f"{path.stem}.yaml")
        book = load_workbook(path)
        try:
            assert len(book.sheetnames) == 2
            assert set(book.sheetnames) == set(profile["tabs"])
            for sheet in book:
                sha = sha256(path.read_bytes()).hexdigest()
                records = parse_tab(sheet, profile, sha)
                assert len(records) == len({r["item_ref"] for r in records}) == 18
                for record in records:
                    assert (record["brand"], record["tab"], record["sha"]) == (
                        path.stem, sheet.title, sha
                    )
                    for field in FIELDS:
                        address = record["lineage"][field]
                        raw = sheet.title if address == "@title" else sheet[address].value
                        if isinstance(raw, datetime):
                            raw = raw.date()
                        if isinstance(raw, date):
                            raw = raw.isoformat()
                        if field == "stage" and path.stem == "bracken-ferry":
                            assert raw == f"{record[field]} date"
                        else:
                            assert raw == record[field]
        finally:
            book.close()


def test_alias_repair_is_brand_scoped_and_transfers_to_another_tab():
    original = read_profile(PROFILES / "flintwake.yaml")
    repaired = read_profile(FIXTURES / "repairs/flintwake.yaml")
    assert {k: v for k, v in repaired.items() if k != "aliases"} == original
    assert repaired["aliases"] == {"target_date": ["Due on"]}
    changed = FIXTURES / "run2/flintwake.xlsx"
    with pytest.raises(Rejection) as error:
        read_tab(changed, "Ridge", original)
    assert (error.value.category, error.value.cell, error.value.value) == (
        "structural_drift", "D1", "Due on"
    )
    assert read_tab(changed, "Ridge", repaired)[0]["target_date"] == "2027-05-10"
    assert read_tab(FIXTURES / "run4/flintwake.xlsx", "Basin", repaired)[0]["target_date"] == "2027-06-14"
    # The exact same spelling on a different brand's worksheet must still be refused.
    foreign = read_profile(PROFILES / "moraine-thread.yaml")
    book = load_workbook(FIXTURES / "run1/moraine-thread.xlsx")
    try:
        sheet = book["Shells"]
        sheet["E3"] = "Due on"
        with pytest.raises(Rejection) as foreign_error:
            parse_tab(sheet, foreign, "synthetic-test")
        assert (foreign_error.value.category, foreign_error.value.cell) == ("structural_drift", "E3")
    finally:
        book.close()


def test_new_brand_combines_existing_offset_and_section_rules():
    profile = read_profile(FIXTURES / "onboarding/gale-stitch.yaml")
    path = FIXTURES / "run4/gale-stitch.xlsx"
    for name in ("Summit", "Valley"):
        records = read_tab(path, name, profile)
        assert len(records) == 18
        assert {r["stage"] for r in records} == {"Sample", "Fit", "Release"}
