"""Small deterministic workbook factory used by the scenario generator."""

from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


STAGES = ("Sample", "Fit", "Release")
OWNERS = ("Pattern studio", "Materials lab", "Field team", "Assembly desk")
STAMP = datetime(2026, 1, 1)


def new_book():
    book = Workbook()
    book.remove(book.active)
    book.properties.creator = "Sedgewater Outfitters"
    book.properties.created = STAMP
    return book


def row_values(prefix: str, sheet_index: int, index: int):
    """Return an independently identifiable item at a different point in its cycle."""
    serial = 18 * sheet_index + index + 1
    return (
        f"{prefix}-{serial:03d}",
        ("Spring", "Fall")[(index // 3 + sheet_index) % 2],
        STAGES[(index + sheet_index) % len(STAGES)],
        date(2027, 1, 4) + timedelta(days=(serial * 3 + len(prefix)) % 94),
        OWNERS[(index + sheet_index) % len(OWNERS)],
    )


def header(sheet, row, labels):
    for col, label in enumerate(labels, 1):
        cell = sheet.cell(row, col, label)
        cell.fill = PatternFill("solid", fgColor="254C4B")
        cell.font = Font(name="Calibri", bold=True, color="FFFFFF")
        cell.alignment = Alignment(vertical="center")
    sheet.row_dimensions[row].height = 20
    sheet.freeze_panes = f"A{row + 1}"


def flat_book():
    book = new_book()
    for number, name in enumerate(("Ridge", "Basin")):
        sheet = book.create_sheet(name)
        header(sheet, 1, ("Item ref", "Season", "Stage", "Target date", "Owner"))
        for index in range(18):
            sheet.append(row_values("FW", number, index))
    return book


def save_book(book, path: Path):
    """Canonicalize volatile package timestamps so unchanged XLSX bytes hash equally."""
    for sheet in book:
        sheet.sheet_view.showGridLines = False
        for cells in sheet.columns:
            width = max(len(str(cell.value or "")) for cell in cells)
            sheet.column_dimensions[get_column_letter(cells[0].column)].width = min(54, max(15, width + 4))
        for cells in sheet.iter_rows():
            for cell in cells:
                if isinstance(cell.value, date):
                    cell.number_format = "yyyy-mm-dd"
    stream = BytesIO()
    book.save(stream)
    path.parent.mkdir(parents=True, exist_ok=True)
    # openpyxl refreshes the core modified time during save. ZIP also dates each entry.
    with ZipFile(stream) as src, ZipFile(path, "w") as out:
        for name in sorted(src.namelist()):
            payload = src.read(name)
            if name == "docProps/core.xml":
                payload = re.sub(rb"(<dcterms:modified\b[^>]*>)[^<]+",
                                 rb"\g<1>2026-01-01T00:00:00Z", payload)
            member = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            member.compress_type = ZIP_DEFLATED
            member.external_attr = 0o600 << 16
            out.writestr(member, payload)
