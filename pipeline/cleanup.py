"""Read one immutable input snapshot. Source coordinates always refer to those bytes."""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import warnings
from xml.etree import ElementTree

from openpyxl.reader.excel import ExcelReader
from openpyxl.xml.constants import REL_NS

from .model import Rejection


UNSUPPORTED_OBJECTS = {
    "AlternateContent", "controls", "drawing", "extLst", "legacyDrawing",
    "legacyDrawingHF", "oleObjects", "picture",
}


class _TabReader(ExcelReader):
    """Keep package metadata shared while isolating openpyxl's per-sheet decoder.

    openpyxl 3.1.5 enumerates parser.sheets inside read_worksheets. Restricting
    that list lets us use its full cell, style, merge and relationship handling
    for each tab while preserving the order used by scoped defined names.
    """

    def read_worksheets(self):
        self.failures = {}
        sheets = self.parser.sheets
        try:
            for sheet in sheets:
                title = sheet.name
                if title.casefold() in {s.casefold() for s in self.wb.sheetnames}:
                    raise ValueError("Duplicate sheet titles")
                self.parser.sheets = [sheet]
                try:
                    self._check_part(sheet)
                    with warnings.catch_warnings():
                        # openpyxl warns before discarding some unsupported worksheet content.
                        warnings.simplefilter("error", UserWarning)
                        super().read_worksheets()
                except Exception as exc:
                    if title in self.wb.sheetnames:
                        del self.wb[title]  # discard a partially decoded sheet
                    self.wb.create_sheet(title)  # preserve worksheet index for workbook metadata
                    self.failures[title] = exc if isinstance(exc, Rejection) else Rejection(
                        "processing_failure", "@worksheet", title,
                        f"Worksheet could not be decoded ({type(exc).__name__}).",
                    )
        finally:
            self.parser.sheets = sheets

    def _check_part(self, sheet):
        relation = self.parser.rels[sheet.id]
        if relation.Type != f"{REL_NS}/worksheet":
            raise Rejection("processing_failure", "@worksheet", relation.Type.rsplit("/", 1)[-1],
                            "Only cell-based worksheets can supply tab records.")
        # Inspect source XML before the library can drop an object or extension.
        with self.archive.open(relation.target) as part:
            for _, element in ElementTree.iterparse(part, events=("end",)):
                name = element.tag.rsplit("}", 1)[-1]
                if name in UNSUPPORTED_OBJECTS:
                    raise Rejection("processing_failure", "@worksheet", name,
                                    "Worksheet contains an unsupported object or extension.")
                element.clear()


class _SourceTabs:
    def __init__(self, book, failures):
        self._book = book
        self._failures = failures

    @property
    def sheetnames(self):
        return self._book.sheetnames

    def __getitem__(self, tab):
        if tab in self._failures:
            raise self._failures[tab]
        return self._book[tab]

    def close(self):
        self._book.close()


def read_source(path: Path):
    data = path.read_bytes()
    digest = sha256(data).hexdigest()
    try:
        reader = _TabReader(BytesIO(data), data_only=False, keep_links=False)
        try:
            reader.read()
        finally:
            reader.archive.close()
    except Exception as exc:
        # openpyxl's reader can raise several XML, ZIP and type errors on malformed files.
        return digest, None, Rejection(
            "processing_failure", "@workbook", path.name,
            f"Workbook could not be decoded ({type(exc).__name__}).",
        )
    return digest, _SourceTabs(reader.wb, reader.failures), None
