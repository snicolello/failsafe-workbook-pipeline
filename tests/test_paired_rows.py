from pathlib import Path

import pytest

from pipeline.cleanup import read_source
from pipeline.model import Rejection
from pipeline.parser import parse_tab
from pipeline.run import load_profile


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "profiles/copper-rill.yaml"
REPAIR = ROOT / "fixtures/repairs/copper-rill.yaml"
SOURCE = ROOT / "fixtures/run3/copper-rill.xlsx"


def test_real_split_item_requires_region_opt_in_and_preserves_both_source_rows():
    sha, book, failure = read_source(SOURCE)
    assert failure is None
    old, repaired = load_profile(BASELINE), load_profile(REPAIR)
    with pytest.raises(Rejection) as caught:
        parse_tab(book["East"], old, sha)
    assert (caught.value.category, caught.value.cell, caught.value.value) == (
        "identity_ambiguity", "A20", "CR-018",
    )
    rows = parse_tab(book["East"], repaired, sha)
    assert len(rows) == 18
    last = rows[-1]
    assert last["item_ref"] == "CR-018"
    assert last["target_date"] == "2027-05-17"
    assert last["lineage"] == {
        "item_ref": "A20", "season": "E21", "stage": "C21", "target_date": "D21", "owner": "B21",
    }
    assert parse_tab(book["West"], old, sha) == parse_tab(book["West"], repaired, sha)
    # The same shape in the other tab is still refused.
    west = book["West"]
    for col in range(2, 6):
        west.cell(21, col).value = west.cell(20, col).value
        west.cell(20, col).value = None
    with pytest.raises(Rejection, match="Reference-only"):
        parse_tab(west, repaired, sha)


@pytest.mark.parametrize(
    ("cell", "new_value"),
    [
        ("A21", "CR-019"),     # adjacent item is complete and has its own identity
        ("B21", None),         # detail row lacks a required field
        ("F21", "unmapped"),   # accepting this pair would lose data
    ],
)
def test_incomplete_or_overlapping_pair_never_becomes_a_record(cell, new_value):
    sha, book, _ = read_source(SOURCE)
    sheet = book["East"]
    sheet[cell] = new_value
    with pytest.raises(Rejection) as caught:
        parse_tab(sheet, load_profile(REPAIR), sha)
    assert (caught.value.category, caught.value.cell) == ("identity_ambiguity", "A20")


def test_valid_pair_still_obeys_value_contract():
    sha, book, _ = read_source(SOURCE)
    sheet = book["East"]
    sheet["C21"] = "Between stages"
    with pytest.raises(Rejection) as caught:
        parse_tab(sheet, load_profile(REPAIR), sha)
    assert (caught.value.category, caught.value.cell) == ("unrecognized_value", "C21")
