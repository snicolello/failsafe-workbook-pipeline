"""Turn a complete worksheet into five-field records with source coordinates."""

from datetime import date, datetime

from .model import Rejection


FIELDS = ("item_ref", "season", "stage", "target_date", "owner")


def _present(value):
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _label(value):
    return " ".join(str(value).split()).casefold()


def _reject(category, cell, message):
    raise Rejection(category, cell.coordinate, "" if cell.value is None else str(cell.value), message)


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


def _header_parts(ws, header_rows, column):
    """A merged parent contributes its anchor text to every child header."""
    parts = []
    for row in header_rows:
        cell = ws.cell(row, column)
        if not _present(cell.value):
            for merged in ws.merged_cells.ranges:
                if cell.coordinate in merged:
                    cell = ws.cell(merged.min_row, merged.min_col)
                    break
        if _present(cell.value) and (not parts or cell.coordinate != parts[-1].coordinate):
            parts.append(cell)
    return parts


def _column_map(region, aliases):
    labels = {}
    for field, names in region["columns"].items():
        labels[field] = [*names, *aliases.get(field, [])]
    for stage, names in region.get("milestones", {}).items():
        labels[("milestone", stage)] = names

    lookup = {}
    for field, names in labels.items():
        for name in names:
            key = _label(name)
            if not key or lookup.setdefault(key, field) != field:
                raise ValueError(f"Blank or conflicting profile header alias: {name!r}")
    return labels, lookup


def _match_headers(ws, region, aliases):
    labels, lookup = _column_map(region, aliases)
    columns = {}
    header_cells = {}
    unknown = []
    for col in range(1, ws.max_column + 1):
        parts = _header_parts(ws, region["headers"], col)
        if not parts:
            continue
        path = " / ".join(str(cell.value) for cell in parts)
        field = lookup.get(_label(path))
        if field is None:
            unknown.append(parts[-1])
            continue
        if field in columns:
            _reject("ambiguous_columns", parts[-1], "Two source columns map to the same field")
        columns[field] = col
        header_cells[field] = parts[-1]
    missing = labels.keys() - columns.keys()
    if missing:
        location = unknown[0] if unknown else ws.cell(region["headers"][-1], 1)
        expected = ", ".join(labels[key][0] for key in labels if key in missing)
        _reject("structural_drift", location, f"Expected header(s): {expected}")
    if unknown:
        _reject("ambiguous_columns", unknown[0], "Column is outside this region's field map")
    return columns, header_cells


def _check_sources(title, region, stages):
    sources = list(region["columns"])
    if region.get("paired_rows") and set(sources) != set(FIELDS):
        raise ValueError("Paired rows require five directly mapped columns")
    for field, label in region.get("from_tab", {}).items():
        if label != title or (field == "stage" and label not in stages):
            raise ValueError(f"Invalid title mapping for {title!r}")
        sources.append(field)
    if "section_field" in region:
        sources.append(region["section_field"])
    if "milestones" in region:
        if region["milestones"].keys() - set(stages):
            raise ValueError(f"Milestones outside stage vocabulary in {title!r}")
        sources.extend(("stage", "target_date"))
    if sorted(sources) != sorted(FIELDS):
        raise ValueError(f"Each field needs exactly one source in {title!r}")


def _check_regions(title, profile):
    next_row = 1
    regions = profile["tabs"][title]["regions"]
    for index, region in enumerate(regions):
        rows = region["headers"]
        if rows[0] < next_row or any(b != a + 1 for a, b in zip(rows, rows[1:])):
            raise ValueError(f"Overlapping or nonconsecutive profile headers in {title!r}")
        end = region.get("end_row")
        if end is None and index < len(regions) - 1:
            raise ValueError(f"Each non-final region needs an end_row in {title!r}")
        if rows[-1] >= 1_048_576 or (end is not None and not rows[-1] < end <= 1_048_576):
            raise ValueError(f"Region must contain at least one legal Excel data row in {title!r}")
        if end is not None:
            next_row = end + 1
        _check_sources(title, region, profile["stages"])
        _column_map(region, profile.get("aliases", {}))


def validate_profile(profile):
    """Check cross-field rules for every declared tab before any ingest decision."""
    if any(stage != stage.strip() or not stage for stage in profile["stages"]):
        raise ValueError("Stage names must be nonempty, trimmed text")
    titles = set()
    for title in profile["tabs"]:
        if (not isinstance(title, str) or not title.strip() or len(title) > 31
                or any(char in title for char in "[]:*?/\\") or title.casefold() in titles):
            raise ValueError(f"Invalid or duplicate worksheet title: {title!r}")
        titles.add(title.casefold())
        _check_regions(title, profile)


def _banner_rows(ws, start, stop, allow_title):
    for index in range(start, stop):
        populated = [c for c in ws[index] if _present(c.value)]
        if not populated:
            continue
        if allow_title and len(populated) == 1 and populated[0].column == 1:
            if populated[0].data_type == "s":
                continue
        _reject("structural_drift", populated[0], "Data outside the declared table region")


def _region_rows(ws, region, columns, end_row):
    """An opted-in region may split one complete item across two adjacent lines."""
    rows = ws.iter_rows(min_row=region["headers"][-1] + 1, max_row=end_row)
    if not region.get("paired_rows"):
        yield from rows
        return
    id_index = columns["item_ref"] - 1
    details = {col - 1 for field, col in columns.items() if field != "item_ref"}
    for row in rows:
        occupied = {index for index, cell in enumerate(row) if _present(cell.value)}
        if occupied != {id_index}:
            yield row
            continue
        anchor = row[id_index]
        continuation = next(rows, ())
        present = {index for index, cell in enumerate(continuation) if _present(cell.value)}
        if present != details:
            _reject("identity_ambiguity", anchor,
                    "Reference must be followed immediately by exactly its four detail cells")
        # Keep the original cells, including the anchor, so each field traces to its own row.
        combined = list(continuation)
        combined[id_index] = anchor
        yield combined


def _parse_region(ws, profile, region, end_row):
    stages = profile["stages"]
    columns, headers = _match_headers(ws, region, profile.get("aliases", {}))
    allowed = set(columns.values())
    section = None
    count = 0
    for row in _region_rows(ws, region, columns, end_row):
        populated = [c for c in row if _present(c.value)]
        if not populated:
            continue
        if region.get("section_field") and len(populated) == 1 and populated[0].column == 1:
            candidate = populated[0]
            if candidate.value in stages:
                section = candidate
                continue
        for cell in populated:
            if cell.column not in allowed:
                _reject("ambiguous_columns", cell, "Populated cell has no mapped column")
        values = dict(region.get("from_tab", {}))
        lineage = {field: "@title" for field in values}
        if region.get("section_field"):
            if section is None:
                _reject("structural_drift", populated[0], "Item appears before a governed section label")
            values["stage"] = section.value
            lineage["stage"] = section.coordinate
        if "milestones" in region:
            dated = [key for key in columns if isinstance(key, tuple)
                     and _present(row[columns[key] - 1].value)]
            if len(dated) != 1:
                if dated:
                    evidence = row[columns[dated[-1]] - 1]
                else:
                    evidence = row[columns[("milestone", next(iter(region["milestones"])))] - 1]
                _reject("unrecognized_value", evidence, "Expected exactly one active milestone date")
            milestone, = dated
            date_cell = row[columns[milestone] - 1]
            values["stage"] = milestone[1]
            lineage["stage"] = headers[milestone].coordinate
            values["target_date"] = _read_value("target_date", date_cell, stages)
            lineage["target_date"] = date_cell.coordinate

        id_cell = row[columns["item_ref"] - 1]
        if len(populated) == 1 and populated[0] == id_cell:
            _reject("identity_ambiguity", id_cell, "Reference-only row cannot identify a complete item")
        for field in FIELDS:
            if field in columns:
                cell = row[columns[field] - 1]
                values[field] = _read_value(field, cell, stages)
                lineage[field] = cell.coordinate
        yield dict(brand=profile["brand"], tab=ws.title, **values, lineage=lineage)
        count += 1
    if not count:
        _reject("structural_drift", ws.cell(region["headers"][-1], 1), "No item rows found")


def parse_tab(ws, profile, sha):
    """Return records only after every region on the tab passes the contract."""
    if ws.title not in profile["tabs"]:
        raise Rejection("structural_drift", "@title", ws.title, "Unexpected worksheet title")
    _check_regions(ws.title, profile)
    records = []
    seen = set()
    next_row = 1
    for region in profile["tabs"][ws.title]["regions"]:
        rows = region["headers"]
        _banner_rows(ws, next_row, min(rows[0], ws.max_row + 1), allow_title=(next_row == 1))
        if rows[-1] > ws.max_row:
            _reject("structural_drift", ws.cell(rows[-1], 1), "Worksheet ends before expected header")
        end = region.get("end_row", ws.max_row)
        for record in _parse_region(ws, profile, region, min(end, ws.max_row)):
            ref = record["item_ref"]
            if ref in seen:
                _reject("identity_ambiguity", ws[record["lineage"]["item_ref"]],
                        "Repeated item reference on this worksheet")
            seen.add(ref)
            records.append(dict(record, sha=sha))
        next_row = end + 1
    _banner_rows(ws, next_row, ws.max_row + 1, allow_title=False)
    return records
