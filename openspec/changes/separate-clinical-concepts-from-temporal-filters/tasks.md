## 1. Regression Coverage First

- [x] 1.1 Add planner regression tests proving `"me mostre a evolucao de mortes por cancer nos ultimos 3 anos"` produces a clinical diagnosis term of `cancer`, a `recent_years_available=3` temporal filter, a death filter, and no diagnosis value containing `ultimos 3 anos`.
- [x] 1.2 Add planner tests for equivalent phrasing with explicit years and respiratory concepts to ensure temporal phrases are separated from resolved CID prefix concepts.
- [x] 1.3 Add fallback tests for unknown clinical phrases with relative time windows to ensure only the disease phrase remains in `diagnostico_principal_descricao`.
- [x] 1.4 Add deterministic SQL tests for temporal death-cause trends verifying `i."MORTE" = true`, `DIAG_PRINC` diagnosis scope, and a latest-available-year window covering 2021, 2022, and 2023 when profile coverage ends in 2023.
- [x] 1.5 Add validator tests proving SQL using `ILIKE '%cancer%'` passes when the normalized plan term is `cancer`, and proving SQL missing `MORTE = true` still fails.
- [x] 1.6 Add repair regression tests proving repaired SQL does not reintroduce `ILIKE '%cancer nos ultimos 3 anos%'` and preserves the annual time-series answer shape.

## 2. Clinical Span Normalization

- [x] 2.1 Introduce a small reusable normalizer for candidate clinical spans, with named helpers for temporal modifiers, metric words, aggregation terms, and answer-shape terms.
- [x] 2.2 Route `_extract_death_cause_description_term()` and diagnosis description extraction through the normalizer before expanding terms or creating filters.
- [x] 2.3 Keep normalization generic by matching modifier classes and boundaries instead of full-query phrases or disease-specific prompts.
- [x] 2.4 Preserve enough debug metadata to explain that the raw phrase was normalized, without making validators depend on raw over-greedy text.
- [x] 2.5 Ensure `find_clinical_concepts()` receives useful cleaned text or span candidates so known concepts still resolve to codes/prefixes before description fallback.

## 3. Temporal Window Semantics

- [x] 3.1 Audit existing recent-year extraction in `src/semantic/planner.py` and make sure `ultimos 3 anos` is represented only as `recent_years_available` or equivalent normalized temporal semantics.
- [x] 3.2 Extend deterministic SQL scope generation in `src/agent/analytic_sql.py` to support `recent_years_available` for `DT_INTER`.
- [x] 3.3 Anchor relative windows on the latest available `internacoes.DT_INTER` year from profile metadata or a deterministic data-driven CTE, never `CURRENT_DATE` or `NOW()`.
- [x] 3.4 Apply the same recent-year condition to denominator and case CTEs in temporal trend SQL so the returned series is limited to the requested window.
- [x] 3.5 Keep explicit year lists and year ranges behavior unchanged, including non-contiguous explicit year lists.

## 4. Death Metric Enforcement

- [x] 4.1 Centralize the check that a death-count metric or `desfecho = MORTE = true` filter requires the SQL case/numerator scope to include `i."MORTE" = true`.
- [x] 4.2 Update temporal condition trend SQL so death trend queries count death rows, not all diagnosis-matched admissions.
- [x] 4.3 Ensure mortality-rate queries keep the existing denominator semantics and are not accidentally converted into death-only denominators.
- [x] 4.4 Keep `CID_MORTE` out of analytical death-cause queries unless the user explicitly requests the raw death CID field.

## 5. Semantic Validation Alignment

- [x] 5.1 Update diagnosis description validation to check normalized plan terms, resolved codes, or resolved prefixes rather than stale raw captures.
- [x] 5.2 Ensure validation still requires `DIAG_PRINC` for analytical diagnosis/death-cause filters.
- [x] 5.3 Strengthen `recent_years_available` validation so SQL must apply a bounded year window on `DT_INTER`, not merely mention `DT_INTER` and `YEAR`.
- [x] 5.4 Keep validation failure messages precise enough for repair to choose the correct strategy: missing death filter, missing temporal window, or missing diagnosis scope.

## 6. Repair Flow

- [x] 6.1 Ensure SQL repair receives and reuses the normalized semantic plan rather than raw query fragments.
- [x] 6.2 Update deterministic repair candidates for diagnosis description lookup and death-cause count/trend so they preserve required dimensions, recent-year filters, and `MORTE = true`.
- [x] 6.3 Add a guard preventing repair from accepting a query that fixes diagnosis text while dropping the time-series answer shape or temporal window.
- [x] 6.4 Confirm post-repair validation can pass when the repaired SQL is semantically equivalent to the normalized plan.

## 7. End-to-End Verification

- [x] 7.1 Run focused tests for clinical concept resolution, temporal chart/shape handling, semantic validation, analytic SQL, and shape-aware repair.
- [x] 7.2 Run the full test suite with `uv run pytest -q`.
- [x] 7.3 Run the CLI command `uv run python src/interfaces/cli/agent.py --query "me mostre a evolucao de mortes por cancer nos ultimos 3 anos" --debug-steps`.
- [x] 7.4 Verify the CLI workflow succeeds, does not emit `SEMANTIC PLAN ERROR`, applies `MORTE = true`, and limits the series to 2021, 2022, and 2023.
- [x] 7.5 Inspect debug output to confirm the semantic contract separates clinical concept `cancer` from the recent-year window.

## 8. Code Quality Review

- [x] 8.1 Remove any phrase-specific hardcoding introduced during implementation and replace it with reusable normalization helpers or concept metadata.
- [x] 8.2 Keep helper functions small, named by intent, and covered by unit tests.
- [x] 8.3 Avoid broad refactors outside planning, SQL generation, validation, repair, and their tests.
- [x] 8.4 Update comments only where they explain non-obvious clinical/temporal semantics.
- [x] 8.5 Review failure messages and debug metadata for clarity without leaking implementation noise into final user responses.
