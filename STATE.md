# Project state

| | |
| --- | --- |
| Project | Failsafe Workbook Pipeline (FWP) |
| Purpose | Verified public repository baseline |
| Status | Local ingest and quarantine milestone |
| As of | November 10, 2026 |
| Authority | Project owner and the [core-field agreement](contracts/core-fields.md) |
| Sources | [Profiles](profiles/), [fixtures](fixtures/) and [tests](tests/) |
| Objective | Keep each healthy tab current while retaining traceable rows for a failed tab |
| Next action | Verify the split-record repair against [issue #1](https://github.com/snicolello/failsafe-workbook-pipeline/issues/1) |
| Read when | Resuming implementation or checking the scope of a public claim |

Eight baseline workbooks yield 288 accepted records across 16 tabs. The second delivery introduces a renamed header and an ungoverned stage. Both affected tabs retain their last accepted data. A proposed two-row parsing capability is tracked separately. The local database is DuckDB.
