"""Rebuild the checked-in synthetic sources. Run python -m fixtures.generate --help."""

import argparse
from datetime import date
from pathlib import Path

from .layouts import banner_tab, baseline_books, offset_sections, stacked_tab, two_tabs
from .source import flat_book, save_book


def changed_flat(*, recurring=False):
    book = flat_book()
    book["Ridge"]["D1"] = "Due on"
    book["Ridge"]["D2"] = date(2027, 5, 10)
    book["Basin"]["D2"] = date(2027, 4, 12)
    if recurring:
        book["Basin"]["D1"] = "Due on"
        book["Basin"]["D2"] = date(2027, 6, 14)
    return book


def changed_banner(*, corrected=False):
    book = two_tabs("MT", ("Shells", "Packs"), banner_tab)
    book["Shells"]["D4"] = "Fit" if corrected else "Awaiting field call"
    book["Packs"]["E4"] = date(2027, 4, 19)
    return book


def split_record():
    book = two_tabs("CR", ("East", "West"), stacked_tab)
    sheet = book["East"]
    # The final item has an identifier-only anchor followed by the event data.
    for col in range(2, 6):
        sheet.cell(21, col).value = sheet.cell(20, col).value
        sheet.cell(20, col).value = None
    sheet["D21"] = date(2027, 5, 17)
    book["West"]["D2"] = date(2027, 5, 24)
    return book


def generate(destination):
    for brand, book in baseline_books():
        save_book(book, destination / "run1" / f"{brand}.xlsx")
    revisions = [
        ("run2/flintwake.xlsx", changed_flat()),
        ("run2/moraine-thread.xlsx", changed_banner()),
        ("run3/copper-rill.xlsx", split_record()),
        ("run3/moraine-thread.xlsx", changed_banner(corrected=True)),
        ("run4/flintwake.xlsx", changed_flat(recurring=True)),
        ("run4/gale-stitch.xlsx", two_tabs("GS", ("Summit", "Valley"), offset_sections)),
    ]
    for filename, book in revisions:
        save_book(book, destination / filename)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="Rebuild the fictional scenario workbooks.")
    cli.add_argument("--output", type=Path, default=Path(__file__).parent,
                     help="Destination for run1 through run4 (default: fixtures/)")
    generate(cli.parse_args().output)
