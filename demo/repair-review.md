# Two profile changes, one owner decision

On November 10, 2026, Codex presented the Flintwake repair and Gale Stitch onboarding for review. The project owner replied **“Approve both profiles”**. The commands below reproduce those scopes with the checked-in synthetic workbooks. Counts measure what the current files can pass in a fresh run. The four-run board also shows the rows served from prior accepted data.

## Restore Flintwake's renamed date column

Run 2 changed `Ridge!D1` from `Target date` to `Due on`. The candidate adds one brand-level alias for `target_date`. It restores 18 Ridge items, taking the full comparison set from 270 to 288 accepted rows. For example, `FW-001` at `Ridge!A2` now carries the date `2027-05-10` from `Ridge!D2`. The Basin rows and all seven other brands' outputs match across the two runs. [Original profile](../profiles/flintwake.yaml) · [Approved candidate](../fixtures/repairs/flintwake.yaml)

```sh
uv run --locked python -m pipeline.preview fixtures/run2/flintwake.xlsx fixtures/repairs/flintwake.yaml
```

The same approved alias handles the later `Basin!D1` spelling. Item `FW-019` then carries `2027-06-14` from `Basin!D2`. Reproduce recurrence by substituting `fixtures/run4/flintwake.xlsx` in the command above.

## Add Gale Stitch through its profile

The new profile reads headers on row 4 and takes stage from vertical section labels. It adds 18 Summit and 18 Valley items, moving the comparison set from 288 to 324 accepted rows. On Summit, `GS-001` at `A6` takes its stage `Sample` from `A5` and its date `2027-01-09` from `C6`. Every pre-existing brand produced identical values, source locations and tab decisions. [Approved profile](../fixtures/onboarding/gale-stitch.yaml)

```sh
uv run --locked python -m pipeline.preview fixtures/run4/gale-stitch.xlsx fixtures/onboarding/gale-stitch.yaml
```

| Reviewed source | Workbook SHA-256 | Candidate YAML SHA-256 |
| --- | --- | --- |
| Flintwake, run 2 | `d57e5ae23277ee5ffcc37500c987d6f6162e8546381f6785d50f36c8416770b8` | `126db16101770db4df3878dc6a1d3d24143577a3b866a4714e2ba1ad59d18675` |
| Gale Stitch, run 4 | `868a1de1fba26ac275c21ff4109d635af9f55fc0e89fbfaf9ea6b67330c49489` | `04ad1cc5a3d6e49b66ebd96e4e0b30b9ad325706cd257b1d257732fce0e9d334` |

Add `--json` to inspect the full before-and-after rows, per-field lineage and tab findings. The [review instructions](../skills/wip-structure/SKILL.md) describe how to conduct another session with Claude.

## What Claude proposed independently

Two later tool-free Claude sessions received the public schema, field agreement, review instructions and source excerpts. Flintwake's session also received its original profile. The approved candidates were withheld. Each session record preserves the actual prompt, reply, reported cost and local replay result.

- **Flintwake passed.** Claude proposed a brand-level date alias. On run 2 and again on run 4, its tab decisions, changed rows, field lineage and seven control brands matched the approved profile. [Flintwake proposal and replays](reviews/flintwake-proposal.json)
- **Gale Stitch was refused before ingestion.** An earlier review saw only the first section and incorrectly suggested replacing `section_field: stage`. The independent proposal received every section marker on both tabs. It recognized the vertical sections but also mapped all three stage labels as horizontal milestones. That gave stage and date multiple sources. The preflight rejected the proposal on Summit. The owner-approved profile uses one source per field and adds 36 items. [Initial review](reviews/gale-stitch-profile.json) · [Gale Stitch proposal and refusal](reviews/gale-stitch-proposal.json)
