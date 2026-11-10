import json

from jsonschema import Draft202012Validator, FormatChecker

from demo.save_snapshots import save
from pipeline.run import ROOT


def test_published_evidence_reproduces_from_workbooks(tmp_path):
    save(tmp_path)
    committed = ROOT / "demo/snapshots"
    expected = {p.relative_to(committed) for p in committed.rglob("*") if p.is_file()}
    actual = {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()}
    assert expected == actual
    for rel in actual:
        # Cross-platform line endings are a presentation property.
        assert (tmp_path / rel).read_text(encoding="utf-8") == (committed / rel).read_text(encoding="utf-8"), rel


def test_saved_rows_and_exceptions_match_public_schemas():
    def validator(name):
        schema = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
        return Draft202012Validator(schema, format_checker=FormatChecker())
    records = validator("record.schema.json")
    events = validator("exception.schema.json")
    for path in (ROOT / "demo/snapshots").glob("*/accepted.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            records.validate(json.loads(line))
        for event in json.loads(path.with_name("exceptions.json").read_text(encoding="utf-8")):
            events.validate(event)
