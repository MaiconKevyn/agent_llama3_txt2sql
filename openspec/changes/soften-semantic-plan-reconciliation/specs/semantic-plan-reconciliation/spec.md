## ADDED Requirements

### Requirement: Upgrade weak scalar plans when candidate shape is supported
The system SHALL allow a candidate semantic plan to upgrade a weak scalar heuristic plan to a grouped or time-series answer shape when the candidate dimensions are valid and supported by the user query or chart contract.

#### Scenario: LLM detects time series missed by heuristic
- **WHEN** the heuristic plan is scalar because no dimension was detected
- **THEN** a candidate `time_series` plan with an allowed `ano` dimension SHALL be accepted if the query or chart contract supports annual output

### Requirement: Preserve explicit scalar intent
The system SHALL reject candidate grouped output when the user explicitly asks for one aggregate total.

#### Scenario: Explicit scalar total
- **WHEN** the user asks for one total across multiple years
- **THEN** candidate grouped dimensions SHALL NOT override the scalar heuristic answer shape

### Requirement: Explain reconciliation decisions
The system SHALL record accepted and rejected semantic planner fields with reasons in response metadata.

#### Scenario: Shape upgrade accepted
- **WHEN** candidate row grain is accepted over a weak heuristic shape
- **THEN** debug metadata SHALL include the accepted field and the reason for acceptance
