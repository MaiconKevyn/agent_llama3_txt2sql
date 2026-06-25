## Context

The semantic planner has an existing clinical concept resolver for respiratory disease, but the failing query used "causa respiratorias", which was extracted as a literal diagnosis description. Literal matching against `cid.DESCRICAO` is brittle because descriptions are abbreviated and may not include the user's exact words.

## Goals / Non-Goals

**Goals:**

- Resolve known disease concepts before falling back to description lookup.
- Handle common misspellings, missing accents, singular/plural variants, and noisy leading words such as "causa".
- Prefer CID codes or prefixes for known concepts.
- Keep fallback lookup for unknown clinical terms.

**Non-Goals:**

- Do not introduce a full medical ontology dependency.
- Do not change the meaning of existing resolved concepts.
- Do not remove diagnosis description lookup for unknown terms.

## Decisions

- Normalize extracted disease phrases before concept resolution by removing noisy context words and accents.
- Expand the respiratory concept aliases to cover malformed but common phrases, including "causa respiratorias" and "causas respiratorias".
- Apply concept resolution before creating `diagnostico_principal_descricao` filters.
- When a known concept resolves to prefixes such as `J%`, generate prefix filters and concept metadata rather than literal description filters.

## Risks / Trade-offs

- Aggressive normalization may over-map unrelated phrases -> mitigate with targeted aliases and tests for false positives.
- Prefix-based concepts are broad -> mitigate by preserving concept labels in metadata and using existing domain definitions.
- Unknown terms still need lookup -> keep fallback behavior unchanged.

## Migration Plan

- Add resolver tests for respiratory phrase variants and false-positive cases.
- Update planner extraction order so concept resolution happens before literal description fallback.
- Add SQL regression showing respiratory concepts use `DIAG_PRINC LIKE 'J%'`.
- No external data migration is required.
