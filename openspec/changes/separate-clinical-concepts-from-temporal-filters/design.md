## Context

The current semantic flow builds filters directly from broad regex captures and then reconciles them with LLM output. For the failing query "me mostre a evolucao de mortes por cancer nos ultimos 3 anos", `_extract_death_cause_description_term()` captures `cancer nos ultimos 3 anos` as a diagnosis description filter. The later repair step can produce a more reasonable SQL predicate such as `ILIKE '%cancer%'` and `i."MORTE" = true`, but validation still checks against the stale over-greedy phrase and rejects the SQL.

The affected path crosses multiple modules: semantic filter extraction in `src/semantic/planner.py`, concept resolution in `src/semantic/concept_resolver.py`, deterministic temporal SQL in `src/agent/analytic_sql.py`, validation in `src/semantic/validators.py`, and repair selection in `src/agent/execution.py`. The fix needs to be reusable for other clinical concepts and relative temporal phrases, not a special case for cancer.

## Goals / Non-Goals

**Goals:**

- Normalize user query spans into distinct clinical concept, temporal window, metric, and answer-shape semantics before creating filters.
- Keep clinical concept extraction general: `cancer nos ultimos 3 anos` must become clinical term `cancer` plus temporal window `last_n_available=3`.
- Ensure death-count and death-cause trends use `MORTE = true` consistently in generated and repaired SQL.
- Ensure recent-year windows are implemented from the latest year available in `internacoes.DT_INTER`, not from wall-clock time.
- Align validator expectations with normalized filters and resolved clinical concepts so repair is not forced to reproduce bad raw captures.
- Add regression tests that prove the original query returns a valid time-series contract for 2021, 2022, and 2023.

**Non-Goals:**

- Do not add a broad LLM-only clinical entity recognizer in this change.
- Do not redesign the full semantic planner or replace existing OpenSpec changes.
- Do not hardcode the exact failing user prompt or a fixed response payload.
- Do not change frontend behavior except through existing API/CLI response correctness.

## Decisions

1. Add a reusable query-span normalization layer before diagnosis filter creation.

   The planner should strip recognized modifiers from candidate clinical spans using shared helpers for temporal expressions, answer-shape terms, metric words, and stop phrases. This keeps extraction deterministic and auditable while avoiding full-query string patches. Alternatives considered: adding more stop words to the existing regex or special-casing "nos ultimos 3 anos"; both are brittle and would fail for equivalent phrases such as "ultimos tres anos", "anos mais recentes", or other diseases.

2. Preserve the normalized clinical term in the semantic contract.

   Description fallback filters should store only cleaned clinical terms. If a known concept is resolved, the plan should prefer `diagnostico_principal_codigo` or `diagnostico_principal_prefix` plus metadata labels. For unresolved broad terms like "cancer", the fallback can remain a description lookup, but its values must exclude temporal modifiers. The plan may retain raw input as debug metadata if useful, but validation must not require the raw over-greedy phrase.

3. Apply relative recent-year filters in deterministic analytic SQL.

   `_scope_conditions_from_plan()` currently handles explicit `ano` and `ano_intervalo`, but not `recent_years_available`. The temporal trend macro should translate `recent_years_available=3` into a `DT_INTER` year predicate anchored on the data's max available year, producing the latest available 3-year window. With current profile coverage ending on 2023-12-31, that means 2021 through 2023. The implementation should use existing profile metadata or a deterministic subquery against `internacoes` rather than `CURRENT_DATE`.

4. Enforce death metrics through a shared required-filter path.

   When a plan metric has `required_filters=["MORTE = true"]` or the plan has `desfecho = MORTE = true`, deterministic SQL should apply the death predicate to the numerator/cases CTE for count-of-deaths questions. Validation should continue rejecting SQL that omits the death filter, but generation should satisfy the rule before repair is needed.

5. Make validator checks semantic, not raw-capture anchored.

   `validate_sql_against_semantic_plan()` should verify that SQL applies the normalized diagnosis filter through `DIAG_PRINC` and that required terms/codes/prefixes are represented. It should not require temporal words that were stripped from a clinical span. If a repair replaces a raw diagnosis phrase with a normalized equivalent that matches the semantic concept, validation should pass.

6. Keep repair shape-aware and contract-preserving.

   Repair should reuse the normalized semantic plan and must not mutate it back to raw query text. When repair fixes a diagnosis term or adds `MORTE = true`, it must preserve the time-series answer shape, required `ano` dimension, recent-year filter, and concept scope.

## Risks / Trade-offs

- Span normalization may remove meaningful clinical words if temporal or metric stripping is too broad. Mitigation: implement small, named normalizers with unit tests for clinical phrases that contain words like "ano" as part of legitimate text before expanding patterns.
- Broad "cancer" description lookup can match many CID descriptions and may need a curated neoplasm concept later. Mitigation: this change only guarantees correct separation and SQL semantics; a future concept expansion can map cancer to CID C/D neoplasm ranges if clinically approved.
- Using a subquery for latest available year can add repeated expressions to SQL. Mitigation: keep the window calculation in a compact CTE or reusable helper and validate with existing DuckDB execution tests.
- Repair may pass SQL that differs textually from the original description term. Mitigation: validation should compare normalized concept intent and required filters, while debug metadata records any normalization that occurred.

## Migration Plan

1. Add failing unit tests for the original query at planner, SQL generation, validator, and repair levels.
2. Implement query-span normalization helpers and route diagnosis/death-cause extraction through them.
3. Extend deterministic SQL scope generation for `recent_years_available`.
4. Wire required death predicates into temporal condition trend SQL.
5. Adjust validator logic to use normalized diagnosis terms and resolved concept filters.
6. Run the full test suite and directly run the CLI query with `--debug-steps` to verify success.

Rollback is a normal code revert: the change is internal to planning, SQL generation, validation, and tests, with no data migration or external API contract migration.

## Open Questions

- Should generic "cancer" remain a description lookup for this change, or should a separate clinical concept map it to a curated neoplasm CID range?
- Should normalized clinical spans be added to response/debug metadata so users can see how their query was interpreted?
