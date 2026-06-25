## Context

Repair currently selects deterministic macros based mostly on error message matching. A diagnosis description error can trigger a lookup query that returns diagnostic metadata instead of the requested chart or grouped answer. Subsequent validation then fails because output columns and grouping no longer satisfy the original contract.

## Goals / Non-Goals

**Goals:**

- Select repairs that preserve semantic answer shape and chart plan.
- Validate candidate repair SQL against required output columns before retrying.
- Avoid replacing chart/time-series queries with diagnostic lookup queries unless lookup output is requested.
- Improve final error messages when no repair fits the contract.

**Non-Goals:**

- Do not remove deterministic repair macros.
- Do not redesign all SQL generation.
- Do not bypass semantic or chart validation.

## Decisions

- Add a repair candidate evaluation step that checks semantic shape, chart required columns, and query category before accepting a deterministic repair.
- Rank repairs by contract fit instead of first non-null SQL. Shape-preserving macros should win over lookup macros for chart and grouped requests.
- Restrict diagnosis lookup repair to lookup-shaped outputs or explicit diagnostic exploration requests.
- Store rejected repair candidates in metadata for debug visibility.

## Risks / Trade-offs

- More repair checks add complexity -> mitigate by centralizing candidate evaluation.
- Some previously repaired queries may now fail with a clearer error -> acceptable when the old repair returned the wrong shape.
- Candidate validation may duplicate existing validation logic -> reuse chart and semantic validators where possible.

## Migration Plan

- Add tests for repair candidate ranking.
- Implement candidate evaluation around deterministic repair builders.
- Add debug metadata for accepted and rejected candidates.
- Run existing semantic repair and chart regression tests.
