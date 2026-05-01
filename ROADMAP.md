# Roadmap de Melhorias — DataVisSUS TXT2SQL Agent

> Documento gerado em 2026-04-26 a partir de análise técnica do repositório, revisão do
> paper CBMS (`docs/CBMS/bare_conf_v2.tex`), pareceres dos revisores
> (`Documentos/obsidian/DaVint/Reviews.md`), histórico consolidado de mudanças
> (`Documentos/obsidian/DaVint/Mudanças CBMS.md`) e cruzamento com o vault de
> AI/Software Engineering em `Documentos/obsidian/`.
>
> Objetivo: consolidar **próximos passos** para evoluir o projeto em
> organização, profissionalismo, versionamento, reprodutibilidade,
> monitoramento, logs, evaluation padronizado e adoção de boas práticas
> de AI Engineering — com foco em **acurácia final** do agente Text-to-SQL.

---

## 0. Snapshot atual (linha de base)

| Eixo | Estado hoje |
|---|---|
| Pipeline | LangGraph 9 estágios: classify → list_tables → get_schema → plan_gate → query_planner → reasoning → generate_sql → vote_sql → validate_sql → execute_sql → repair → response. Caminho multi-query opcional via `multi_sql_executor`/`multi_verifier`/`result_synthesizer`. |
| Modelo | GPT-4o-mini (OpenAI), `temperature=0`, structured output Pydantic + self-consistency 3 candidatos. |
| Acurácia | EX = **93,3 %** (LangGraph) vs **90,0 %** (single-shot baseline). Hard +10,0 pp; Medium −2,5 pp. McNemar p = 0,289 com m = 8 pares discordantes. |
| Benchmark | `evaluation/ground_truth.json` + `ground_truth_v2.json`, 120 queries, três tiers (Easy/Medium/Hard). |
| Avaliação | DAG (`evaluation/dag/pipeline.py`) com `run_dag_evaluation.py`, métricas EX/CM/EM em `evaluation/metrics/`. |
| Observabilidade | LangSmith opcional, `RotatingFileHandler` em `logs/orchestrator_v3.log`, `StructuredFormatter` em `src/utils/logging_config.py`. |
| Tests | 8 arquivos em `tests/`, foco em SQL safety, classification, orchestrator. Sem cobertura medida, sem mutation testing. |
| Reprodutibilidade | `requirements.txt` com versões pinadas, `.env.example` presente, sem `pyproject.toml` / `uv.lock`, sem container, sem seeds explícitas. |
| Documentação | `README.md` completo; CLAUDE.md atual com changelog manual de checkpoints; sem ADRs. |

### Pontos fortes a preservar

- **Baseline controlado idêntico** ao agente (mesmas RULES A–O e schema), citado pelos três revisores como ponto forte.
- **Heurística + cascata 3 estágios para seleção de tabela** (regex → embedding → LLM): rápida, auditável.
- **Self-consistency (vote majority)** em `vote_sql.py` já implementado.
- **Plan gate determinístico** decidindo entre single/multi/CoT antes de chamar LLM.
- **Estrutura modular** em `src/agent/*` (workflow, state, nodes especializados) — limites claros.

### Sintomas / dores principais

1. Sem **ablation por estágio** — não sabemos quanto de EX vem de table-selection, CoT, validação, repair.
2. Regressão Medium (−2,5 pp): single-shot vence em queries cujo gargalo é a etapa de seleção de tabela do agente.
3. **Gargalo dominante = table-selection errors** (2 casos `c=2`) que produzem SQL plausível mas semanticamente errado e fogem do repair.
4. Benchmark pequeno (n = 120) e sem participação clínica → poder estatístico limitado (p = 0,289).
5. `nodes.py` virtualmente vazio (86 LoC) mas arquivos derivados — `sql_generation.py` (689 LoC), `state.py` (711 LoC), `orchestrator.py` (917 LoC) — flertam com god-files.
6. Logs e métricas não persistidos de forma estruturada por query (apenas EX agregado por run; sem token/latency/erro por estágio).
7. Sem CI, sem lint estrito, sem coverage gate, sem `pip-audit`. CLAUDE.md no `.gitignore`.
8. Reprodutibilidade frágil: nenhuma seed para self-consistency, sem snapshot de DB, dependências em `requirements.txt` plano (sem lock determinístico).

---

## 1. Eixo Acurácia (resposta direta à pergunta principal)

### CP-A1 · Ablation por estágio _(prioridade máxima — pedido por R1, R3)_

**Objetivo:** Quantificar a contribuição marginal de cada estágio para o EX e para os dois pontos de falha (Hard +10 pp, Medium −2,5 pp).

- [ ] Adicionar flags boolean em `src/application/config/simple_config.py:OrchestratorConfig`: `disable_table_selection_llm`, `disable_cot_planning`, `disable_self_repair`, `disable_self_consistency`, `disable_validation`
- [ ] Modificar `src/agent/workflow.py:create_langgraph_sql_workflow` para respeitar cada flag ao montar o grafo
- [ ] Criar tarefa `run_ablation_matrix` em `evaluation/dag/tasks.py` com 8 variantes: full pipeline + 5 estágios off individualmente + zero-rules + zero-shot raw
- [ ] Rodar ablation completa (120 queries × 8 variantes) e salvar em `evaluation/results/ablation_<ts>.csv`
- [ ] Gerar Markdown report com tabela EX × variante × tier + McNemar pareado de cada variante vs full

**Saída:** tabela ablation pronta para inserir no paper (Future Work → Results).

---

### CP-A2 · Ataque ao gargalo de table-selection

**Diagnóstico:** os 2 casos `c=2` (Medium + Hard) vêm de tabela errada mapeada que produz SQL plausível e foge do repair.

- [ ] Implementar **LLM verifier** após `EmbeddingTableSelector` em `src/agent/table_selector.py`: segunda chamada com prompt "dado o user_query e os candidatos, liste conflitos semânticos segundo RULES A, B, H, M"
- [ ] Adicionar pós-validação em `src/agent/table_selection.py`: se query menciona `morte/óbito/falecimento` e set contém `primaryICD`, levantar warning e forçar reroute para `deathICD`
- [ ] Implementar **confidence threshold dinâmico**: se heuristic confidence < 0.85 *e* embeddings discordam da heurística, obrigar passagem pela LLM com chain-of-verification
- [ ] Escrever testes unitários para as 3 mudanças acima em `tests/test_table_selection.py`
- [ ] Rodar eval full (120 q) antes/depois e confirmar EX Medium ≥ 99 % e Hard failures ≤ 4

---

### CP-A3 · Multi-query path realmente avaliado

- [ ] Auditar o GT (120 queries) e anotar `expected_plan_type` em cada item de `evaluation/ground_truth_v2.json`
- [ ] Adicionar métrica `planner_routing_correct@N` no relatório do DAG
- [ ] Investigar `single_fallback_active` no log do run mais recente e identificar se está disparando em casos onde multi venceria
- [ ] Criar pelo menos 10 queries Hard direcionadas para cada plan type (`fanout_concat`, `bind_then_query`, `verification_side_query`) e medir EX do caminho multi vs single

---

### CP-A4 · Engenharia de domínio: rules audit + zero-rule baseline _(pedido R1)_

- [ ] Criar variant "no-rules": remover RULES A–O do system prompt mantendo apenas schema e rodar 120 q → reportar ΔEX
- [ ] Criar variant "no-schema-enrichment": desabilitar `_enhance_sus_schema_context` e rodar 120 q → reportar ΔEX
- [ ] Criar variant "reflection-rules": substituir RULES por instrução de auto-descoberta via one-shot exemplo → comparar
- [ ] Documentar resultado das 3 variants em `evaluation/results/rules_ablation_<ts>.md`
- [ ] Incluir conclusão sobre peso das regras vs arquitetura nos trabalhos futuros do paper

---

### CP-A5 · Modelo & stack

- [ ] Rodar eval full com **Claude Sonnet 4.6** via `OrchestratorConfig.switch_model` e reportar EX vs GPT-4o-mini por tier
- [ ] Rodar eval full com **GPT-4o** e comparar custo-benefício (EX × tokens × latency)
- [ ] Implementar **prompt caching** quando usar modelo Anthropic: `cache_control` no system prompt + RULES + schema_context (>5 KB elegível)
- [ ] Avaliar se fine-tuning Qwen 7B (ver `Plano Fine-tuning Qwen 7B DATASUS.md`) é justificado com base nos resultados de CP-A1 e CP-A4

---

### CP-A6 · Reflection / self-debug after first execution

- [ ] Implementar em `src/agent/execution.py`: pós-checagem `if row_count == 0 and is_count_or_aggregation_query → trigger reflection`
- [ ] Criar prompt de reflection: "a query devolveu 0 linhas; dado o schema e a pergunta original, há filtro incorreto? sugira SQL corrigida"
- [ ] Limitar a 1 tentativa de reflection (sem loop) e logar `reflection_triggered=True` no evento de stage
- [ ] Adicionar métrica `reflection_rescue_rate` no relatório DAG
- [ ] Testar em 5 casos Hard do GT onde resultado correto é não-vazio e o agente retornou 0 linhas

---

### CP-A7 · Expansão e qualidade do benchmark _(pedido R1, R2, R3)_

- [ ] Mapear os 6 Hard queries que ninguém acerta (benchmark's difficulty ceiling) e criar pelo menos 10 variantes mais acessíveis como novos exemplos de treinamento/ablation
- [ ] Adicionar campos `expected_tables`, `expected_join_count`, `expected_plan_type`, `expected_window_function`, `clinical_validity_flag` em `evaluation/ground_truth_v2.json`
- [ ] Elaborar 120 novas queries com pelo menos um especialista clínico: 20 Easy, 40 Medium, 60 Hard
- [ ] Incluir dimensões sub-representadas: janelas temporais móveis, cohort definitions, risk-adjusted metrics, peer comparison
- [ ] Consolidar em `evaluation/ground_truth_v3.json` mantendo retro-compatibilidade com v2
- [ ] Rodar eval completa em v3 e reportar EX com n = 240 para nova submissão

---

## 2. Eixo Organização & Profissionalismo

### CP-O1 · Migração para `pyproject.toml` + `uv`

- [x] Criar `pyproject.toml` unificando metadados de projeto e dependências (substitui `requirements.txt`)
- [x] Adicionar `.python-version` com versão exata (ex: `3.11`)
- [x] Gerar `uv.lock` determinístico via `uv lock`
- [x] Manter `requirements.txt` como fallback de compat se necessário
- [x] Atualizar `README.md` com instruções de setup via `uv`

---

### CP-O2 · Quebrar god-files (> 300 LoC sem justificativa)

| Arquivo | LoC | Sugestão |
|---|---|---|
| `src/agent/orchestrator.py` | 917 | Extrair `MetricsCollector`, `LoggingSetup`, `WorkflowVisualizer`, `InteractiveSession` |
| `src/agent/state.py` | 711 | Separar `state_models.py` (TypedDict + dataclasses) de `state_helpers.py` |
| `src/agent/sql_generation.py` | 689 | Extrair para `prompt_builder.py`, `schemas.py`, `self_consistency.py` |
| `src/agent/workflow.py` | 707 | Mover funções `route_after_*` para `routing.py` |
| `src/agent/table_selection.py` | 529 | Promover heuristics para `table_selection/heuristics.py` |

- [x] Extrair `MetricsCollector` de `orchestrator.py` para `src/agent/metrics.py`
- [x] Extrair `LoggingSetup` de `orchestrator.py` para `src/utils/logging_setup.py`
- [x] Extrair `WorkflowVisualizer` + `InteractiveSession` de `orchestrator.py` para `src/agent/cli_session.py`
- [x] Separar `state.py` em `state_models.py` + `state_helpers.py`
- [x] Extrair `_build_pregeneration_hints`, `SQLOutput`, `_generate_sql_candidates` de `sql_generation.py` para módulos próprios
- [x] Mover funções `route_after_*` de `workflow.py` para `src/agent/routing.py`
- [x] Garantir que todos os testes existentes continuam passando após cada refactor

---

### CP-O3 · ADRs (Architecture Decision Records)

- [ ] Criar pasta `docs/adrs/`
- [ ] Escrever ADR-001: por que LangGraph e não LangChain Agents puro
- [ ] Escrever ADR-002: por que GPT-4o-mini como modelo padrão
- [ ] Escrever ADR-003: cascata 3 estágios para table selection (regex → embedding → LLM)
- [ ] Escrever ADR-004: SQL repair com retry budget bounded (2 gen, 3 val, 15 cycles)
- [ ] Escrever ADR-005: snowflake schema + DuckDB para OLAP local
- [ ] Escrever ADR-006: política de versionamento de prompts e RULES A–O

---

### CP-O4 · Reorganizar `evaluation/` + `baselines/`

- [ ] Criar `evaluation/benchmarks/` e mover `ground_truth_v*.json` para lá
- [ ] Criar `evaluation/runners/` e mover `run_dag_evaluation.py`, `run_rich_prompt_baseline.py` para lá
- [ ] Remover outputs duplicados de `evaluation/dag/` (manter apenas código do pipeline, não resultados)
- [ ] Criar `evaluation/README.md` explicando como rodar cada runner e como ler os relatórios

---

### CP-O5 · `CLAUDE.md` versionado (remover do .gitignore)

- [x] Remover `CLAUDE.md` da linha de exclusão em `.gitignore`
- [x] Adicionar `CLAUDE.local.md` ao `.gitignore` para overrides pessoais
- [x] Revisar conteúdo atual do `CLAUDE.md` e atualizar com base no template do vault

---

## 3. Eixo Versionamento

### CP-V1 · Conventional Commits + Changelog automatizado

- [x] Documentar adoção de Conventional Commits no `CONTRIBUTING.md` ou `README.md`: `feat:`, `fix:`, `chore:`, `docs:`, `eval:`, `prompt:`
- [x] Configurar `git-cliff` ou `release-please` para gerar `CHANGELOG.md` automaticamente
- [x] Criar primeira tag semântica (`v0.3.0`) marcando o estado atual (EX = 93,3 %)
- [x] Adicionar pre-commit hook que valida formato do commit message

---

### CP-V2 · Versionamento de prompts

- [ ] Criar pasta `prompts/v1/` e extrair RULES A–O e templates de `table_templates.py` para arquivos `.txt`/`.md` versionados
- [ ] Adicionar campo `prompt_version` em `OrchestratorConfig` (default: `"v1"`)
- [ ] Garantir que cada `evaluation/results/*.json` grave: `prompt_version`, `rules_version`, `model_id`, `git_sha`
- [ ] Criar script `evaluation/runners/prompt_regression_test.py` que roda 40 queries críticas sempre que um arquivo em `prompts/` é modificado

---

### CP-V3 · Versionamento de dataset

- [ ] Adicionar campos `version`, `created_at`, `created_by`, `clinical_review_at` em `ground_truth_v2.json`
- [ ] Criar tag git (`benchmark-v2`) no commit correspondente
- [ ] Avaliar uso de `dvc` ou `git-lfs` se snapshot binário do DB entrar no repo

---

## 4. Eixo Reprodutibilidade

### CP-R1 · Determinismo da geração SQL

- [ ] Adicionar `seed=42` em `ChatOpenAI(...)` dentro de `_generate_sql_candidates` em `src/agent/sql_generation.py`
- [ ] Capturar `system_fingerprint` e `model` de cada resposta da API e logar no evento de stage
- [ ] Atualizar `README.md` com nota explicando que `temperature=0` reduz variabilidade mas não garante determinismo (alinhado com correção já feita no paper)

---

### CP-R2 · Snapshot reproduzível do DB

- [ ] Criar `scripts/dump_db_snapshot.py` gerando dump comprimido em `data/snapshots/sihrd_<sha>_<date>.duckdb.gz`
- [ ] Adicionar campo `db_snapshot_sha256` em cada JSON de resultado de evaluation
- [ ] Criar `infra/migrations/` com DDL versionado para reproduzir o schema do zero

---

### CP-R3 · Container minimal reproduzível

- [ ] Criar `Dockerfile` multi-stage: base `python:3.11-slim`, non-root user, `HEALTHCHECK` em `/health`
- [ ] Criar `docker-compose.yml` subindo API + DuckDB seedado + frontend
- [ ] Documentar em `README.md`: `docker compose up` deve replicar EX = 93,3 % com snapshot correto montado

---

### CP-R4 · `make` ou `task` para fluxos comuns

- [ ] Criar `Makefile` com targets: `setup`, `lint`, `test`, `eval`, `eval-fast`, `eval-ablation`, `report`
- [ ] Documentar cada target no `README.md` com exemplo de saída esperada

---

## 5. Eixo Monitoramento & Logs

### CP-M1 · Logs estruturados por query/stage

- [ ] Definir schema do evento JSON de stage: `{query_id, session_id, stage, latency_ms, llm_calls, prompt_tokens, completion_tokens, cost_usd, status, error_kind}`
- [ ] Instrumentar cada nó principal (`classify`, `list_tables`, `generate_sql`, `validate_sql`, `execute_sql`, `repair_sql`) para emitir o evento ao final
- [ ] Configurar output em `logs/events.jsonl` com rotação diária (appended)
- [ ] Criar sub-loggers por estágio: `txt2sql.classify`, `txt2sql.generate_sql`, etc.

---

### CP-M2 · Métricas observability-grade

- [ ] Adicionar dependência `opentelemetry-sdk` + `prometheus-client` em `pyproject.toml`
- [ ] Instrumentar spans por nó do LangGraph via LangGraph callbacks
- [ ] Expor endpoint `/metrics` na API FastAPI com métricas Prometheus:
  - [ ] `txt2sql_request_total{outcome=success|error|repair_rescued}`
  - [ ] `txt2sql_latency_seconds_bucket{stage=...}`
  - [ ] `txt2sql_llm_tokens_total{stage=...}`
  - [ ] `txt2sql_repair_attempts`
  - [ ] `txt2sql_table_selection_confidence_bucket`
- [ ] Validar métricas com `curl localhost:8000/metrics` em smoke test

---

### CP-M3 · Tracing LangSmith por padrão

- [ ] Tornar LangSmith ativo por default (não apenas quando `LANGSMITH_TRACING=true` no env): fallback silencioso se key ausente
- [ ] Adicionar `plan_type` e `tier` no `run_name` de cada trace para facilitar filtros
- [ ] Criar view/filter salvo no LangSmith: "queries com EX=0" baseado em tag `ex_score=0`

---

### CP-M4 · Dashboard local de evaluation

- [ ] Criar `evaluation/dashboard.py` (Streamlit ou Gradio) lendo `evaluation/results/*.json`
- [ ] Implementar visualização: tendência EX por commit/hora
- [ ] Implementar heatmap: erro por tabela × tier
- [ ] Implementar drill-down: query → prompt → SQL gerado → resultado → gold SQL
- [ ] Documentar como rodar: `make dashboard` ou `streamlit run evaluation/dashboard.py`

---

### CP-M5 · Erro taxonomy persistente

- [ ] Garantir que `failure_taxonomy` em `state.py` seja preenchido em **todos** os paths de erro (não só em alguns)
- [ ] Definir e documentar a lista canônica de categorias: `schema_error`, `syntax_error`, `wrong_table_selection`, `wrong_value_mapping`, `wrong_aggregation`, `wrong_window`, `null_semantics`, `missing_join`, `wrong_filter`, `cot_drift`, `repair_loop`
- [ ] Persistir `failure_taxonomy` em cada item de `evaluation/results/*.json`
- [ ] Adicionar contagem por categoria no relatório do DAG

---

## 6. Eixo Evaluation padronizado e organizado

### CP-E1 · Métricas além de EX

- [ ] Adicionar ao relatório DAG: **Valid SQL rate** (queries que passam `validate_sql` na primeira tentativa)
- [ ] Adicionar: **First-pass success rate** (executa correto sem nenhuma iteração de repair)
- [ ] Adicionar: **Repair-rescued rate** (queries que falharam e foram salvas pelo repair)
- [ ] Adicionar: **Average prompt + completion tokens per query por tier** (responde overhead do Revisor 2)
- [ ] Adicionar: **p95 latency por tier** (responde Limitação 4 do paper)
- [ ] Garantir que CM e EM (já implementados) apareçam destacados no relatório final, não apenas como campos opcionais

---

### CP-E2 · Eval agentic com LLM-as-judge para mensagem final

- [ ] Selecionar 30 queries representativas e coletar julgamento humano (binary: resposta correta/incorreta)
- [ ] Calibrar GPT-4o como juiz: medir agreement com humano → prosseguir só se ≥ 0.85
- [ ] Implementar `evaluation/metrics/llm_judge.py` com métricas: `answer_relevance`, `groundedness`, `clinical_safety_flag`
- [ ] Integrar LLM-as-judge como etapa opcional no DAG (flag `--include-llm-judge`)

---

### CP-E3 · Regression suite rápida

- [ ] Criar `evaluation/regression_set.json` com 40 queries críticas (queries do paper + bordas de RULES A–O + casos que falharam historicamente)
- [ ] Criar runner `evaluation/runners/run_regression.py` que completa em ≤ 5 min
- [ ] Configurar CI para rodar regression em todo PR e comentar tabela EX antes/depois

---

### CP-E4 · Failure analysis automatizada

- [ ] Implementar `evaluation/runners/failure_analysis.py`: para cada query com EX = 0, extrair stage de falha, diff SQL gerada vs gold, e sub-string do prompt como provável causa
- [ ] Adicionar chamada LLM opcional: "qual RULE A–O foi violada nesta SQL?" → gravar em `failure_log`
- [ ] Output em `evaluation/results/failure_log_<ts>.md` com seção por query

---

### CP-E5 · CI/CD + quality gates

- [ ] Criar `.github/workflows/ci.yml` com:
  - [ ] Etapa 1 — Lint: `ruff check src/`, `ruff format --check src/`, `mypy --strict src/`
  - [ ] Etapa 2 — Testes: `pytest --cov=src --cov-fail-under=80`
  - [ ] Etapa 3 — Segurança: `pip-audit`
  - [ ] Etapa 4 — Regression (label `eval`): rodar `run_regression.py` e comentar tabela EX no PR
- [ ] Configurar pre-commit hooks: `ruff`, `mypy`, `gitleaks` (scan de secrets)

---

### CP-E6 · Mutation testing nos módulos críticos

- [ ] Instalar `mutmut` e adicionar ao `pyproject.toml` como dev dependency
- [ ] Rodar: `mutmut run --paths-to-mutate src/agent/validation.py src/agent/multi_verifier.py src/agent/table_selection.py`
- [ ] Reportar mutation score e garantir ≥ 70 % nos três módulos
- [ ] Inspecionar mutantes vivos e adicionar testes faltantes

---

## 7. Eixo Boas práticas AI Engineering (cruzamento com vault)

Mapeando direto do `LLM Project Checklist`, `Project Checklist`, `Project Review Checklist`:

| Item do vault | Estado | Ação |
|---|---|---|
| Prompt versionado em repo | parcial | CP-V2 |
| Output format especificado | ✅ `SQLOutput` Pydantic | manter |
| Tool schemas estritos | parcial | revisar `schema_node.py`, `tools/` |
| Max iterations / timeouts configurados | ✅ 15 cycles, 3 retries | documentar em ADR |
| Cada tool call rastreado | parcial | CP-M1 |
| Baseline medido | ✅ rich_prompt_baseline | manter |
| Eval dataset existe | ✅ 120 queries | ampliar (CP-A7) |
| Métricas e thresholds definidos | parcial | CP-E1 |
| Regression eval pré-release | ❌ | CP-E3 |
| Bad cases armazenados | parcial (ex_zero files) | CP-E4 |
| Cost tracking | ❌ | CP-M2 |
| Latency p50/p95 | ❌ | CP-M2 |
| Token usage | ❌ | CP-M2 |
| Pre-commit hooks (ruff, mypy, gitleaks) | ❌ | CP-E5 |
| pyproject + uv lock | ❌ | CP-O1 |
| Mutation score | ❌ | CP-E6 |
| OpenTelemetry / structured tracing | parcial | CP-M2 |
| OWASP LLM (prompt injection) | parcial | revisar contexto multi-turn que chega no prompt |
| ADRs | ❌ | CP-O3 |

---

## 8. Eixo "fora da caixa" — opiniões de especialista

- [ ] **Classificador denso para schema linking** — treinar logistic regression sobre embeddings BGE-M3 + one-hot RULES match usando o GT como rótulos; medir table-selection accuracy isolado (inspiração: MAC-SQL schema linker)
- [ ] **SQL parsing como guardrail** — generalizar `evaluation/metrics/improved_sql_parser.py` para o validation node; detectar `LIMIT` sem ORDER BY, `JOIN` sem ON, `COUNT(DISTINCT col1, col2)` ilegais em DuckDB
- [ ] **Constrained decoding** — se migrar para modelo open (Qwen/Llama via vLLM), aplicar grammar constrained decoding (LMQL/Outlines/XGrammar); para OpenAI, adicionar post-parser sqlglot reescrevendo para SQL canônica
- [ ] **Calibração de confiança** — calibrar `SQLOutput.confidence` via Platt scaling em held-out set (30 queries); ativar modo seletivo: confiança < threshold → pedir clarificação ao usuário
- [ ] **Plan-and-revise** — após `execute_sql` com sucesso, rodar reflection: "o resultado responde literalmente a pergunta?"; ativar apenas em Hard tier para controlar custo
- [ ] **Cache Q→SQL aprovadas** — implementar FAISS sobre pares `(question, gold_sql, executed_at)` com EX=1; reusar para cosine > 0.95; reduz custo, latência e variabilidade
- [ ] **Audit trail signing** — registrar hash SHA-256 de `(user_query, sql_query, results_summary, timestamp)` em append-only log com chained hash para compliance LGPD/healthcare
- [ ] **Custo como argumento de paper** — implementar CP-M2, gerar tabela `tokens/query × tier × variante`; incluir como nova seção na próxima submissão respondendo diretamente ao Revisor 2

---

## 9. Plano de execução priorizado

| Sprint | Objetivo | Checkpoints | Saída tangível |
|---|---|---|---|
| **S1 (1 semana)** | Resposta direta ao paper / reviewers | CP-A1, CP-A4, CP-M1, CP-E1 | tabela ablation + tabela cost/latency → 2 tabelas novas no paper |
| **S2 (1 semana)** | Atacar o gargalo de acurácia | CP-A2, CP-A6, CP-V2 | EX Medium ≥ 99 %; EX overall ≥ 95 % |
| **S3 (2 semanas)** | Profissionalismo & reprodutibilidade | CP-O1, CP-O2, CP-O3, CP-O5, CP-R1, CP-R2, CP-R4 | repo "publishable", citável, com snapshots determinísticos |
| **S4 (2 semanas)** | Evaluation 2.0 e CI | CP-A7, CP-E3, CP-E4, CP-E5, CP-E6 | n ≥ 240 queries com clínico; CI verde em main |
| **S5 (background)** | Observability prod-grade | CP-M2, CP-M3, CP-M4 | dashboard live + alerting |
| **S6 (research)** | Modelos & otimizações | CP-A5, Eixo 8 | comparação Sonnet 4.6 vs GPT-4o-mini, fine-tune, cache Q→SQL |

---

## 10. Critérios de "pronto" (DoD por checkpoint)

Cada CP só é considerado completo quando:

- [ ] Código mergeado em `main` via PR pequeno (< 400 LoC excluindo testes)
- [ ] Teste de regressão (ou ablation snapshot) cobrindo o comportamento
- [ ] Documento atualizado: `README`, `CLAUDE.md`, ou ADR correspondente
- [ ] Resultado de eval rodada antes/depois anexada ao PR
- [ ] Sem regressão em EX overall (ou regressão justificada com tradeoff documentado)

---

## 11. Arquivos-chave para cada checkpoint (referência rápida)

- `src/agent/workflow.py` — adicionar feature flags (CP-A1)
- `src/agent/table_selection.py:_heuristic_table_selection` + `table_selector.py` — schema linker melhorado (CP-A2)
- `src/agent/sql_generation.py:_generate_sql_candidates` — seed determinístico (CP-R1)
- `src/agent/state.py:failure_taxonomy` — preencher consistentemente (CP-M5)
- `evaluation/dag/pipeline.py` + `tasks.py` — ablation matrix, métricas extras (CP-A1, CP-E1)
- `evaluation/metrics/improved_sql_parser.py` — promover para validation guardrail (Eixo 8)
- `src/utils/logging_config.py` — eventos JSON por estágio (CP-M1)
- `src/application/config/simple_config.py:OrchestratorConfig` — flags de ablation (CP-A1)
- `docs/adrs/` (criar) — ADR-001 a ADR-006 (CP-O3)
- `prompts/v1/` (criar) — extrair RULES A–O e templates (CP-V2)

---

## 12. Histórico de conclusões

> Atualizar aqui ao concluir cada checkpoint. Formato: `✅ CP-XX — <data> — PR#NNN — <frase curta do resultado>`

✅ CP-O5 — 2026-04-30 — CLAUDE.md versionado: removido do .gitignore, CLAUDE.local.md ignorado, conteúdo atualizado.
✅ CP-O2 — 2026-04-30 — God-files quebrados: orchestrator 917→550 LoC, state.py virou facade (67 LoC), sql_generation 689→186 LoC, workflow 707→449 LoC; 6 módulos extraídos; 53 testes passando.
✅ CP-O1 — 2026-04-30 — pyproject.toml + uv.lock: 126 pacotes resolvidos deterministicamente; .python-version=3.12; requirements.txt mantido como fallback; README atualizado.
✅ CP-V1 — 2026-04-30 — Conventional Commits: CONTRIBUTING.md, cliff.toml, .githooks/commit-msg (hook ativo via core.hooksPath), CHANGELOG.md gerado, tag v0.3.0 criada (EX=93.3%).
✅ CP-R1 — 2026-04-30 — seed=42 em self_consistency.py (SEED_CANDIDATES=42); self-consistency agora determinístico.
✅ CP-M5 — 2026-04-30 — failure_taxonomy.py com 11 categorias canônicas; add_error aceita taxonomy opcional com fallback via classify_sql_error; execution.py e table_selection.py instrumentados.
✅ CP-E3 — 2026-04-30 — evaluation/regression_set.json (40 queries: 10E/15M/15H, cobertura RULES A–O); evaluation/runners/run_regression.py com exit-code, relatório JSON e --tier/--max-queries.
✅ CP-E5 — 2026-04-30 — .github/workflows/ci.yml: lint (ruff) + unit tests em todo PR; regression job ativado por label 'eval' ou push em main com comentário automático de EX no PR.
✅ CP-V2 — 2026-04-30 — prompts/v1/rules.md com RULES A–O extraídas; prompt_version='v1' em ApplicationConfig e OrchestratorConfig; regression runner grava model_id + prompt_version + git_sha em cada relatório.
