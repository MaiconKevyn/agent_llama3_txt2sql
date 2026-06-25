## Why

The semantic planner currently anchors too strongly on heuristic output, so the LLM cannot correct under-detected answer shapes such as scalar versus time series. This creates false validation failures when the user intent is clear but the keyword heuristic missed it.

## What Changes

- Allow reconciled LLM plans to upgrade answer shape when the heuristic is weak or lacks supporting dimensions.
- Preserve deterministic guardrails for unsafe downgrades, unknown dimensions, and schema-invalid fields.
- Record why a planner field was accepted or rejected so debug output explains the decision.
- Add regression coverage for cases where the LLM identifies a valid shape that the heuristic missed.

## Capabilities

### New Capabilities

- `semantic-plan-reconciliation`: Merge heuristic and LLM semantic plans with confidence-aware acceptance rather than treating the heuristic as an absolute authority.

### Modified Capabilities

- None.

## Impact

- Affected planner code: `src/semantic/plan_reconciler.py`, `src/agent/semantic_planner.py`.
- Affected metadata/debug output: `response_metadata.semantic_planner`.
- Affected tests: reconciliation unit tests and end-to-end query planning tests.
