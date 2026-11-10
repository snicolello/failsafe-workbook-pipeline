"""The eight source teams each arrange the same agreed fields differently."""

from .source import STAGES, flat_book, header, new_book, row_values


def two_tabs(prefix, names, write_tab):
    book = new_book()
    for index, name in enumerate(names):
        rows = [row_values(prefix, index, i) for i in range(18)]
        write_tab(book.create_sheet(name), rows)
    return book


def banner_tab(sheet, rows):
    sheet["A1"] = f"Moraine Thread / {sheet.title} planning"
    header(sheet, 3, ("Coordinator", "Season drop", "Style key", "Gate", "Promise"))
    for item, season, stage, due, owner in rows:
        sheet.append((owner, season, item, stage, due))


def grouped_tab(sheet, rows):
    header(sheet, 1, ("Catalogue", None, "Delivery", None, "People"))
    sheet.merge_cells("A1:B1")
    sheet.merge_cells("C1:D1")
    header(sheet, 2, ("Reference", "Season", "Gate", "Date", "Desk"))
    for row in rows:
        sheet.append(row)


def stage_sections(sheet, rows, row=1):
    header(sheet, row, ("Stock mark", "Season", "Target", "Workcell"))
    for section in STAGES:
        sheet.append((section,))
        for item, season, stage, due, owner in rows:
            if stage == section:
                sheet.append((item, season, due, owner))


def milestone_tab(sheet, rows):
    header(sheet, 1, ("Work order", "Season", "Desk", "Sample date", "Fit date", "Release date"))
    for item, season, stage, due, owner in rows:
        dates = [due if milestone == stage else None for milestone in STAGES]
        sheet.append((item, season, owner, *dates))


def stage_tab(sheet, rows):
    header(sheet, 1, ("Article", "Range", "Handler", "Due"))
    for item, season, _, due, owner in rows:
        sheet.append((item, season, owner, due))


def season_tab(sheet, rows):
    header(sheet, 1, ("Ticket", "Review stage", "Needed by", "Custodian"))
    for item, _, stage, due, owner in rows:
        sheet.append((item, stage, due, owner))


def stacked_tab(sheet, rows):
    header(sheet, 1, ("Reference", "Ship season", "Step", "Commit date", "Lead"))
    for row in rows[:9]:
        sheet.append(row)
    header(sheet, 11, ("Ref code", "Desk", "Checkpoint", "Deadline", "Drop"))
    for item, season, stage, due, owner in rows[9:]:
        sheet.append((item, owner, stage, due, season))
    sheet.freeze_panes = "A2"


def offset_sections(sheet, rows):
    sheet["A1"] = f"Gale Stitch / {sheet.title} route"
    stage_sections(sheet, rows, row=4)


def baseline_books():
    yield "flintwake", flat_book()
    yield "moraine-thread", two_tabs("MT", ("Shells", "Packs"), banner_tab)
    yield "alder-reach", two_tabs("AR", ("Lowland", "Upland"), grouped_tab)
    yield "cairn-loom", two_tabs("CL", ("North", "South"), stage_sections)
    yield "bracken-ferry", two_tabs("BF", ("Fabric", "Trim"), milestone_tab)
    yield "slate-finch", two_tabs("SF", ("Sample", "Release"), stage_tab)
    yield "tarn-field", two_tabs("TF", ("Spring", "Fall"), season_tab)
    yield "copper-rill", two_tabs("CR", ("East", "West"), stacked_tab)
