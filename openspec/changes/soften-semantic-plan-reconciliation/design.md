## Context

The semantic plan reconciler currently treats the heuristic plan as the safety anchor. When the heuristic returns `single_scalar`, candidate LLM dimensions and row grain are rejected even if the candidate correctly identifies a time series or grouped answer. This is safe but too rigid for underspecified natural language.

## Goals / Non-Goals

**Goals:**

- Allow the LLM candidate to upgrade weak heuristic answer shapes when the candidate is schema-valid and supported by query evidence.
- Preserve deterministic rejection for unsafe, unknown, or schema-invalid dimensions.
- Emit clear metadata explaining accepted and rejected fields.
- Keep validation strict after reconciliation.

**Non-Goals:**

- Do not let the LLM bypass SQL safety validation.
- Do not accept arbitrary new dimensions outside the semantic catalog.
- Do not remove the heuristic planner.

## Decisions

- Classify heuristic plans as strong or weak. A `single_scalar` plan is weak when it was chosen only because no dimension was detected, not because scalar phrasing was explicit.
- Accept candidate row-grain upgrades from weak scalar to `time_series` or `one_row_per_group` when candidate required dimensions are allowed and supported by filters, chart plan, or query terms.
- Keep the heuristic as authoritative for explicit scalar questions, top-N scope, rate denominator constraints, and clinical safety constraints.
- Extend reconciliation metadata with an acceptance reason so debug output can explain why the candidate shape was used.

## Risks / Trade-offs

- Accepting LLM shape upgrades can introduce over-grouping -> mitigate with strict allowed dimension checks and semantic validation.
- More nuanced reconciliation can be harder to debug -> mitigate with explicit metadata for field acceptance/rejection.
- Existing tests may assume heuristic priority -> update tests to distinguish strong and weak heuristic cases.

## Migration Plan

- Add focused unit tests for weak and strong heuristic cases.
- Implement shape-upgrade rules in the reconciler.
- Update debug metadata assertions.
- Run planner and CLI regression tests before enabling by default.
