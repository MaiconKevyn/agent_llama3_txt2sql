## ADDED Requirements

### Requirement: Clinical spans exclude temporal modifiers
The system SHALL normalize diagnosis and death-cause clinical spans before creating semantic filters, removing temporal, metric, aggregation, and answer-shape modifiers while preserving the clinical concept text.

#### Scenario: Relative years are not captured as disease text
- **WHEN** the user asks "me mostre a evolucao de mortes por cancer nos ultimos 3 anos"
- **THEN** the semantic plan contains a clinical diagnosis filter for `cancer` and does not contain a diagnosis description value equal to `cancer nos ultimos 3 anos`

#### Scenario: Explicit years are not captured as disease text
- **WHEN** the user asks "me mostre um grafico mostrando o numero total de mortes por causas respiratorias em 2021, 2022 e 2023"
- **THEN** the semantic plan separates the respiratory clinical concept from the explicit year filter

#### Scenario: Unknown concepts still use clean fallback lookup
- **WHEN** the user asks for a death trend for an unknown disease phrase with a relative time window
- **THEN** the semantic plan uses a diagnosis description fallback containing only the disease phrase and a separate temporal filter

### Requirement: Relative recent-year filters use available data coverage
The system SHALL interpret relative year windows such as "ultimos 3 anos" using the latest year available in `internacoes.DT_INTER`, not the wall-clock current date.

#### Scenario: Latest three available years
- **WHEN** the data profile reports `internacoes.DT_INTER` coverage ending in 2023 and the user asks for the last 3 years
- **THEN** the semantic contract and generated SQL restrict the annual series to 2021, 2022, and 2023

#### Scenario: SQL does not use wall-clock date
- **WHEN** generated SQL handles a relative recent-year request
- **THEN** the SQL does not use `CURRENT_DATE`, `NOW()`, or the local machine date as the anchor

### Requirement: Death-cause trends require death filters
The system SHALL apply `MORTE = true` for death-count and death-cause trend queries when counting deaths associated with a diagnosis through `DIAG_PRINC`.

#### Scenario: Initial deterministic SQL includes death predicate
- **WHEN** the user asks "me mostre a evolucao de mortes por cancer nos ultimos 3 anos"
- **THEN** the generated SQL filters the counted case rows with `i."MORTE" = true`

#### Scenario: Validation rejects missing death predicate
- **WHEN** SQL for a death-count plan joins `internacoes` to diagnosis data but omits the death predicate
- **THEN** semantic validation fails with a required death-filter error

### Requirement: Validation follows normalized clinical intent
The system SHALL validate diagnosis filters against normalized clinical terms or resolved clinical concept filters rather than against over-greedy raw query captures.

#### Scenario: Repaired SQL with normalized cancer term passes diagnosis validation
- **WHEN** the plan normalized the clinical term to `cancer` and repaired SQL uses `c."DESCRICAO" ILIKE '%cancer%'`
- **THEN** semantic validation does not require the phrase `cancer nos ultimos 3 anos`

#### Scenario: Resolved concepts validate by code or prefix
- **WHEN** a clinical concept resolves to CID codes or prefixes
- **THEN** semantic validation accepts SQL that applies those resolved targets through `DIAG_PRINC` without requiring the original user phrase in the SQL text

### Requirement: Repair preserves temporal answer shape and normalized filters
The system SHALL repair failed SQL using the normalized semantic plan while preserving required answer shape, dimensions, temporal filters, and death filters.

#### Scenario: Repair does not reintroduce raw temporal disease phrase
- **WHEN** SQL repair runs for a failed temporal death-cause query
- **THEN** repaired SQL does not use `ILIKE '%cancer nos ultimos 3 anos%'`

#### Scenario: Repair keeps annual time-series contract
- **WHEN** repair succeeds for a relative recent-year death trend
- **THEN** the repaired SQL still returns one row per year or the deterministic analytic time-series package required by the semantic answer shape

### Requirement: Original cancer death trend query succeeds end to end
The system SHALL answer the original cancer death trend query without semantic plan failure and with a valid annual trend over the latest three available years.

#### Scenario: CLI query produces a successful response
- **WHEN** the CLI runs `me mostre a evolucao de mortes por cancer nos ultimos 3 anos` with debug steps enabled
- **THEN** the workflow completes successfully and does not return `SEMANTIC PLAN ERROR`

#### Scenario: Response reflects requested scope
- **WHEN** the original query succeeds
- **THEN** the response scope indicates deaths associated with cancer diagnoses and the time series covers 2021, 2022, and 2023
