## Why

Clinical concept matching currently falls back to brittle literal description filters for phrasing such as "causa respiratorias". The database uses CID descriptions and abbreviations, so literal string matching can miss known concepts that should resolve to catalog rules like CID chapter `J%`.

## What Changes

- Route clinical disease phrases through concept resolution before building diagnosis description filters.
- Map common variants and imperfect phrases for respiratory disease to the existing respiratory concept.
- Prefer resolved CID codes or prefixes over raw `ILIKE` description filters when a concept is known.
- Keep fallback description lookup for genuinely unknown disease terms.
- Add regression coverage for respiratory, pulmonary, accented, unaccented, singular, plural, and malformed user phrasing.

## Capabilities

### New Capabilities

- `clinical-concept-resolution`: Resolve user disease phrases to known clinical concepts, CID prefixes, or safe fallback lookup behavior.

### Modified Capabilities

- None.

## Impact

- Affected concept code: `src/semantic/concept_resolver.py`, `src/semantic/planner.py`.
- Affected SQL generation/repair code: diagnosis filters and description lookup paths.
- Affected tests: concept resolver, semantic planner filters, and direct SQL/query regression cases.
