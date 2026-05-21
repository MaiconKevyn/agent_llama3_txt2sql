# Chart Agent Production Acceptance Log

## Incidentes

| Data | Caso | Sintoma | Camada raiz | Fix generalizavel | Evidencia | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-05-21 | PROD_MORT_LOC_001 | erro bruto de `SEMANTIC PLAN ERROR` em pergunta por municipio | semantic_planner + semantic_validator + chart_plan | perguntas plurais de ranking por metrica sem limite explicito usam top 10 legivel; ranking global por janela `ROW_NUMBER()/RANK()` com `rank <= N` e aceito; ChartPlan reconhece entidade plural como dimensao visual | `run_chart_agent_prod_eval.py --run-agent --only PROD_MORT_LOC_001`: success_rate=1.0; SQL com `LIMIT 10`; ChartSpec bar `municipio` x `taxa_mortalidade` | fixed |
| 2026-05-21 | PROD_CANARY_BATCH_002 | canary online caiu para 92,5% por suporte minimo, KPI, procedimento temporal, obstetricia, sexo temporal e menor taxa | semantic_planner + chart_plan + deterministic_chart_sql + prod_eval | suporte minimo reconhece `pelo menos`; KPI escalar gera uma unica metrica; procedimento temporal usa serie limitada por top procedimentos; obstetricia aplica `ESPEC = 2`; sexo exige label via CASE sem falso positivo no eval; rankings de menor taxa ordenam ASC | `run_chart_agent_prod_eval.py --run-agent --only` nos 6 casos: todos success_rate=1.0; full online seeds `20260521` e `20260522`: success_rate=1.0 | fixed |

## Gates

| Gate | Target | Resultado | Evidencia |
| --- | --- | --- | --- |
| Unit/contract regression | 100% pass | pass | `pytest tests/test_semantic_layer.py tests/test_semantic_validators.py tests/test_visualization_chart_plan.py tests/test_api_chart_contract.py tests/test_chart_agent_prod_eval.py -q`: pass |
| Chart engine eval | 100% pass | pass | `chart_evaluation_20260521T073229Z.json`: all chart metrics 1.0 |
| Curated prod canary offline | 100% success | pass | `chart_agent_prod_eval_20260521T073229Z.json`: success_rate=1.0, chart_contract_validity=1.0, sql_invariant_validity=1.0, semantic_dimension_validity=1.0 |
| Online full repeat 1 | 100% success | pass | seed `20260521`, `chart_agent_prod_eval_20260521T071006Z.json`: success_rate=1.0, no_raw_internal_error=1.0 |
| Online full repeat 2 | 100% success | pass | seed `20260522`, `chart_agent_prod_eval_20260521T073207Z.json`: success_rate=1.0, no_raw_internal_error=1.0 |
| Zero raw internal errors | 0 | pass | offline and online canaries report no_raw_internal_error=1.0; API/frontend tests sanitize `SEMANTIC PLAN ERROR` |
| User-facing error boundary | no raw internal details | pass | `_build_query_response`, `process_query`, frontend app and proxy sanitize known internal markers |
| Frontend smoke | pass | pass | screenshots captured for desktop/mobile: `20260521T_frontend_smoke_rerun_desktop.png`, `20260521T_frontend_smoke_rerun_mobile.png` |

## Status final

Sem P0/P1 aberto para geracao de graficos no corpus production canary atual. Novos incidentes devem entrar neste log com causa raiz, regra generalizavel, teste de regressao e repeticao do canary online antes de release.
