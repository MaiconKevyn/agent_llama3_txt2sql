## ADDED Requirements

### Requirement: Infer annual chart shape from explicit year lists
The system SHALL infer an annual chart result shape when an explicit visualization request includes two or more explicit years and does not ask for a single aggregate total.

#### Scenario: Chart request lists years
- **WHEN** the user asks for a graph of a metric in "2021, 2022 e 2023"
- **THEN** the chart plan SHALL require `ano` and the metric column as output columns

#### Scenario: Non-contiguous year list
- **WHEN** the user asks for a chart for "2019, 2021 e 2023"
- **THEN** the SQL contract SHALL preserve those years as an `IN` filter rather than broadening to a continuous range

### Requirement: Preserve scalar totals when requested
The system SHALL keep a single-metric answer shape when the user explicitly asks for one total across multiple years.

#### Scenario: Single total across listed years
- **WHEN** the user asks for "o total de mortes somando 2021, 2022 e 2023"
- **THEN** the semantic answer shape SHALL remain scalar and SHALL NOT require `ano` in the output

### Requirement: Align chart and semantic temporal contracts
The system SHALL keep chart plan required columns and semantic answer shape consistent for explicit-year chart requests.

#### Scenario: Annual chart contract
- **WHEN** the chart plan requires `ano` and `total_mortes`
- **THEN** the semantic plan SHALL allow grouping by `ano`
