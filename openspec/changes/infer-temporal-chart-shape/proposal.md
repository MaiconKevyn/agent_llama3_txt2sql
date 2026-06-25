## Why

The agent currently treats explicit year lists in chart requests as scalar filters unless the user says exact trigger phrases such as "por ano" or uses a year range. This makes valid chart questions fail or collapse into KPI-style answers even when the intended shape is a year-by-year series.

## What Changes

- Infer a temporal chart shape when a visualization request includes multiple explicit years.
- Treat listed years such as "2021, 2022 e 2023" as both a filter and an output time dimension when the requested chart needs comparison across those years.
- Keep scalar behavior for non-chart questions where multiple years are only a cohort filter.
- Add regression coverage for chart requests with explicit year lists, ranges, and scalar totals.

## Capabilities

### New Capabilities

- `temporal-chart-shape-inference`: Detect chart-ready temporal result shapes from explicit year lists and equivalent natural-language phrasing.

### Modified Capabilities

- None.

## Impact

- Affected planner code: `src/visualization/chart_plan.py`, `src/semantic/planner.py`.
- Affected validation/rendering behavior: chart plan required columns and semantic answer shape.
- Affected tests: semantic planner, chart plan, and CLI/API regression cases for chart queries.
