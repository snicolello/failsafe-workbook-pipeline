"""Exercise the public ingest path with Excel packages and a real acceptance store."""

import hashlib
import subprocess
from datetime import date
from unittest.mock import Mock
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import yaml
from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, Reference

from pipeline.review import claude_review
from pipeline.run import ROOT, ingest
from pipeline.store import Store


PROFILE = ROOT / "profiles/flintwake.yaml"
D1, D2, D3 = "2026-03-01", "2026-03-02", "2026-03-03"


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "flintwake.xlsx"
    book = Workbook()
    ridge = book.active
    ridge.title = "Ridge"
    basin = book.create_sheet("Basin")
    for sheet in (ridge, basin):
        sheet.append(["Item ref", "Season", "Stage", "Target date", "Owner"])
        sheet.append(["T-7", "Spring", "Sample", date(2026, 3, 20), "Rowan"])
    book.save(path)
    book.close()
    return path


def edit(path, change):
    book = load_workbook(path)
    try:
        change(book)
        book.save(path)
    finally:
        book.close()


def statuses(db):
    return {s["tab"]: s for s in db.statuses()}


def test_lineage_uses_original_bytes_and_points_to_changed_date(source):
    with Store(":memory:") as db:
        assert ingest(db, source, PROFILE, D1) == 2
        old_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        edit(source, lambda book: setattr(book["Basin"]["D2"], "value", date(2026, 4, 3)))
        new_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        assert new_sha != old_sha
        assert ingest(db, source, PROFILE, D2) == 2
        basin, ridge = db.current_rows()
        assert basin["tab"] == "Basin"
        assert basin["sha"] == ridge["sha"] == new_sha
        assert basin["target_date"] == "2026-04-03"
        assert basin["lineage"]["target_date"] == "D2"
        assert ridge["target_date"] == "2026-03-20"


def test_renamed_tab_preserves_missing_tab_and_quarantines_new_name(source):
    with Store(":memory:") as db:
        original = source.read_bytes()
        ingest(db, source, PROFILE, D1)
        edit(source, lambda book: setattr(book["Basin"], "title", "Bay"))
        assert ingest(db, source, PROFILE, D2) == 3
        state = statuses(db)
        assert state["Bay"]["status"] == "quarantined"
        assert state["Basin"]["status"] == "fallback"
        assert state["Bay"]["category"] == state["Basin"]["category"] == "structural_drift"
        assert state["Ridge"]["status"] == "current"
        assert {row["tab"] for row in db.current_rows()} == {"Basin", "Ridge"}
        exceptions = db.exceptions()
        assert len(exceptions) == 2

        source.write_bytes(original)
        assert ingest(db, source, PROFILE, D3) == 3
        assert [(s["tab"], s["status"]) for s in db.statuses()] == [
            ("Basin", "current"), ("Ridge", "current"),
        ]
        assert db.exceptions() == exceptions
        assert ingest(db, source, PROFILE, D3) == 0


def test_profile_recheck_on_previously_rejected_bytes_skips_external_call(source, tmp_path):
    with Store(":memory:") as db:
        ingest(db, source, PROFILE, D1)
        edit(source, lambda book: setattr(book["Basin"]["C2"], "value", "Unscheduled"))
        called = Mock(side_effect=lambda brand, tab, sha, rejected, finding: finding)
        ingest(db, source, PROFILE, D2, reviewer=called)

        profile = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
        profile["aliases"] = {"owner": ["Steward"]}
        candidate = tmp_path / "candidate.yaml"
        candidate.write_text(yaml.safe_dump(profile), encoding="utf-8")
        assert ingest(db, source, candidate, D3, reviewer=called) == 2
        called.assert_called_once()
        latest = db.exceptions()[-1]
        assert latest["finding"]["reviewer"] == "deterministic"
        assert latest["finding"]["sha_comparison"] == "different"
        assert latest["finding"]["review_status"] == "Unchanged since previous attempt"
        assert latest["finding"]["quote"] == "Unscheduled"


def test_corrupt_archive_keeps_each_accepted_tab_visible(source):
    with Store(":memory:") as db:
        ingest(db, source, PROFILE, D1)
        accepted = db.current_rows()
        source.write_bytes(source.read_bytes()[:37])
        ingest(db, source, PROFILE, D2)
        assert db.current_rows() == accepted
        assert {s["category"] for s in db.statuses()} == {"processing_failure"}
        assert {s["status"] for s in db.statuses()} == {"fallback"}
        assert {e["sha"] for e in db.exceptions()} == {hashlib.sha256(source.read_bytes()).hexdigest()}


def test_formula_is_evidence_and_same_sha_replay_skips_reviewer(source):
    with Store(":memory:") as db:
        called = Mock(side_effect=lambda brand, tab, sha, rejected, finding: finding)
        ingest(db, source, PROFILE, D1, reviewer=called)
        called.assert_not_called()
        edit(source, lambda book: setattr(book["Basin"]["D2"], "value", "=TODAY()"))
        ingest(db, source, PROFILE, D2, reviewer=called)
        called.assert_called_once()
        assert ingest(db, source, PROFILE, D3, reviewer=called) == 0
        called.assert_called_once()
        finding, = db.exceptions()
        assert (finding["category"], finding["cell"], finding["value"]) == (
            "processing_failure", "D2", "=TODAY()"
        )
        assert statuses(db)["Ridge"]["status"] == "current"
        assert statuses(db)["Basin"]["status"] == "fallback"


def test_unchanged_accepted_sha_and_changed_profile_skip_content_review(source, tmp_path):
    with Store(":memory:") as db:
        ingest(db, source, PROFILE, D1)
        profile = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
        profile["stages"] = ["Fit", "Release"]
        new_contract = tmp_path / "revised.yaml"
        new_contract.write_text(yaml.safe_dump(profile), encoding="utf-8")
        called = Mock()
        ingest(db, source, new_contract, D2, reviewer=called)
        called.assert_not_called()
        assert {s["finding"]["sha_comparison"] for s in db.statuses()} == {"unchanged"}
        assert {s["status"] for s in db.statuses()} == {"fallback"}


@pytest.mark.parametrize("mode", ["offline", "missing", "timeout"])
def test_optional_review_availability_cannot_control_acceptance(source, monkeypatch, mode):
    edit(source, lambda book: setattr(book["Basin"]["C2"], "value", "Unscheduled"))
    launch = Mock(side_effect=subprocess.TimeoutExpired("claude", 60))
    monkeypatch.setattr("pipeline.review.subprocess.run", launch)
    monkeypatch.setattr("pipeline.review.shutil.which", lambda _: None if mode == "missing" else "claude")
    with Store(":memory:") as db:
        ingest(db, source, PROFILE, D1, reviewer=None if mode == "offline" else claude_review)
        state = statuses(db)
        assert state["Ridge"]["status"] == "current"
        assert state["Basin"]["status"] == "quarantined"
        finding = state["Basin"]["finding"]
        assert finding["reviewer"] == "deterministic"
        assert finding["cell"] == "C2" and finding["quote"] == "Unscheduled"
        assert launch.call_count == int(mode == "timeout")


def test_chartsheet_in_place_of_expected_worksheet_is_isolated(source):
    def replace_with_chart(book):
        del book["Basin"]
        sheet = book.create_chartsheet("Basin")
        chart = BarChart()
        chart.add_data(Reference(book["Ridge"], min_col=4, min_row=2, max_row=2))
        sheet.add_chart(chart)

    with Store(":memory:") as db:
        ingest(db, source, PROFILE, D1)
        edit(source, replace_with_chart)
        ingest(db, source, PROFILE, D2)
        state = statuses(db)
        assert state["Basin"]["status"] == "fallback"
        assert state["Basin"]["category"] == "processing_failure"
        assert state["Ridge"]["status"] == "current"
        assert state["Ridge"]["accepted_sha"] == hashlib.sha256(source.read_bytes()).hexdigest()


def test_reviewer_exception_cannot_interrupt_sibling(source):
    edit(source, lambda book: setattr(book["Basin"]["C2"], "value", "Unscheduled"))
    reviewer = Mock(side_effect=RuntimeError("review service failed"))
    with Store(":memory:") as db:
        ingest(db, source, PROFILE, D1, reviewer=reviewer)
        state = statuses(db)
        assert state["Ridge"]["status"] == "current"
        assert state["Basin"]["status"] == "quarantined"
        assert state["Basin"]["finding"]["quote"] == "Unscheduled"
        assert state["Basin"]["finding"]["review_status"] == "Review unavailable (RuntimeError)"


@pytest.mark.parametrize("shape", ["extension", "unclosed_xml", "bad_date_style"])
def test_unreadable_worksheet_keeps_healthy_sibling_current(source, tmp_path, shape):
    replacement = tmp_path / "extended.xlsx"
    extension = (b'<extLst><ext uri="{C46BAAF1-EE4E-4890-9601-E0FC44815FEF}">'
                 b'<review xmlns="urn:synthetic:demo">Item on hold</review></ext></extLst>')
    with Store(":memory:") as db:
        ingest(db, source, PROFILE, D1)
        with ZipFile(source) as original, ZipFile(replacement, "w", ZIP_DEFLATED) as out:
            for entry in original.infolist():
                payload = original.read(entry)
                if entry.filename == "xl/worksheets/sheet2.xml":
                    if shape == "extension":
                        payload = payload.replace(b"</worksheet>", extension + b"</worksheet>")
                    elif shape == "unclosed_xml":
                        payload = payload.removesuffix(b"</worksheet>")
                    else:
                        # Well-formed XML can still be undecodable by the Excel reader.
                        payload = payload.replace(b'<c r="D2" s="1"', b'<c r="D2" s="99999"')
                out.writestr(entry, payload)
        source.write_bytes(replacement.read_bytes())
        ingest(db, source, PROFILE, D2)
        state = statuses(db)
        assert state["Basin"]["category"] == "processing_failure"
        assert state["Basin"]["status"] == "fallback"
        assert state["Ridge"]["status"] == "current"
