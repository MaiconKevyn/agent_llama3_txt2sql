## Why

SQL repair can replace a failed query with a diagnostic lookup query that no longer satisfies the requested answer shape. This causes repair loops where the system fixes one validation error while breaking chart columns or group-by requirements.

## What Changes

- Make deterministic repair selection aware of the semantic answer shape and chart plan.
- Prefer repairs that preserve required output columns, grouping, and chart grain.
- Prevent diagnosis lookup repairs from replacing chart/time-series answers unless the user explicitly asked for a lookup.
- Surface a clear unrecoverable error when no repair can satisfy both semantic and chart contracts.
- Add regression coverage for repair ordering after diagnosis lookup, chart plan, and semantic shape failures.

## Capabilities

### New Capabilities

- `shape-aware-sql-repair`: Select and validate SQL repairs against the requested answer shape and chart contract before retrying.

### Modified Capabilities

- None.

## Impact

- Affected repair code: `src/agent/execution.py`.
- Affected validation code: `src/agent/validation.py`, `src/semantic/validators.py`, `src/visualization/chart_plan.py`.
- Affected debug output: repair attempts and final error messaging.
