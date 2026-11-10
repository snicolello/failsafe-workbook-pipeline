"""Render the accepted report and its source evidence as one offline HTML file."""

import json
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from tempfile import NamedTemporaryFile


FIELDS = (
    ("item_ref", "Item reference"),
    ("season", "Season"),
    ("stage", "Stage"),
    ("target_date", "Target date"),
    ("owner", "Owner"),
)
STATUSES = {
    "quarantined": ("Quarantined", 0),
    "fallback": ("Last accepted", 1),
    "current": ("Current", 2),
}
CATEGORIES = {
    "processing_failure": "Workbook processing failure",
    "structural_drift": "Structural drift",
    "ambiguous_columns": "Unmapped or ambiguous columns",
    "identity_ambiguity": "Record identity ambiguity",
    "unrecognized_value": "Unrecognized event or status",
}

CSS = """
:root{color-scheme:light;--ink:#182c26;--muted:#4d5c55;--line:#ccd4cb;--paper:#f5f5ee;--white:#fffefa}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 Barlow,"Segoe UI",Arial,sans-serif}
main,.mast-inner{max-width:1180px;margin:auto;padding-inline:clamp(16px,4vw,58px)}
.mast{background:var(--ink);color:white;border-bottom:4px solid #d4e67c}
.mast-inner{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding-block:12px;font-size:.86rem}
.mast strong{font-weight:700;letter-spacing:.05em}.mast span{color:#e0e8dc}
main{padding-bottom:48px}
h1,h2,h3,p,dl,dd{margin:0}
h1{font:normal clamp(2.1rem,5vw,3.7rem)/1.08 "DM Serif Text",Georgia,serif;letter-spacing:-.035em}
h2{font-size:1.24rem;line-height:1.3}h3{font-size:1rem}
.intro{padding:32px 0 22px}.intro p{color:var(--muted);margin-top:9px}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;border:1px solid var(--line);background:var(--line)}
.metrics div{padding:15px clamp(10px,2vw,23px);background:var(--white);display:flex;flex-direction:column-reverse}
.metrics div:first-child{background:#e6edd5}.metrics dt{font-size:.82rem;font-weight:600;color:var(--muted)}
.metrics dd{line-height:1.1;font-weight:600;font-size:2.15rem;font-variant-numeric:tabular-nums}
.section-head{margin:28px 0 12px}.section-head p,.sub{font-size:.87rem;color:var(--muted)}
.tabs{border-top:2px solid var(--ink)}
details{background:var(--white);border:1px solid var(--line);border-top:0}
summary{cursor:pointer;padding:12px 15px;display:grid;align-items:center;grid-template-columns:20px minmax(0,1.7fr) minmax(8.4em,.8fr) minmax(0,1.8fr) 5em;gap:10px;list-style:none}
summary::-webkit-details-marker{display:none}
summary:hover{background:#f0f3e9}summary:focus-visible,.scroll:focus-visible{outline:3px solid #28669a;outline-offset:-3px}
.arrow{width:8px;height:8px;border-right:2px solid var(--muted);border-bottom:2px solid var(--muted);transform:rotate(-45deg);margin-left:2px}
details[open] .arrow{transform:rotate(45deg)}summary .sub{display:block}.count{text-align:right;font-size:.85rem;white-space:nowrap}
.badge{display:inline-block;width:max-content;border-radius:3px;padding:2px 9px;font-size:.79rem;font-weight:700}
.current{background:#e2f1e3;color:#1f5836}.fallback{background:#ffedc6;color:#68470b}.quarantined{background:#f6dcd9;color:#812921}
.body{padding:16px;background:#fafbf5;border-top:1px solid var(--line)}
.evidence{border-left:4px solid #a16d26;background:#fff6de;padding:12px 14px;margin-bottom:14px}
.evidence p,.sources p{overflow-wrap:anywhere}.evidence p+p,.sources p+p{margin-top:4px}
pre{margin:6px 0 0;white-space:pre-wrap;overflow-wrap:anywhere}
code,pre,.cell{font:.84rem/1.45 "IBM Plex Mono",Consolas,monospace}
.sources{margin-bottom:12px;font-size:.84rem;color:var(--muted)}
.scroll{overflow-x:auto}.scroll table{width:100%;border-collapse:collapse;font-size:.88rem}
th,td{text-align:left;vertical-align:top;padding:7px 10px;border-bottom:1px solid var(--line)}
th{font-size:.8rem;background:#eaf0e1}tbody tr:nth-child(even){background:var(--white)}
.cell{display:block;color:#526258;font-size:.77rem}.empty{padding:18px;background:var(--white)}
@media(max-width:760px){.metrics{grid-template-columns:1fr 1fr}summary{grid-template-columns:12px minmax(0,1fr) auto;gap:5px 9px}
summary .context{grid-column:2}.count{grid-column:3}.mast-inner{flex-wrap:wrap;gap:2px 12px}}
@media(max-width:400px){.mast span{display:none}summary{padding:10px 8px}.body{padding:8px}}
"""


def _text(value):
    return escape(str(value), quote=True)


def _metric(label, value):
    return f"<div><dt>{label}</dt><dd>{value}</dd></div>"


def _evidence(status):
    if status["status"] == "current":
        return ""
    cell = status.get("cell")
    evidence = ""
    if cell:
        value = json.dumps(status.get("value"), ensure_ascii=False, default=str)
        evidence = f'<p>Source <code>{_text(cell)}</code> · <code>{_text(value)}</code></p>'
    review = status.get("finding")
    if isinstance(review, dict) and "reviewer" in review:
        reviewer = "Local rule review" if review["reviewer"] == "deterministic" else f'Reviewed by {_text(review["reviewer"])}'
        comparison = _text(review.get("sha_comparison", "unknown"))
        evidence += f'<p>{reviewer} · Workbook SHA comparison ({comparison})</p>'
        note = review.get("commentary") or review.get("review_status")
        if note:
            evidence += f"<p>{_text(note)}</p>"
    elif review:
        finding = json.dumps(review, ensure_ascii=False, indent=2) if isinstance(review, dict) else review
        evidence += f"<p><strong>Review finding</strong></p><pre>{_text(finding)}</pre>"
    return (
        '<section class="evidence"><h3>Rejected input</h3>'
        f'<p>{_text(status["message"])}</p>{evidence}</section>'
    )


def _accepted_rows(records, label):
    if not records:
        return "<p>No accepted records for this tab.</p>"
    headers = "".join(f'<th scope="col">{name}</th>' for _, name in FIELDS)
    rows = []
    for record in records:
        cells = []
        for key, _ in FIELDS:
            value = _text(record[key])
            source = _text(record["lineage"][key])
            cells.append(f'<td>{value}<span class="cell">{source}</span></td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        f'<div class="scroll" role="region" aria-label="Accepted records for {label}" tabindex="0">'
        f'<table><caption>Accepted values and their source locations</caption>'
        f'<thead><tr>{headers}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )


def _panel(status, records):
    state = status["status"]
    badge, _ = STATUSES[state]
    brand = _text(status["brand"].replace("-", " ").title())
    tab = _text(status["tab"])
    category = CATEGORIES.get(status.get("category"), status.get("category"))
    if state == "current":
        context = "Accepted this input"
    elif state == "fallback":
        context = f'{_text(category)}<span class="sub">Serving data accepted {_text(status["accepted_at"])}</span>'
    else:
        context = f'{_text(category)}<span class="sub">Awaiting first acceptance</span>'
    sources = (
        f'<p>Input observed {_text(status["observed_at"])} · SHA-256 '
        f'<code>{_text(status["sha"])}</code></p>'
    )
    if state == "fallback":
        sources += (
            f'<p>Accepted source {_text(status["accepted_at"])} · SHA-256 '
            f'<code>{_text(status["accepted_sha"])}</code></p>'
        )
    row_count = len(records)
    noun = "row" if row_count == 1 else "rows"
    return (
        '<details><summary><span class="arrow" aria-hidden="true"></span>'
        f'<span><strong>{tab}</strong><span class="sub">{brand}</span></span>'
        f'<span class="badge {state}">{badge}</span><span class="context sub">{context}</span>'
        f'<span class="count">{row_count} {noun}</span></summary><div class="body">'
        f'{_evidence(status)}<div class="sources">{sources}</div>'
        f'{_accepted_rows(records, brand + " / " + tab)}</div></details>'
    )


def render_board(statuses, records, destination, *, title="Workbook status board", as_of=None):
    """Write a portable report from a single store snapshot and return its path."""
    by_tab = defaultdict(list)
    for record in records:
        by_tab[(record["brand"], record["tab"])].append(record)
    ordered = sorted(statuses, key=lambda s: (STATUSES[s["status"]][1], s["brand"], s["tab"]))
    if by_tab.keys() - {(s["brand"], s["tab"]) for s in ordered}:
        raise ValueError("A report row has no corresponding tab decision")
    for status in ordered:
        rows = by_tab[(status["brand"], status["tab"])]
        if len(rows) != status["row_count"] or any(row["sha"] != status["accepted_sha"] for row in rows):
            raise ValueError("Report rows and accepted tab decisions describe different snapshots")
    counts = Counter(s["status"] for s in ordered)
    metrics = "".join((
        _metric("Accepted records", sum(len(rows) for rows in by_tab.values())),
        _metric("Current tabs", counts["current"]),
        _metric("Tabs serving last accepted", counts["fallback"]),
        _metric("Tabs without accepted data", counts["quarantined"]),
    ))
    panels = "".join(_panel(s, by_tab[(s["brand"], s["tab"])]) for s in ordered)
    if not panels:
        panels = '<p class="empty">No workbooks have been processed.</p>'
    timestamp = f" · {_text(as_of)}" if as_of else ""
    brand_count = len({s["brand"] for s in ordered})
    brands = "brand" if brand_count == 1 else "brands"
    tabs = "tab" if len(ordered) == 1 else "tabs"
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_text(title)} | Sedgewater Outfitters</title><style>{CSS}</style></head>
<body><header class="mast"><div class="mast-inner"><strong>Sedgewater Outfitters</strong>
<span>Synthetic portfolio demo</span></div></header><main>
<header class="intro"><h1>{_text(title)}</h1><p>Work in progress across {brand_count} {brands} and {len(ordered)} workbook {tabs}{timestamp}</p></header>
<dl class="metrics">{metrics}</dl>
<section aria-labelledby="tabs"><div class="section-head"><h2 id="tabs">Workbook tabs</h2>
<p>Open a tab to trace each value to its source. Tabs with rejected inputs appear first.</p></div>
<div class="tabs">{panels}</div></section></main></body></html>
"""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Readers opening the board during refresh see one complete snapshot.
    draft = NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
    temporary = Path(draft.name)
    try:
        with draft:
            draft.write(html)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path
