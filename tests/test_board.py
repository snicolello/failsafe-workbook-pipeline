from html.parser import HTMLParser

from pipeline.board import render_board


class BoardReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.tags = []

    def handle_data(self, data):
        if data.strip():
            self.text.append(data.strip())

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


def test_board_distinguishes_accepted_and_rejected_sources(tmp_path):
    accepted = "a" * 64
    rejected = "b" * 64
    hostile = "<script>alert(1)</script>"
    status = {
        "brand": "test-brand", "tab": "Ridge", "status": "fallback", "category": "structural_drift",
        "sha": rejected, "accepted_sha": accepted, "observed_at": "2026-11-09",
        "accepted_at": "2026-11-01", "cell": "D1", "value": hostile,
        "message": "Unexpected heading", "finding": {"source": "Ridge!D1"},
    }
    record = {
        "brand": "test-brand", "tab": "Ridge", "sha": accepted, "item_ref": "R-4",
        "season": "Spring", "stage": "Cut", "target_date": "2027-03-17", "owner": "River",
        "lineage": dict(zip(("item_ref", "season", "stage", "target_date", "owner"), ("A4", "B4", "C4", "D4", "E4"))),
    }
    other = dict(status, status="quarantined", tab="Summit", accepted_sha=None, accepted_at=None)
    current = dict(status, status="current", tab="Basin", sha=accepted, accepted_sha=accepted)
    path = render_board([current, status, other], [record], tmp_path / "demo" / "report.html")
    board = BoardReader()
    board.feed(path.read_text(encoding="utf-8"))
    contents = " ".join(board.text)
    assert "Accepted records 1 Current tabs 1 Tabs serving last accepted 1 Tabs without accepted data 1" in contents
    assert contents.index("Summit") < contents.index("Ridge test-brand") < contents.index("Basin")
    assert "Serving data accepted 2026-11-01" in contents
    assert "Awaiting first acceptance" in contents
    assert "2027-03-17 D4" in contents
    assert "Source D1" in contents and "Ridge!D1" in contents
    assert accepted in contents and rejected in contents
    assert hostile in contents and "script" not in board.tags
    assert board.tags.count("details") == 3
