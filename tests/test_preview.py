from pathlib import Path

import pytest
import yaml

from pipeline.preview import preview


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
PROFILES = ROOT / "profiles"


def test_repair_and_onboarding_compare_all_rows_and_source_cells(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    changed = FIXTURES / "run2/flintwake.xlsx"
    proposed = FIXTURES / "repairs/flintwake.yaml"
    before_files = {p: p.read_bytes() for p in (changed, proposed, PROFILES / "flintwake.yaml")}
    result = preview(changed, proposed)
    assert result["row_counts"] == {"before": 270, "after": 288}
    assert len(result["row_changes"]) == 18
    assert all(delta["tab"] == "Ridge" and delta["before"] is None for delta in result["row_changes"])
    ridge, = [t for t in result["tabs"] if t["brand"] == "flintwake" and t["tab"] == "Ridge"]
    assert (ridge["before"]["cell"], ridge["before"]["value"]) == ("D1", "Due on")
    first = result["row_changes"][0]["after"]
    assert (first["target_date"], first["lineage"]["target_date"]) == ("2027-05-10", "D2")
    assert first["sha"] == result["workbook_sha"] == ridge["before"]["sha"]
    assert len(result["other_brands"]) == 7
    assert all(c["identical"] for c in result["other_brands"].values())

    onboard = preview(FIXTURES / "run4/gale-stitch.xlsx", FIXTURES / "onboarding/gale-stitch.yaml")
    assert onboard["previous_profile_sha"] is None
    assert onboard["row_counts"] == {"before": 288, "after": 324}
    assert {c["tab"] for c in onboard["row_changes"]} == {"Summit", "Valley"}
    assert len(onboard["row_changes"]) == 36 and len(onboard["other_brands"]) == 8
    assert all(c["identical"] for c in onboard["other_brands"].values())
    assert all(p.read_bytes() == original for p, original in before_files.items())
    assert list(tmp_path.iterdir()) == []


def test_same_count_changed_fields_and_lineage_are_reported(tmp_path):
    # A mistaken swap of two compatible text fields leaves row counts unchanged.
    profile = yaml.safe_load((PROFILES / "flintwake.yaml").read_text())
    columns = profile["tabs"]["Ridge"]["regions"][0]["columns"]
    columns["owner"], columns["season"] = columns["season"], columns["owner"]
    proposed = tmp_path / "candidate.yaml"
    proposed.write_text(yaml.safe_dump(profile), encoding="utf8")
    result = preview(FIXTURES / "run1/flintwake.xlsx", proposed)
    assert result["row_counts"] == {"before": 288, "after": 288}
    assert len(result["row_changes"]) == 36
    for delta in result["row_changes"]:
        before, after = delta["before"], delta["after"]
        assert before["owner"] != after["owner"] == before["season"]
        assert after["lineage"]["owner"] == before["lineage"]["season"]
    assert all(c["identical"] for c in result["other_brands"].values())


def test_wrong_brand_cannot_be_previewed():
    with pytest.raises(ValueError, match="Expected flintwake.xlsx"):
        preview(FIXTURES / "run4/gale-stitch.xlsx", FIXTURES / "repairs/flintwake.yaml")
