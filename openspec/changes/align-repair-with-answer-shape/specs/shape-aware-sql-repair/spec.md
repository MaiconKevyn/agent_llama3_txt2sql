## ADDED Requirements

### Requirement: Preserve answer shape during repair
The system SHALL only accept a repaired SQL query when it preserves the semantic answer shape required by the user request.

#### Scenario: Time-series repair
- **WHEN** the original request requires annual grouped output
- **THEN** an accepted repair SHALL still output one row per required year or group

### Requirement: Preserve chart required columns during repair
The system SHALL reject repaired SQL that does not output all columns required by the chart plan.

#### Scenario: Chart columns missing after repair
- **WHEN** the chart plan requires `ano` and `total_mortes`
- **THEN** a repair that outputs only diagnostic lookup columns SHALL be rejected before retry

### Requirement: Restrict diagnostic lookup repair
The system SHALL use diagnosis lookup repair only when the requested answer shape is lookup-compatible or the user explicitly asks to inspect matching diagnoses.

#### Scenario: Chart request with diagnosis filter
- **WHEN** a chart request fails diagnosis description validation
- **THEN** diagnosis lookup repair SHALL NOT replace the chart SQL unless it can preserve the chart contract

### Requirement: Report unrecoverable repair mismatch
The system SHALL return a clear error when no repair candidate satisfies both semantic and chart contracts.

#### Scenario: No valid repair candidate
- **WHEN** all repair candidates fail contract validation
- **THEN** the final response SHALL explain that SQL repair could not preserve the requested answer shape
