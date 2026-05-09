# Ablation Study Report

- **Date**: 2026-05-06T23:51:39.041268Z
- **Run ID**: 20260506T235139_85bd7469
- **Git SHA**: 0ad7c80
- **Model**: gpt-4o-mini
- **Queries per variant**: 40

## Results

| ID | Variant | EX (%) | ΔEX (pp) | Easy | Medium | Hard | χ² | p-value | Tokens | Cost ($) |
|---|---|---|---|---|---|---|---|---|---|---|
| V0 | full_pipeline | 95.0 | — | 100.0 | 93.3 | 93.3 | None | None | 565,710 | 0.0735 |
| V2 | no_cot_reasoning | 95.0 | +0.0 | 100.0 | 93.3 | 93.3 | 0.000 | 1.000 | 565,773 | 0.0734 |
| V3 | no_validation | 40.0 | -55.0 | 90.0 | 40.0 | 6.7 | 22.000 | 0.000 | 522,017 | 0.0607 |
| V4 | no_repair | 75.0 | -20.0 | 100.0 | 80.0 | 53.3 | 8.000 | 0.004 | 548,948 | 0.0668 |
| V5 | no_table_selection_llm | 95.0 | +0.0 | 100.0 | 93.3 | 93.3 | 0.000 | 1.000 | 567,243 | 0.0728 |
| V6 | no_schema_enrichment | 97.5 | +2.5 | 100.0 | 100.0 | 93.3 | 1.000 | 0.500 | 518,246 | 0.0706 |
| V7 | no_rules | 87.5 | -7.5 | 100.0 | 86.7 | 80.0 | 3.000 | 0.125 | 461,669 | 0.0635 |
| V8 | zero_shot_raw | 40.0 | -55.0 | 90.0 | 46.7 | 0.0 | 22.000 | 0.000 | 376,921 | 0.0516 |
| V9 | no_semantic_planner | 95.0 | +0.0 | 100.0 | 93.3 | 93.3 | 0.000 | 1.000 | 506,583 | 0.0640 |
| V10 | no_semantic_plan_validation | 87.5 | -7.5 | 100.0 | 86.7 | 80.0 | 3.000 | 0.125 | 562,309 | 0.0718 |
| V11 | no_semantic_contract_validator | 92.5 | -2.5 | 100.0 | 93.3 | 86.7 | 1.000 | 0.500 | 559,974 | 0.0733 |
| V12 | no_semantic_repair_guidance | 87.5 | -7.5 | 100.0 | 80.0 | 86.7 | 3.000 | 0.125 | 565,372 | 0.0731 |

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
