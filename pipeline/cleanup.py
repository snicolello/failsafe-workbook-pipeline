"""Read one immutable input snapshot. Source coordinates always refer to those bytes."""

from hashlib import sha256
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from .model import Rejection


def read_source(path: Path):
    data = path.read_bytes()
    digest = sha256(data).hexdigest()
    try:
        book = load_workbook(BytesIO(data), data_only=False, keep_links=False)
    except Exception as exc:
        # openpyxl's reader can raise several XML, ZIP and type errors on malformed files.
        return digest, None, Rejection(
            "processing_failure", "@workbook", path.name,
            f"Workbook could not be decoded ({type(exc).__name__}).",
        )
    return digest, book, None
