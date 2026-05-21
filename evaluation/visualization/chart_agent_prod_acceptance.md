# Chart Agent Production Acceptance Log

## Incidentes

| Data | Caso | Sintoma | Camada raiz | Fix generalizavel | Evidencia | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-05-21 | PROD_MORT_LOC_001 | erro bruto de `SEMANTIC PLAN ERROR` em pergunta por municipio | semantic_planner + semantic_validator + chart_plan | perguntas plurais de ranking por metrica sem limite explicito usam top 10 legivel; ranking global por janela `ROW_NUMBER()/RANK()` com `rank <= N` e aceito; ChartPlan reconhece entidade plural como dimensao visual | `run_chart_agent_prod_eval.py --run-agent --only PROD_MORT_LOC_001`: success_rate=1.0; SQL com `LIMIT 10`; ChartSpec bar `municipio` x `taxa_mortalidade` | fixed |

## Gates

| Gate | Target | Resultado | Evidencia |
| --- | --- | --- | --- |
| Curated prod canary | 100% success | pass | `run_chart_agent_prod_eval.py`: success_rate=1.0, chart_contract_validity=1.0, semantic_dimension_validity=1.0 |
| Online full repeat 1 | 100% success | not_run | pending |
| Online full repeat 2 | 100% success | not_run | pending |
| Zero raw internal errors | 0 | pass | offline canary and `PROD_MORT_LOC_001` online both no_raw_internal_error=1.0 |
| Frontend smoke | pass | not_run | pending |
