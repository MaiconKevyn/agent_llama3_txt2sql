# Ablation Study Report

- **Date**: 2026-05-05T13:03:37.590448Z
- **Git SHA**: 0ad7c80
- **Model**: gpt-4o-mini
- **Queries per variant**: 40

## Results

| ID | Variant | EX (%) | ΔEX (pp) | Easy | Medium | Hard | χ² | p-value | Tokens | Cost ($) |
|---|---|---|---|---|---|---|---|---|---|---|
| V0 | full_pipeline | 0.0 | — | 0.0 | 0.0 | 0.0 | None | None | 587,561 | 0.0776 |
| V2 | no_cot_reasoning | 0.0 | +0.0 | 0.0 | 0.0 | 0.0 | 0.000 | 1.000 | 582,377 | 0.0742 |
| V3 | no_validation | 0.0 | +0.0 | 0.0 | 0.0 | 0.0 | 0.000 | 1.000 | 524,713 | 0.0623 |
| V4 | no_repair | 0.0 | +0.0 | 0.0 | 0.0 | 0.0 | 0.000 | 1.000 | 548,875 | 0.0679 |
| V5 | no_table_selection_llm | 0.0 | +0.0 | 0.0 | 0.0 | 0.0 | 0.000 | 1.000 | 581,995 | 0.0742 |
| V6 | no_schema_enrichment | 0.0 | +0.0 | 0.0 | 0.0 | 0.0 | 0.000 | 1.000 | 535,320 | 0.0708 |
| V7 | no_rules | 0.0 | +0.0 | 0.0 | 0.0 | 0.0 | 0.000 | 1.000 | 484,256 | 0.0666 |
| V8 | zero_shot_raw | 0.0 | +0.0 | 0.0 | 0.0 | 0.0 | 0.000 | 1.000 | 377,592 | 0.0499 |
| V9 | no_semantic_planner | 0.0 | +0.0 | 0.0 | 0.0 | 0.0 | 0.000 | 1.000 | 501,380 | 0.0637 |
| V10 | no_semantic_plan_validation | 0.0 | +0.0 | 0.0 | 0.0 | 0.0 | 0.000 | 1.000 | 560,825 | 0.0714 |
| V11 | no_semantic_contract_validator | 0.0 | +0.0 | 0.0 | 0.0 | 0.0 | 0.000 | 1.000 | 562,281 | 0.0717 |
| V12 | no_semantic_repair_guidance | 0.0 | +0.0 | 0.0 | 0.0 | 0.0 | 0.000 | 1.000 | 564,590 | 0.0725 |

## Notes

- ΔEX = variant EX − V0 EX (full pipeline)
- McNemar mid-p test (exact) when discordant pairs < 25, chi-square continuity correction otherwise
- p < 0.05 suggests the component has a statistically significant impact on EX

## Decision Table

| Result | Decision |
|---|---|
| ΔEX ≈ 0 pp, p > 0.05 | Candidate for removal / simplification |
| ΔEX < −3 pp, p < 0.05 | Keep component |
| ΔEX < −3 pp, p > 0.05 | Effect present but not significant — keep, rerun with more queries |
