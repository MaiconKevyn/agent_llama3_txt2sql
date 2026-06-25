## Why

The agent fails queries such as "me mostre a evolucao de mortes por cancer nos ultimos 3 anos" because the planner greedily treats the temporal phrase as part of the clinical concept, producing a diagnosis lookup for "cancer nos ultimos 3 anos". This blocks SQL validation and repair even after the repaired SQL correctly narrows the concept to cancer.

## What Changes

- Separate clinical concept spans from temporal, aggregation, metric, and answer-shape modifiers before building semantic filters.
- Represent "ultimos 3 anos" as an available-data temporal window and keep "cancer" as the clinical concept to resolve.
- Ensure death metrics consistently require and validate `MORTE = true` in generated SQL and repaired SQL.
- Ensure recent-year windows are applied to SQL generation using dataset coverage, so this query targets the latest three available years: 2021, 2022, and 2023.
- Make semantic validation compare resolved clinical concepts and normalized filter intent instead of requiring the original over-greedy literal phrase.
- Add regression coverage for cancer, respiratory, accented/unaccented variants, relative time windows, death metrics, and repair flows.
- Preserve model generalization by using structured span normalization and reusable filter semantics instead of hardcoded full-query phrases.

## Capabilities

### New Capabilities

- `clinical-temporal-filter-separation`: Split clinical concepts from temporal and metric modifiers, then enforce the resulting normalized contract across planning, SQL generation, validation, and repair.

### Modified Capabilities

- None.

## Impact

- Affected planning code: `src/semantic/planner.py`, `src/semantic/plan_reconciler.py`, and clinical concept extraction paths.
- Affected concept resolution code: `src/semantic/concept_resolver.py` and related diagnosis filter builders.
- Affected SQL generation and repair code: deterministic analytic macros, death metric filters, recent-year filters, and repair validation.
- Affected validation code: `src/semantic/validators.py`, especially diagnosis lookup and required-filter checks.
- Affected tests: semantic planner, concept resolver, SQL validation, SQL repair, and CLI/API regression coverage for temporal clinical death-trend queries.
