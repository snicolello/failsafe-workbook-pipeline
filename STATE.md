# Project state

| | |
| --- | --- |
| Project | Failsafe Workbook Pipeline (FWP) |
| Purpose | Verified baseline for the public recruiting demonstration |
| Status | Four-run local demonstration and offline SQL comparison verified |
| As of | November 10, 2026 |
| Authority | Project owner, [project boundaries](PROJECT.md) and [field agreement](contracts/core-fields.md) |
| Sources | [Saved reports](demo/snapshots/summary.json), [profile decisions](demo/repair-review.md), [split-row repair](https://github.com/snicolello/failsafe-workbook-pipeline/pull/3) and [SQL comparison](databricks/local-expected.json) |
| Objective | Demonstrate traceable tab-level acceptance and recovery with independently authored synthetic workbooks |
| Next action | Run the prepared SQL and compare all six snapshots when an approved personal Unity Catalog workspace is available |
| Read when | Resuming implementation or checking the scope of a recruiting claim |

## Completed

The local replay serves 288 rows across 16 baseline tabs. Two independent run 2 failures retain dated fallback. An approved alias restores one tab and a later source correction restores the other. Run 3 reproduces the split-record refusal, then recovers the item with distinct source coordinates on both rows. Run 4 serves 324 rows on 18 current tabs through profile-only onboarding and recurrence handling. The default replay uses captured Claude findings and runs without accounts.

The tests cover original workbook SHA and lineage, every failure category, tab isolation, replay, interrupted transactions, restored worksheet names, invalid profiles, semantic profile previews and the recorded board outputs. The prepared SQL's merge and report logic reproduced all six reports locally after two loads.

## Pending and deferred

The owner selected SQL preparation for later verification. A live Databricks run and saved warehouse results remain pending until an approved personal workspace, catalog and SQL warehouse are available. [Workspace procedure](databricks/README.md)

## Blocked

No dependency remains for cloning, running or reviewing the public demonstration.
