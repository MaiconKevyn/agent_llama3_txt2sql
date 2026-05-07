# Ablation Study Report

- **Date**: 2026-05-05T21:43:05.346384Z
- **Git SHA**: 0ad7c80
- **Model**: gpt-4o-mini
- **Queries per variant**: 40

## Results

| ID | Variant | EX (%) | ΔEX (pp) | Easy | Medium | Hard | χ² | p-value | Tokens | Cost ($) |
|---|---|---|---|---|---|---|---|---|---|---|
| V0 | full_pipeline | 82.5 | — | 90.0 | 93.3 | 66.7 | None | None | 579,850 | 0.0760 |
| V2 | no_cot_reasoning | 82.5 | +0.0 | 90.0 | 93.3 | 66.7 | 0.000 | 1.000 | 575,387 | 0.0720 |
| V3 | no_validation | 40.0 | -42.5 | 90.0 | 40.0 | 6.7 | 17.000 | 0.000 | 524,849 | 0.0623 |
| V4 | no_repair | 77.5 | -5.0 | 90.0 | 93.3 | 53.3 | 1.000 | 0.375 | 550,209 | 0.0661 |
| V5 | no_table_selection_llm | 72.5 | -10.0 | 90.0 | 80.0 | 53.3 | 4.000 | 0.062 | 582,303 | 0.0729 |
| V6 | no_schema_enrichment | 80.0 | -2.5 | 90.0 | 93.3 | 60.0 | 0.333 | 0.625 | 538,758 | 0.0707 |
| V7 | no_rules | 75.0 | -7.5 | 90.0 | 86.7 | 53.3 | 3.000 | 0.125 | 485,962 | 0.0668 |
| V8 | zero_shot_raw | 42.5 | -40.0 | 90.0 | 46.7 | 6.7 | 16.000 | 0.000 | 377,824 | 0.0497 |
| V9 | no_semantic_planner | 80.0 | -2.5 | 90.0 | 86.7 | 66.7 | 0.200 | 0.688 | 512,619 | 0.0645 |
| V10 | no_semantic_plan_validation | 87.5 | +5.0 | 90.0 | 100.0 | 73.3 | 0.667 | 0.453 | 564,519 | 0.0680 |
| V11 | no_semantic_contract_validator | 87.5 | +5.0 | 90.0 | 93.3 | 80.0 | 0.667 | 0.453 | 566,940 | 0.0686 |
| V12 | no_semantic_repair_guidance | 80.0 | -2.5 | 90.0 | 86.7 | 66.7 | 0.333 | 0.625 | 653,646 | 0.0786 |

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
