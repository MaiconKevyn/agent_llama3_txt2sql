## Context

The current chart planner and semantic planner infer temporal output only from explicit trigger phrases such as "por ano", "serie temporal", or a year range like "2021 a 2023". A chart request that lists years as "2021, 2022 e 2023" is treated as a scalar cohort filter, producing a KPI chart plan and a semantic answer shape that rejects `GROUP BY ano`.

## Goals / Non-Goals

**Goals:**

- Infer `ano` as an output dimension for chart requests that compare multiple explicit years.
- Keep the year list as a filter so only requested years are returned.
- Keep scalar totals unchanged when the user asks for one aggregate across multiple years.
- Make chart plan and semantic plan agree on required columns and answer grain.

**Non-Goals:**

- Do not redesign all temporal understanding.
- Do not change frontend chart rendering contracts.
- Do not alter database schemas or CID mappings.

## Decisions

- Add a reusable "explicit year list" detector shared by chart and semantic planning. This avoids duplicating regex drift while keeping deterministic detection narrow and testable.
- Treat explicit chart requests with at least two listed years as temporal comparisons unless the user explicitly asks for one total. This preserves normal scalar questions while improving chart behavior.
- Represent the result as `x_dimension=ano`, expected shape `time_metric`, required columns `ano` and metric. This aligns with the existing chart renderer and SQL validation model.
- Preserve filters as `ano IN (...)` rather than converting to a broad `BETWEEN`, because the user may list non-contiguous years.

## Risks / Trade-offs

- Over-inference for "total across 2021, 2022 and 2023" chart requests -> mitigate by detecting scalar-total phrasing and keeping KPI behavior.
- Regex-based year extraction can still miss unusual phrasing -> mitigate with regression tests and isolated helper functions.
- Semantic and chart planners can diverge -> mitigate by adding cross-check tests for the same input across both planners.

## Migration Plan

- Add helper tests first for explicit year list detection.
- Update chart planner and semantic planner to consume the helper.
- Add CLI/API regression for the respiratory deaths chart query.
- No data migration or API migration is required.
