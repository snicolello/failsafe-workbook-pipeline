from datetime import date

import pytest
from openpyxl import Workbook

from pipeline.model import Rejection
from pipeline.parser import FIELDS, parse_tab


SHA = "e" * 64


def table():
    sheet = Workbook().active
    sheet.title = "Ridge"
    sheet.append(FIELDS)
    sheet.append(("F-1", "Spring", "Fit", date(2027, 4, 6), "Assembly"))
    region = {"headers": [1], "columns": {f: [f] for f in FIELDS}}
    profile = {"brand": "test", "stages": ["Fit"], "tabs": {"Ridge": {"regions": [region]}}}
    return sheet, profile


def test_flat_table_date_lineage_and_safe_whitespace():
    sheet, profile = table()
    sheet["D1"] = "  TARGET_DATE  "
    row, = parse_tab(sheet, profile, SHA)
    assert row["target_date"] == "2027-04-06"
    assert (row["sha"], row["tab"]) == (SHA, "Ridge")
    assert row["lineage"] == dict(zip(FIELDS, ("A2", "B2", "C2", "D2", "E2")))


@pytest.mark.parametrize(
    ("coordinate", "value", "category"),
    [
        ("D1", "Needed by", "structural_drift"),
        ("F1", "Unexpected metric", "ambiguous_columns"),
        ("F1", "target_date", "ambiguous_columns"),
        ("F2", "unexpected value", "ambiguous_columns"),
        ("A2", "", "identity_ambiguity"),
        ("C2", "Pending discussion", "unrecognized_value"),
        ("D2", "2027-02-30", "unrecognized_value"),
        ("D2", "=TODAY()", "processing_failure"),
        ("D2", "#REF!", "processing_failure"),
        ("E2", None, "unrecognized_value"),
    ],
)
def test_failures_cite_actual_cell(coordinate, value, category):
    sheet, profile = table()
    sheet[coordinate] = value
    with pytest.raises(Rejection) as caught:
        parse_tab(sheet, profile, SHA)
    assert caught.value.category == category
    assert caught.value.cell == coordinate
    assert caught.value.value == ("" if value is None else str(value))


def test_row_identity_spans_regions():
    sheet, profile = table()
    first = profile["tabs"]["Ridge"]["regions"][0]
    first["end_row"] = 2
    profile["tabs"]["Ridge"]["regions"].append({"headers": [3], "columns": first["columns"]})
    sheet.append(FIELDS)
    sheet.append(("F-1", "Fall", "Fit", "2027-04-20", "Packing"))
    with pytest.raises(Rejection) as caught:
        parse_tab(sheet, profile, SHA)
    assert (caught.value.category, caught.value.cell) == ("identity_ambiguity", "A4")


def test_out_of_region_data_is_visible():
    sheet, profile = table()
    profile["tabs"]["Ridge"]["regions"][0]["end_row"] = 2
    sheet["A3"] = "F-2"
    with pytest.raises(Rejection) as caught:
        parse_tab(sheet, profile, SHA)
    assert (caught.value.category, caught.value.cell) == ("structural_drift", "A3")


def test_multiple_dates_cannot_choose_a_stage():
    sheet, profile = table()
    region = profile["tabs"]["Ridge"]["regions"][0]
    del region["columns"]["stage"], region["columns"]["target_date"]
    profile["stages"].append("Release")
    region["milestones"] = {"Fit": ["Fit due"], "Release": ["Release due"]}
    sheet["C1"], sheet["D1"] = "Fit due", "Release due"
    sheet["C2"] = date(2027, 1, 28)
    with pytest.raises(Rejection) as caught:
        parse_tab(sheet, profile, SHA)
    assert (caught.value.category, caught.value.cell) == ("unrecognized_value", "D2")
    sheet["D2"] = None
    row, = parse_tab(sheet, profile, SHA)
    assert (row["stage"], row["target_date"]) == ("Fit", "2027-01-28")
    assert (row["lineage"]["stage"], row["lineage"]["target_date"]) == ("C1", "C2")
