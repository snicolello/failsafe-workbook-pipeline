from pipeline.run import ROOT, ingest
from pipeline.store import Store


def test_drift_preserves_rows_and_accepts_the_changed_sibling():
    profile = ROOT / "profiles/flintwake.yaml"
    with Store(":memory:") as store:
        ingest(store, ROOT / "fixtures/run1/flintwake.xlsx", profile, "2026-06-01")
        before = store.current_rows()
        path = ROOT / "fixtures/run2/flintwake.xlsx"
        assert ingest(store, path, profile, "2026-06-02") == 2
        after = store.current_rows()
        assert [r for r in before if r["tab"] == "Ridge"] == [r for r in after if r["tab"] == "Ridge"]
        sibling = next(r for r in after if r["tab"] == "Basin" and r["item_ref"] == "FW-019")
        assert sibling["target_date"] == "2027-04-12"
        event, = store.exceptions()
        assert (event["cell"], event["value"], event["category"]) == ("D1", "Due on", "structural_drift")
        assert ingest(store, path, profile, "2026-06-03") == 0
        assert store.current_rows() == after and store.exceptions() == [event]
