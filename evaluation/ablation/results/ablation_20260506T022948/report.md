# Ablation Study Report

- **Date**: 2026-05-06T02:29:48.500486Z
- **Run ID**: 20260506T022948_c4872fb0
- **Git SHA**: 0ad7c80
- **Model**: gpt-4o-mini
- **Queries per variant**: 40

## Results

| ID | Variant | EX (%) | ΔEX (pp) | Easy | Medium | Hard | χ² | p-value | Tokens | Cost ($) |
|---|---|---|---|---|---|---|---|---|---|---|
| V0 | full_pipeline | 90.0 | — | 90.0 | 100.0 | 80.0 | None | None | 565,975 | 0.0720 |
| V2 | no_cot_reasoning | 92.5 | +2.5 | 90.0 | 100.0 | 86.7 | 1.000 | 0.500 | 566,808 | 0.0692 |
| V3 | no_validation | 40.0 | -50.0 | 90.0 | 40.0 | 6.7 | 20.000 | 0.000 | 521,756 | 0.0534 |
| V4 | no_repair | 80.0 | -10.0 | 90.0 | 86.7 | 66.7 | 2.667 | 0.125 | 547,491 | 0.0571 |
| V5 | no_table_selection_llm | 92.5 | +2.5 | 90.0 | 100.0 | 86.7 | 1.000 | 0.500 | 565,139 | 0.0680 |
| V6 | no_schema_enrichment | 92.5 | +2.5 | 90.0 | 100.0 | 86.7 | 1.000 | 0.500 | 522,450 | 0.0683 |
| V7 | no_rules | 87.5 | -2.5 | 90.0 | 93.3 | 80.0 | 0.333 | 0.625 | 463,104 | 0.0633 |
| V8 | zero_shot_raw | 42.5 | -47.5 | 90.0 | 46.7 | 6.7 | 19.000 | 0.000 | 374,280 | 0.0504 |
| V9 | no_semantic_planner | 90.0 | +0.0 | 90.0 | 93.3 | 86.7 | 0.000 | 1.000 | 502,622 | 0.0615 |
| V10 | no_semantic_plan_validation | 92.5 | +2.5 | 90.0 | 93.3 | 93.3 | 0.333 | 0.625 | 560,405 | 0.0680 |
| V11 | no_semantic_contract_validator | 92.5 | +2.5 | 90.0 | 93.3 | 93.3 | 0.333 | 0.625 | 563,100 | 0.0686 |
| V12 | no_semantic_repair_guidance | 90.0 | +0.0 | 90.0 | 100.0 | 80.0 | 0.000 | 1.000 | 565,255 | 0.0691 |

## Notes

- ΔEX = variant EX − V0 EX (full pipeline)
- Session IDs include Run ID to avoid LangGraph checkpoint reuse across ablation runs
- results_detail.csv includes EX comparison row counts, samples, and mismatch details
- McNemar mid-p test (exact) when discordant pairs < 25, chi-square continuity correction otherwise
- p < 0.05 suggests the component has a statistically significant impact on EX

## Decision Table

| Result | Decision |
|---|---|
| ΔEX ≈ 0 pp, p > 0.05 | Candidate for removal / simplification |
| ΔEX < −3 pp, p < 0.05 | Keep component |
| ΔEX < −3 pp, p > 0.05 | Effect present but not significant — keep, rerun with more queries |
