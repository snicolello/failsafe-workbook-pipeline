"""Configuration errors invalidate the proposal before any tab decision is saved."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from pipeline.parser import validate_profile
from pipeline.run import ingest, load_profile
from pipeline.store import Store


ROOT = Path(__file__).resolve().parents[1]


def test_invalid_final_tab_leaves_the_store_empty(tmp_path):
    profile = load_profile(ROOT / "profiles/slate-finch.yaml")
    # Release sorts first and is valid. Sample cannot derive 'Bogus' from its own title.
    profile["tabs"]["Sample"]["regions"][0]["from_tab"]["stage"] = "Bogus"
    profile_path = tmp_path / "candidate.yaml"
    profile_path.write_text(yaml.safe_dump(profile), encoding="utf8")
    with Store(":memory:") as store:
        with pytest.raises(ValueError, match="Invalid title mapping for 'Sample'"):
            ingest(store, ROOT / "fixtures/run1/slate-finch.xlsx", profile_path, "2026-01-01")
        assert store.current_rows() == []
        assert store.statuses() == []
        assert store.connection.execute("SELECT count(*) FROM attempts").fetchone() == (0,)


@pytest.mark.parametrize(
    "defect",
    ["missing field", "duplicate source", "conflicting header aliases", "nonconsecutive headers",
     "overlapping regions", "unbounded intermediate region", "empty region", "outside worksheet"],
)
def test_impossible_mappings_are_configuration_errors(defect):
    profile = load_profile(ROOT / "profiles/copper-rill.yaml")
    first, second = profile["tabs"]["East"]["regions"]
    if defect == "missing field":
        del first["columns"]["season"]
    elif defect == "duplicate source":
        first["from_tab"] = {"season": "East"}
    elif defect == "conflicting header aliases":
        profile["aliases"] = {"owner": ["  SHIP  SEASON "]}
    elif defect == "nonconsecutive headers":
        first["headers"] = [1, 3]
    elif defect == "overlapping regions":
        second["headers"] = [first["end_row"]]
    elif defect == "unbounded intermediate region":
        del first["end_row"]
    elif defect == "empty region":
        first["end_row"] = first["headers"][-1]
    else:
        second["headers"] = [1_048_576]
    with pytest.raises(ValueError):
        validate_profile(profile)


def test_milestone_names_and_pair_grammar_use_the_same_runtime_contract():
    profile = load_profile(ROOT / "profiles/bracken-ferry.yaml")
    region = profile["tabs"]["Fabric"]["regions"][0]
    original = deepcopy(region["milestones"])
    region["milestones"]["Unconfirmed"] = region["milestones"].pop("Fit")
    with pytest.raises(ValueError, match="Milestones outside stage vocabulary"):
        validate_profile(profile)
    region["milestones"] = original
    region["paired_rows"] = True
    with pytest.raises(ValueError, match="five directly mapped columns"):
        validate_profile(profile)
