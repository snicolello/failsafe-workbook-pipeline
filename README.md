# Failsafe Workbook Pipeline

Sedgewater Outfitters collects work-in-progress reports from eight fictional brands. Their Excel layouts range from flat tables to stacked regions and milestone columns. A shared parser resolves the five agreed fields and records where every value came from. DuckDB publishes each worksheet only after all of its rows pass.

Run one source from the repository root with Python 3.11+ and uv.

```sh
uv run --locked python -m pipeline ingest fixtures/run1/flintwake.xlsx profiles/flintwake.yaml
uv run --locked python -m pipeline ingest fixtures/run2/flintwake.xlsx profiles/flintwake.yaml
```

Open `build/status.html`. The Ridge tab serves its 18 earlier rows after its date header changes. Basin serves the newly submitted date in the same workbook. Click either tab to inspect the accepted workbook SHA and source cells.

Run `uv run --locked python -m pytest` to verify the pipeline. The [core-field agreement](contracts/core-fields.md) defines what passes. [Issue #1](https://github.com/snicolello/failsafe-workbook-pipeline/issues/1) records the next repair.
