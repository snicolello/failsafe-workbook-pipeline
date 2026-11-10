"""Map a workbook tab to the five agreed fields and their source locations."""

from datetime import date, datetime

from openpyxl.utils import get_column_letter

from .model import Rejection


FIELDS = ("item_ref", "season", "stage", "target_date", "owner")


def _present(value):
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _label(value):
    return " ".join(str(value).split()).casefold()


def _reject(category, cell, message):
    raise Rejection(category, cell.coordinate, str(cell.value or ""), message)


def _read_value(field, cell, stages):
    value = cell.value
    if not _present(value):
        category = "identity_ambiguity" if field == "item_ref" else "unrecognized_value"
        _reject(category, cell, f"Missing required {field}")
    if cell.data_type in ("e", "f"):
        _reject("processing_failure", cell, "A formula or Excel error cannot supply a trusted value")
    if field == "target_date":
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            try:
                parsed = date.fromisoformat(value.strip())
                if value.strip() == parsed.isoformat():
                    return parsed.isoformat()
            except ValueError:
                pass
        _reject("unrecognized_value", cell, "Expected an Excel date or YYYY-MM-DD")
    if not isinstance(value, str):
        _reject("unrecognized_value", cell, f"Expected text for {field}")
    value = value.strip()
    if field == "stage" and value not in stages:
        _reject("unrecognized_value", cell, "Stage is outside this profile's governed vocabulary")
    return value


def _flat_columns(ws, region, aliases):
    header_row = region["headers"][0]
    columns = {}
    for cell in ws[header_row]:
        if not _present(cell.value):
            continue
        matches = [
            field for field, names in region["columns"].items()
            if _label(cell.value) in {_label(name) for name in [*names, *aliases.get(field, [])]}
        ]
        if not matches:
            _reject("structural_drift", cell, "Header does not match the profile")
        if len(matches) != 1 or matches[0] in columns:
            _reject("ambiguous_columns", cell, "Header maps ambiguously")
        columns[matches[0]] = cell.column
    for field in FIELDS:
        if field not in columns:
            _reject("structural_drift", ws.cell(header_row, 1), f"Missing header for {field}")
    return columns


def parse_tab(ws, profile, sha):
    """Parse a complete tab. A rejection discards every candidate on the tab."""
    if ws.title not in profile["tabs"]:
        raise Rejection("structural_drift", "@title", ws.title, "Unexpected worksheet title")
    region, = profile["tabs"][ws.title]["regions"]
    columns = _flat_columns(ws, region, profile.get("aliases", {}))
    records = []
    seen = set()
    for row in ws.iter_rows(min_row=region["headers"][0] + 1):
        if not any(_present(cell.value) for cell in row):
            continue
        for cell in row:
            if _present(cell.value) and cell.column not in columns.values():
                _reject("ambiguous_columns", cell, "Populated cell has no mapped column")
        cells = {field: row[col - 1] for field, col in columns.items()}
        values = {field: _read_value(field, cell, profile["stages"]) for field, cell in cells.items()}
        if values["item_ref"] in seen:
            _reject("identity_ambiguity", cells["item_ref"], "Repeated item reference on this worksheet")
        seen.add(values["item_ref"])
        lineage = {field: cell.coordinate for field, cell in cells.items()}
        records.append(dict(brand=profile["brand"], tab=ws.title, sha=sha, **values, lineage=lineage))
    if not records:
        _reject("structural_drift", ws.cell(region["headers"][0], 1), "No item rows found")
    return records
