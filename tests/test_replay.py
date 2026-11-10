import json

from pipeline.scenario import replay
from pipeline.store import Store


def test_four_deliveries_and_repairs_match_the_served_report(tmp_path):
    runs = replay(tmp_path)
    assert [(s["rows"], s["current"], s["fallback"], s["quarantined"]) for s in runs] == [
        (288, 16, 0, 0), (288, 14, 2, 0), (288, 15, 1, 0),
        (288, 15, 1, 0), (288, 16, 0, 0), (324, 18, 0, 0),
    ]
    def read(step, name):
        return json.loads((tmp_path / step / (name + ".json")).read_text(encoding="utf-8"))
    assert len(read("run4", "exceptions")) == 3
    assert [e["category"] for e in read("run4", "exceptions")] == [
        "structural_drift", "unrecognized_value", "identity_ambiguity"
    ]
    before = [r for r in read("run2", "records") if r["brand"] != "flintwake"]
    after = [r for r in read("run2-repaired", "records") if r["brand"] != "flintwake"]
    assert before == after
    with Store(tmp_path / "report.duckdb") as store:
        assert store.current_rows() == read("run4", "records")
        assert store.statuses() == read("run4", "status")
