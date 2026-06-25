## ADDED Requirements

### Requirement: Resolve known clinical phrases before literal lookup
The system SHALL attempt clinical concept resolution before creating literal diagnosis description filters.

#### Scenario: Respiratory phrase with noisy wording
- **WHEN** the user asks for deaths by "causa respiratorias"
- **THEN** the semantic plan SHALL resolve the phrase to the respiratory disease concept instead of using a literal `ILIKE '%causa respiratorias%'` filter

### Requirement: Prefer CID codes or prefixes for known concepts
The system SHALL express known clinical concepts as resolved CID codes or prefixes when the concept catalog provides them.

#### Scenario: Respiratory disease concept
- **WHEN** the respiratory disease concept is resolved
- **THEN** the semantic filters SHALL include `diagnostico_principal_prefix` with `J%`

### Requirement: Preserve fallback lookup for unknown terms
The system SHALL use diagnosis description lookup when no known concept matches the clinical phrase.

#### Scenario: Unknown disease phrase
- **WHEN** the user provides a disease phrase absent from the concept catalog
- **THEN** the semantic plan SHALL retain a safe diagnosis description lookup filter
