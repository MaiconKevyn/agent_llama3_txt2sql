# Architecture Review and Improvement Plan

> Documento crítico-pragmático gerado em 2026-04-26 a partir de leitura direta do
> código (`src/agent/*`, `baselines/rich_prompt_baseline/*`, `evaluation/*`,
> `src/interfaces/*`, `src/application/config/*`) e dos artefatos de evaluation
> mais recentes (`dag_evaluation_20260306_070021.json`,
> `rich_prompt_baseline_20260306_070116.json`).
>
> Objetivo: avaliar se a arquitetura agentic atual ainda é a melhor escolha,
> dado que **o single-shot baseline atinge 90,0 % EX vs 93,3 % do agente
> LangGraph** — diferença não significativa (McNemar p = 0,289, m = 8 pares
> discordantes). Toda a sugestão aqui prioriza robustez, estabilidade de métricas
> e clareza arquitetural sobre adicionar complexidade.

---

## 1. Current Architecture Overview

### 1.1 Camadas físicas

```
txt2sql_refactor_openai_v2/
├── src/
│   ├── agent/                    # núcleo agentic — 22 módulos, ~7.122 LoC
│   │   ├── workflow.py           # 707 LoC — grafo LangGraph + 7 funções de roteamento
│   │   ├── orchestrator.py       # 917 LoC — wrapper de produção + sessão + métricas
│   │   ├── state.py              # 711 LoC — TypedDict + 7 dataclasses + helpers
│   │   ├── sql_generation.py     # 689 LoC — prompt + structured output + N candidatos
│   │   ├── table_selection.py    # 529 LoC — heurística regex + LLM selector
│   │   ├── classification.py     # 284 LoC — DATABASE/CONVERSATIONAL/SCHEMA
│   │   ├── plan_gate.py          # 165 LoC — 13 regex → 5 plan_types
│   │   ├── query_planner.py      # 270 LoC — LLM planner para multi-query
│   │   ├── multi_executor.py     # 401 LoC — exec + repair sub-queries
│   │   ├── multi_verifier.py     # 242 LoC — checks de shape/binding/leak
│   │   ├── result_synthesizer.py # 107 LoC — LLM final p/ multi
│   │   ├── execution.py          # 419 LoC — execute + repair LLM
│   │   ├── validation.py         # 248 LoC — DB validate + 7 regras semânticas
│   │   ├── vote_sql.py           # 155 LoC — self-consistency majority
│   │   ├── schema_node.py        # 301 LoC — list_tables + sus_mappings
│   │   ├── nodes.py              # 86 LoC — re-exports residuais
│   │   ├── nodes_misc.py         # 76 LoC — clarification + response
│   │   ├── llm_manager.py        # 293 LoC — ChatOpenAI + SQLDatabaseToolkit
│   │   └── tools/                # enhanced_list_tables_tool
│   ├── application/config/
│   │   ├── simple_config.py      # 67 LoC — ApplicationConfig + OrchestratorConfig
│   │   ├── table_descriptions.py # 467 LoC — metadata p/ API /schema
│   │   ├── table_templates.py    # 1.284 LoC — 13 prompts por tabela
│   │   └── table_templates_backup.py  # 1.094 LoC — duplicata legacy
│   ├── interfaces/
│   │   ├── api/main.py           # 233 LoC — FastAPI thin wrapper sobre orchestrator
│   │   └── cli/agent.py          # 722 LoC — CLI interativo
│   ├── infrastructure/database/  # connection_service
│   ├── memory/                   # artefatos de exemplo (não wired)
│   └── utils/                    # logging_config, sql_safety, classification
├── baselines/rich_prompt_baseline/  # 919 LoC — single-shot, mesmos prompts
│   ├── pipeline.py               # 262 LoC — loop → LLM → parse → exec → metrics
│   ├── prompt_builder.py         # 286 LoC — IMPORTA RULES e hints do agente
│   ├── llm_client.py             # 45 LoC — ChatOpenAI direto
│   ├── query_executor.py         # 100 LoC — psycopg2 / DuckDB
│   ├── sql_parser.py             # 43 LoC — extract_sql + safety
│   └── config.py / context_loader / run_batch
├── evaluation/
│   ├── dag/                      # NetworkX DAG c/ 9 tasks (load → eval → save)
│   ├── metrics/                  # EM, CM, EX, improved_sql_parser
│   ├── ground_truth.json + ground_truth_v2.json
│   ├── results/                  # JSONs e relatórios
│   └── run_dag_evaluation.py + run_rich_prompt_baseline.py
├── frontend/                     # Node/Express chat web
├── docs/CBMS/                    # paper LaTeX + figuras
└── tests/                        # 8 arquivos, ~600 LoC
```

### 1.2 Fluxo do agente (caminho DATABASE — 9 estágios)

`START → classify_query → list_tables → get_schema → plan_gate → query_planner? → reasoning? → generate_sql (+ N candidatos) → vote_sql → validate_sql → execute_sql → (repair_sql → loop) → generate_response → END`

Caminhos paralelos:

- **CONVERSATIONAL / SCHEMA / clarification:** desviam direto para `generate_response` ou `clarification`, sem SQL.
- **Multi-query:** `query_planner` → `multi_sql_executor` → `multi_verifier` → `result_synthesizer` → END (com fallback para single).

### 1.3 Fluxo do baseline (single-shot)

`build_prompts (RULES A–O + SUS_MAPPINGS + TODOS TABLE_TEMPLATES + dynamic hints) → ChatOpenAI.invoke → sql_parser.extract_sql → is_select_only → psycopg2.execute → metrics`

Cinco arquivos pequenos, zero estado, zero retry, zero LLM além da geração.

### 1.4 Fluxo da API (FastAPI)

`POST /query → _orchestrator.process_query (singleton no lifespan) → mesma stack do agente`.

A "API separada" mencionada no contexto **não é separada**: `src/interfaces/api/main.py:34` instancia `create_production_orchestrator()` e simplesmente expõe HTTP. A API e o CLI são clientes do mesmo agente. **A "API separada" do contexto é, na verdade, o `rich_prompt_baseline`**, que é um pipeline determinístico paralelo construído originalmente para isolar a contribuição da arquitetura LangGraph no paper CBMS.

### 1.5 Fluxo do evaluation

`run_dag_evaluation.py` cria `EvaluationDAG` (NetworkX) com 9 tasks: load_configuration, load_ground_truth, initialize_database, initialize_metrics, initialize_agent, evaluate_questions, aggregate_results, generate_report, save_results, cleanup_resources. As tasks `evaluate_questions` chama o orquestrador agente; `run_rich_prompt_baseline.py` chama o `rich_prompt_baseline.pipeline.run_batch` em paralelo arquitetural (mas escrito hoje sem reuso comum com o DAG agent).

---

## 2. Main Findings

### 2.1 Pontos fortes a preservar

- **Baseline controlado idêntico ao agente** (`baselines/rich_prompt_baseline/prompt_builder.py:244-245` importa `TABLE_TEMPLATES` e `_build_pregeneration_hints` direto do agente). Isso é metodologicamente forte e citado pelos três revisores.
- **Schema cache** estático em `src/agent/schema_node.py:23` — `_schema_cache: Dict[str, str]`. Evita ~1 round-trip LLM/DB por query.
- **Self-consistency com fingerprint do resultado** em `src/agent/vote_sql.py:13-22` — vota por igualdade de execução, não por igualdade de SQL. É uma boa idéia.
- **Static + DB validation com EXPLAIN + regras semânticas** em `src/agent/validation.py:check_semantic_rules` — 7 regras determinísticas (socioeconomico sem `metrica`, JOIN tempo cartesiano, NOT IN com NULL, etc.). Esses são guardrails de alto leverage.
- **Determinismo já endereçado** no `LLMManager`: `seed=42` configurado em `src/agent/llm_manager.py:78` — boa prática que não estava no `rich_prompt_baseline/llm_client.py`.

### 2.2 Fragilidades e duplicações

#### F1 — Caminho multi-query é dead code em prática
Em `evaluation/dag/dag_evaluation_20260306_070021.json` o relatório registra **`Multi Plans Triggered: 4` (em 120 queries) e `EX Evaluated via merged_rows: 0`**. Ou seja: 967 LoC (`plan_gate.py` 165 + `query_planner.py` 270 + `multi_executor.py` 401 + `multi_verifier.py` 242 + `result_synthesizer.py` 107) entregam **zero** EX adicional. Os 4 disparos terminaram em fallback ou foram descartados pelo verifier.

#### F2 — Vote-SQL nunca dispara override em prática
`src/agent/vote_sql.py:107` define `PRIMARY_OVERRIDE_MIN_SIZE = 3`, mas `N_SQL_CANDIDATES = 3` (`src/agent/sql_generation.py:43`). Para o vote sobrescrever o primary precisa de **3 candidatos com mesmo fingerprint** — só acontece se todos os 3 (incluindo o primário a `temperature=0`) coincidirem. Quando o primário está certo, override é desnecessário; quando o primário erra, é improvável que 3 candidatos a `temperature=0.1` produzam o mesmo resultado divergente. Logo: vote_sql custa ~3× tempo de geração + 3 round-trips ao DB e quase nunca corrige. Comportamento confirmado na prática (sem evidência de override em logs).

#### F3 — `plan_gate` trabalha hard mas nunca enxerga single_fallback
13 regex (`src/agent/plan_gate.py:25-64`) → 5 plan_types → roteamento. Porém, como o evaluation roda com `force_single_query=True` por default em `execute_sql_workflow` (`src/agent/workflow.py:558`), o gate vira **no-op de fato** durante toda a avaliação. O CLI/API rodam com `force_single_query=False` por default (`src/agent/orchestrator.py:245`), mas como F1 mostra que multi não ganha EX, o ramo todo é overhead.

#### F4 — Duplicação massiva de RULES e SUS_MAPPINGS
O texto das RULES A–O e os SUS_MAPPINGS aparecem em **três lugares**:
- `src/agent/sql_generation.py` (system prompt do agente).
- `src/agent/schema_node.py:_enhance_sus_schema_context` (linhas 150-213, chamada em `generate_sql_node`).
- `baselines/rich_prompt_baseline/prompt_builder.py:RULES_AO` (linhas 23-147) — comentário diz "mirrors src/agent/sql_generation.py".

A lógica reutilizada do agente (`_build_pregeneration_hints`, `TABLE_TEMPLATES`) é importada via cross-package import. Risco real: drift silencioso entre as cópias quando uma RULE é editada.

#### F5 — God-files e scope creep
| Arquivo | LoC | Responsabilidades misturadas |
|---|---|---|
| `orchestrator.py` | 917 | Workflow init + sessão CLI interativa + visualização Mermaid + logging + métricas + factory |
| `state.py` | 711 | TypedDict + 7 dataclasses + 12+ helper functions |
| `workflow.py` | 707 | Grafo + 7 funções de roteamento + execute_sql_workflow + stream_sql_workflow + complexity estimator |
| `sql_generation.py` | 689 | Prompt builder + structured schema + self-consistency + dynamic hints |
| `table_templates.py` | 1.284 | + arquivo `_backup.py` de 1.094 LoC commitado lado a lado |
| `cli/agent.py` | 722 | CLI |

#### F6 — `nodes.py` virtualmente vazio
86 LoC de re-exports. Vestígio de refactor anterior. `from .nodes import ...` ainda é usado em `orchestrator.py:101` (`set_global_llm_manager`).

#### F7 — `table_templates_backup.py` commitado
Arquivo "_backup.py" de 1.094 LoC versionado no repositório. É lixo de migração que nunca foi removido.

#### F8 — Evaluation assimétrico entre agente e baseline
| Métrica | Agent JSON | Baseline JSON |
|---|---|---|
| EX | ✅ 0.933 | ✅ 0.900 |
| CM | ❌ ausente (`null` nos breakdowns) | ✅ 0.710 |
| EM | ❌ ausente | ✅ 0.150 |

A `evaluation/dag/tasks.py:evaluate_questions` aparentemente não chama `ComponentMatchingMetric` e `ExactMatchMetric` para o agente, ou os resultados não são serializados no JSON final. **A comparação não é apples-to-apples**.

#### F9 — Recursion limit / loop tracking redundante
`workflow.py:553-606` calcula um `_estimate_query_complexity` heurístico para definir `recursion_limit ∈ {50,75,150,200}`. Em paralelo, `route_after_sql_generation` (`workflow.py:305`) já tem `total_workflow_cycles > 15 → error`. Dois sistemas de proteção, ambos arbitrários.

#### F10 — Multi-turn memory pouco usado
SQLite checkpointer em `data/chatbot_memory.db` (`orchestrator.py:111-114`) é instanciado para todos os ambientes; `session_id` vira `thread_id`. Mas o evaluation roda com session_id por questão (sem reuso) e a maioria das queries do GT é one-shot. Não há evidência de que a memória contribua para EX. Em contrapartida, abre risco de poluição entre sessões em prod.

### 2.3 Complexidade desnecessária identificada

| # | Componente | Impacto medido em EX | LoC | Veredicto |
|---|---|---|---|---|
| 1 | Multi-query (plan_gate + planner + executor + verifier + synthesizer) | 0 pp confirmado | 1.185 | **dead code** |
| 2 | Vote-SQL (com `MIN_SIZE=3, N=3`) | indeterminado, provavelmente 0 pp | 155 | **near-dead code** |
| 3 | `_estimate_query_complexity` (regex em PT) | 0 (limita recursion artificialmente) | ~60 | over-engineering |
| 4 | `table_templates_backup.py` | 0 | 1.094 | **lixo** |
| 5 | `nodes.py` re-exports | 0 | 86 | resíduo de refactor |
| 6 | Estimador de complexity em workflow + 13 regex em plan_gate | redundantes | ~210 | over-engineering |
| 7 | Memory checkpointer SQLite + thread_id | indeterminado | ~10 (mas state grande) | feature ativa que não atende caso de uso atual |

**Total de LoC com baixo ou nenhum valor mensurável: ~2.800 (≈ 39 % do `src/agent/`).**

---

## 3. Agentic AI / LangGraph Assessment

### 3.1 Onde o LangGraph realmente agrega valor

Cruzando o gráfico com os dados:

| Estágio | Agrega valor? | Evidência |
|---|---|---|
| `classify_query` | ✅ Sim, mas marginal | Filtra CONVERSATIONAL/SCHEMA — útil em prod, pouco usado no eval (todos GT são DATABASE) |
| `list_tables` + `get_schema` | ✅ Sim | Schema cache + selected_tables reduzem tokens; EnhancedListTablesTool dá metadata |
| `generate_sql` (com structured output Pydantic) | ✅ Sim | `SQLOutput` elimina parse de markdown — single-shot baseline ainda parseia regex |
| `validate_sql` (DB EXPLAIN + regras semânticas) | ✅ **Forte** | 7 regras semânticas pegam erros que o LLM repete (RULE J, RULE D, NOT IN). Esse é o estágio com **maior leverage por linha** |
| `execute_sql` + `repair_sql` | ⚠️ Parcial | Repair com whitelist de colunas e schema refresh é correto, mas evidência de eval mostra que o ganho é pequeno |
| `vote_sql` | ❌ Não (na config atual) | F2 — threshold inalcançável |
| `plan_gate` + `query_planner` + multi-* | ❌ Não | F1 — 0 pp em 120 queries |
| `reasoning` (CoT) | ⚠️ Indeterminado | Aplicado a 5 plan_types complexos; sem ablation, hipótese de R1/R3 |
| `generate_response` | ✅ Sim | Necessário — formata em PT |

### 3.2 O LangGraph é necessário?

**Resposta direta: não no formato atual.**

Os componentes que de fato agregam valor — schema cache, structured output, semantic validation, bounded repair — **não exigem LangGraph**. Eles são funções determinísticas que poderiam ser organizadas como pipeline linear (com retry decorator no repair) sem perder nada mensurável.

LangGraph **só justificaria sua complexidade** quando há de fato:

1. Branching dinâmico baseado em estado intermediário com mais de 2 caminhos plausíveis em produção.
2. Ciclos de retry que precisam de estado persistente entre tentativas.
3. Multi-turn com memória que **comprovadamente** muda EX.
4. Composição de sub-agents independentes (multi-supervisor pattern).

Hoje o projeto tem (1) com 2 caminhos reais (database vs conversational), (2) com retry simples e (3) ativada mas sem evidência de ganho. **(4) não existe**.

### 3.3 O que o LangGraph adiciona em complexidade

- **State explícito (`MessagesStateTXT2SQL`, 711 LoC):** 60+ chaves de estado, 7 dataclasses, ~12 helpers. Cada nó precisa ler/escrever campos certos sem contrato — qualquer adição/renomeação obriga editar grafo, nodes, helpers e testes.
- **Routing functions:** 7 funções `route_after_*` com regras imperativas (string matching de error_message para decidir retry path em `route_after_sql_execution:430-453`). Difícil de testar e razoavelmente fácil de quebrar.
- **`add_messages` accumulator:** o estado guarda histórico longo de mensagens AI/Human/Tool, inflando tokens em queries com retry (cada repair vê mais histórico).
- **Loop guards duplos:** `total_workflow_cycles`, `generation_retry_count`, `validation_retry_count`, `execution_retry_count`, `recursion_limit` — coerção redundante.

### 3.4 Veredicto

O LangGraph é hoje **uma máquina de estado pesada para um workflow que, de fato, é um pipeline com 1–2 retry branches**. O ganho de +3,3 pp não significativo (`p=0.289, m=8`) **não compensa** a superfície de manutenção de ~7.000 LoC do `src/agent/`.

---

## 4. API vs Agent Comparison

> **Nota crítica de terminologia:** a "API separada" do contexto é o
> `baselines/rich_prompt_baseline/`. A `src/interfaces/api/main.py` (FastAPI) é
> apenas um wrapper HTTP do mesmo `LangGraphOrchestrator`. Toda a comparação
> abaixo é **agente vs single-shot baseline**.

### 4.1 Resultado factual da última run (2026-03-06)

| Métrica | Agente LangGraph | Baseline single-shot | Δ |
|---|---|---|---|
| EX overall | **93.3 %** (112/120) | 90.0 % (108/120) | +3.3 pp |
| EX Easy | 100.0 % (40/40) | 97.5 % (39/40) | +2.5 pp |
| EX Medium | 97.5 % (39/40) | **100.0 % (40/40)** | **−2.5 pp** |
| EX Hard | 82.5 % (33/40) | 72.5 % (29/40) | +10.0 pp |
| Pipeline completion | 98.3 % (multi fallouts) | 100 % | −1.7 pp |
| Avg latency | 14.76 s/q | 14.03 s/q | +0.73 s |
| Significância (McNemar) | b=6, c=2, m=8, **p=0.289** | — | inconclusivo |

### 4.2 O que o agente realmente adiciona (sobre o baseline)

1. **Hard tier +10 pp** — único ganho real e direcional. A hipótese (paper) é que table-selection + CoT planning ajudam em queries com JOIN/PARTITION.
2. **Roteamento conversacional/schema** — baseline não faz; agente desvia direto para resposta sem chamar SQL.
3. **Multi-turn memory** (potencial; não medido).
4. **Auditabilidade** (cada nó produz uma `ToolCallResult` rastreável) — qualidade não-funcional importante para healthcare.

### 4.3 Onde o agente piora resultado

1. **Medium tier −2.5 pp** — table-selection LLM erra em casos onde o baseline simplesmente lê o schema completo e acerta. Confirmado nos `c=2` (`primaryICD` em vez de `deathICD`).
2. **Pipeline failure rate 1.7 %** vs 0 % do baseline — multi-query path produz fallouts.
3. **Custo de tokens maior** (não mensurado, mas inerente: classify + table_select + 3 candidates + validate + 1+ repair).

### 4.4 Onde se sobrepõem (duplicação)

| Lógica | Agente | Baseline |
|---|---|---|
| RULES A–O | `sql_generation.py` system prompt | `prompt_builder.py:RULES_AO` |
| SUS_MAPPINGS | `schema_node.py:_enhance_sus_schema_context` | `prompt_builder.py:SUS_MAPPINGS` |
| TABLE_TEMPLATES | `application/config/table_templates.py` | importado direto pelo baseline |
| Dynamic hints | `sql_generation.py:_build_pregeneration_hints` | importado direto pelo baseline |
| SQL parsing/safety | `utils/sql_safety.py` | `baselines/rich_prompt_baseline/sql_parser.py` (wrapper) |
| Connection executor | `llm_manager.py` (via SQLDatabaseToolkit) | `baselines/rich_prompt_baseline/query_executor.py` (psycopg2 direto) |
| EM/CM/EX metrics | mesma lib `evaluation/metrics/` | mesma lib |

A sobreposição é tão grande que o baseline literalmente importa do agente. **Existe um "core engine" implícito embutido em `src/agent/` que ambos consomem, mas que nunca foi extraído**.

### 4.5 Sugestão: manter ambos, mas reorganizar

- **NÃO remover o baseline.** Ele é o controle experimental do paper e do eval. Removê-lo destrói a comparação metodológica.
- **NÃO manter a estrutura dual de hoje.** A duplicação textual de RULES/MAPPINGS é frágil.
- **Extrair um `core_engine/`** com prompt builder, schema enhancer, validators, parser, executor. Tanto agent quanto baseline consomem — ambos tornam-se "modos de execução" do mesmo motor.
- **Promover a API a cliente do core_engine**, não do agente — assim a API pode rodar em "modo single-shot" ou "modo orchestrated" via flag.

---

## 5. LLM Engineering Improvements

### 5.1 Prompts

**Problema 1 — RULES A-O em texto plano gigante.** ~7 KB inline no system prompt. Difícil testar regra por regra.
- **Recomendação:** transformar cada RULE em arquivo `prompts/rules/A_uti.md`, `B_death_cause.md`, ... Carregar com hash → versionar → permitir rule-level ablation. Cada rule também ganha 1–2 unit tests (input → SQL esperada).

**Problema 2 — RULES e SUS_MAPPINGS duplicadas (F4).**
- **Recomendação:** mover para `core_engine/prompts/` e fazer agente + baseline importarem o mesmo arquivo.

**Problema 3 — `_build_pregeneration_hints` é regex sobre PT.**
- **Recomendação:** manter — é prático e barato. Mas adicionar feature flag para desligar em ablation (CP-A4 do ROADMAP).

**Problema 4 — `_enhance_sus_schema_context` é chamado em `generate_sql_node` mas seu conteúdo já está dentro de RULES em outro lugar.**
- **Recomendação:** unificar. Há overlap textual entre os dois blocos.

### 5.2 Structured outputs

`SQLOutput` (`src/agent/sql_generation.py:32`) é um bom Pydantic schema. Pontos de melhoria:

- **Adicionar `tables_used: list[str]`** — permite verificação automática "todas as tabelas selecionadas foram realmente usadas?"
- **Adicionar `requires_window: bool`** + `requires_partition_by: bool` — o LLM declara intent; depois o validator confere SQL → reduz erros de RULE J.
- **Promover `confidence` para gate de execução**: queries com `confidence < 0.4` poderiam acionar reflection ou pedir clarificação ao usuário.
- **No baseline**, o output **não** usa structured output (é regex sobre markdown — `sql_parser.py:21-37`). Pequeno upgrade: usar `with_structured_output(SQLOutput)` no baseline também eliminaria o parser ad-hoc.

### 5.3 Validações e retries

**Forte.** As 7 regras em `validation.py:check_semantic_rules` são o componente de **maior alavancagem** da arquitetura atual e custam quase nada (puro regex).

**Sugestões:**

- **Promover o `improved_sql_parser.py` (`evaluation/metrics/`) para guardrail pré-execução** — ele já parseia componentes (SELECT/FROM/WHERE/JOIN/GROUP/ORDER/LIMIT). Use-o para detectar:
  - LIMIT sem ORDER BY (não-determinístico).
  - JOIN sem ON.
  - COUNT(DISTINCT col1, col2) (ilegal em DuckDB).
  - Subquery sem alias.
- **Adicionar dry-run via `EXPLAIN (FORMAT JSON)` antes de `EXECUTE`** — captura erros de tipo sem rodar o plano.
- **Limitar repair budget mais cedo** — hoje são 2 generation retries + 3 validation retries + 15 cycles. Em prática, se `repair_sql` produz a mesma SQL 2× seguidas (loop_detection já existe em `execution.py:351-369`), abortar imediatamente.

### 5.4 Schema selection

**O ponto fraco mais evidente do agente** (gargalo dominante per paper).

- **Manter o cascata regex → embedding → LLM**, mas encurtar quando confiança alta (já feito).
- **Adicionar verifier passada por LLM-as-judge** depois da seleção: "given user_query e candidate tables, há conflito semântico (ex.: morte/óbito + primaryICD)?"
- **Treinar classificador denso supervisionado** — com 120 queries do GT já dá pra fitar um logreg sobre embeddings + features (regex matches). Custa quase nada e dá upper-bound mensurável.

### 5.5 Logging, tracing, debugabilidade

Ver detalhes em `ROADMAP.md` § Eixo 5. Resumo:

- Adotar evento JSON por estágio (já discutido).
- LangSmith on-by-default em dev (hoje opcional).
- Persistir `failure_taxonomy` consistentemente (`state.py` já tem o campo, mas só preenche em alguns paths).

---

## 6. AI Engineering and Evaluation Improvements

### 6.1 Como o projeto mede qualidade hoje

- **EX, CM, EM** implementadas em `evaluation/metrics/`.
- **DAG NetworkX** para orquestrar tasks (load → init → eval → aggregate → report → save). Boa engenharia.
- **Two runners independentes** (`run_dag_evaluation.py` para agente, `run_rich_prompt_baseline.py` para baseline). Não compartilham métrica/relato.
- **EX-zero export** automático (`run_dag_evaluation.py:36-102`) — bom para triagem.
- **Sem CI, sem regression suite, sem dashboard.**

### 6.2 Métricas mais estáveis e úteis a adicionar

| Métrica | Por quê | Custo |
|---|---|---|
| `valid_sql_rate` | passa em validate_sql | trivial |
| `first_pass_success` | acertou sem retry | trivial |
| `repair_rescued_rate` | errou e foi salvo pelo repair | trivial |
| `multi_query_triggered_rate` | quantas vezes multi disparou e venceu | trivial — já parcial |
| `tokens_per_correct_query` | overhead pedido pelo R2 | requer instrumentação |
| `p50/p95 latency por estágio` | gargalo de prod | requer instrumentação |
| `result_set_containment` | resposta correta pode conter linhas extras (precisão vs recall) | médio |
| `clinical_safety_flag` | LLM-as-judge sobre answer textual | médio |

### 6.3 Comparação semântica e containment

**EX hoje é exact-match-of-multiset** (cf. `vote_sql.py:13-22` e `evaluation/metrics/execution_accuracy.py`). Para SQL com `LIMIT N` e queries underspecified, isso é frágil.

- Adicionar métrica **`row_containment`** = |GT ∩ Predicted| / |GT|. Captura "predicted é superset de GT".
- Adicionar **`column_alignment_score`** — match por coluna usando heurística de tipo + nome.

### 6.4 Reprodutibilidade

Ver `ROADMAP.md` § Eixo 4. Pontos críticos para o ARCH:
- `LLMManager` já usa `seed=42`. Baseline `llm_client.py` **não passa seed** — assimetria.
- DB snapshot ainda inexistente.
- `model_id`/`system_fingerprint` da OpenAI não capturados em nenhum lado.

### 6.5 Organização de resultados/auditoria/versões

Hoje:
- `evaluation/dag/dag_evaluation_*.json` (raw + report)
- `evaluation/results/dag_evaluation_*.json` (cópia? talvez mais "oficial")
- `baselines/rich_prompt_baseline/artifacts/rich_prompt_baseline_*.json`

→ Três pastas para resultados; nomes sobrepostos (idênticos arquivos em duas pastas confirmados via `ls`).

**Recomendação:**

```
evaluation/
├── benchmarks/                       # GT versionado
├── runners/                          # ambos runners
├── results/<git_sha>_<ts>/
│   ├── agent.json
│   ├── baseline.json
│   ├── report.md
│   └── env.json                      # model_id, seed, prompt_version, db_snapshot_sha
└── metrics/
```

Cada run gera 1 pasta com sha+timestamp; relatórios são gerados a partir desse pacote.

### 6.6 Tracking de experimentos

Para 120 queries × N variantes (quando ablation entrar), começar **sem ferramenta pesada**:
- JSON estruturado por run em `evaluation/results/<sha>_<ts>/`.
- `evaluation/results/index.csv` agregando: sha, ts, variant, EX_overall, EX_easy, EX_medium, EX_hard, prompt_version, model.
- **Só** se isso virar bottleneck (≥ 50 runs/semana) avaliar W&B / MLflow.

---

## 7. Recommended Architecture Options

### 7.1 Opção A — **Conservadora**: simplificar dentro do LangGraph

**O que muda**
- Remover caminho multi-query (`plan_gate`, `query_planner`, `multi_executor`, `multi_verifier`, `result_synthesizer`) — é dead code (F1).
- Remover `vote_sql` ou ajustar `MIN_SIZE=2, N=3` (vote vira útil).
- Remover `_estimate_query_complexity` e adaptive recursion — usar limite fixo.
- Apagar `nodes.py` residual (re-exports inúteis) e `table_templates_backup.py`.
- Quebrar god-files (orchestrator, state, sql_generation, workflow) conforme `ROADMAP.md` § CP-O2.
- Extrair RULES/SUS_MAPPINGS para `prompts/v1/` consumidos por agente + baseline.

**Vantagens**
- Mantém auditabilidade do LangGraph.
- ~2.800 LoC eliminados (~39 % do `src/agent/`).
- Reduz superfície de bug significativamente.
- Não exige migração de produção.

**Riscos**
- LangGraph ainda traz peso de state/routing para benefício limitado.
- Se algum dia multi-query realmente ajudar, terá que ser reimplementado.

**Impacto esperado em métricas**
- EX: 0 pp (componentes removidos não contribuem).
- Latência: −10 a −15 % (vote_sql custava 3 round-trips).
- Tokens: −10 a −20 % (sem candidatos extras).
- Stability: ↑ significativa (menos paths, menos branches).

**Esforço:** ~1–2 semanas.

### 7.2 Opção B — **Intermediária**: Pipeline determinístico + `core_engine` compartilhado

**O que muda**
- Criar `src/core_engine/` com:
  - `prompts/` (RULES, SUS_MAPPINGS, table templates).
  - `schema/` (cache, enhance, list_tables).
  - `generation.py` (single LLM call com structured output).
  - `validation.py` (semantic rules + DB EXPLAIN).
  - `execution.py` (psycopg2/DuckDB executor).
  - `repair.py` (1–2 retry com whitelist).
- `src/agent_modes/` com **dois modos**:
  - `single_shot.py` — invoca core_engine direto (substitui rich_prompt_baseline).
  - `orchestrated.py` — pipeline `classify → table_select → schema → generate → validate → execute (→ repair)` — Python puro com `try/except + retry decorator`, sem LangGraph.
- `src/interfaces/api/main.py` recebe parâmetro `mode=single|orchestrated` no body.
- `evaluation/runners/` consome ambos com mesma interface — relatório unificado.
- LangGraph **removido**.

**Vantagens**
- Elimina F4, F5, F6, F7 e a maior parte de F1, F2, F3.
- Código de produção volta a ser ~2.000–2.500 LoC totais.
- Single-shot e orchestrated rodam o mesmo prompt builder e o mesmo validator → comparação trivial.
- LangGraph some como dependência → menos surface area de versão (langgraph 0.6.6, langgraph-checkpoint-sqlite 3.0.3 saem do `requirements.txt`).
- Auditabilidade preservada via logs estruturados por estágio.

**Riscos**
- Perde checkpointer multi-turn (mas evidência de uso é nula no eval).
- Se requerer multi-agent supervisor no futuro, terá que ressuscitar LangGraph.
- Mudança maior — um esforço de migração não trivial.

**Impacto esperado em métricas**
- EX: 0 a +1 pp (paths simplificados podem reduzir bugs sutis de state).
- Latência: −15 a −25 %.
- Tokens: −20 %.
- Mantenabilidade: ↑↑↑.
- Tempo de execução de eval: −10 a −15 %.

**Esforço:** ~3–4 semanas.

### 7.3 Opção C — **Radical**: Prompt-first, LangGraph fora, single-shot como default

**O que muda**
- Adotar **single-shot baseline como agente principal de produção**. Resultados mostram que ele é estatisticamente equivalente em EX (90 vs 93.3 %, p=0.289) e estritamente melhor em Medium e em pipeline completion.
- Manter `core_engine/` (Opção B) mas só com prompts + structured output + validate + execute + repair.
- Adicionar **uma única feature opcional ativável por header da API**: `enable_table_selection_pre_pass` (1 LLM call extra antes da geração) — para queries Hard onde o ganho de +10 pp justifica o overhead.
- Remover totalmente o LangGraph, multi-turn checkpointer, vote_sql, multi-query, plan_gate.
- Frontend e CLI passam a chamar a API.

**Vantagens**
- Repositório fica enxuto: `core_engine/ + interfaces/ + evaluation/ + frontend/`.
- Zero dependência de framework agentic — só `langchain-openai` para o cliente OpenAI.
- Latência potencial: 1 LLM call (~7s) em vez de 2-4 (~14s) para Easy/Medium.
- Cost-benefit honesto para deploy clínico (resposta esperada ao Reviewer 2).

**Riscos**
- Hard tier pode cair se table-selection pre-pass não for habilitado por default.
- Perde-se completamente a narrativa "agentic" do paper. **Mas** a evidência empírica suporta isso.
- Ablation pendente: se CP-A1 mostrar que table-selection ou CoT realmente contribuem, essa opção volta a fazer sentido apenas com eles.

**Impacto esperado em métricas**
- EX: −2 a +1 pp (intervalo dentro do ruído).
- EX Medium: provavelmente +2 pp (vira igual ao baseline).
- EX Hard: −5 a 0 pp se desligar table-selection; +5 a +10 pp se ligar.
- Latência: −40 a −50 % na config default.
- Tokens: −50 % na config default.

**Esforço:** ~2 semanas (a maior parte é deletar código).

---

## 8. Recommended Path

### 8.1 Decisão: **Opção B (Intermediária)** + ablation antes de decidir entre B e C.

### 8.2 Justificativa

1. **Os dados ainda não suportam Opção C com confiança.** O paper deixa explícito: "p=0.289 não justifica claim de superioridade, **mas tampouco evidencia ausência de efeito moderado em Hard**". Migrar para single-shot puro sem ablation pode regredir Hard. Antes de cortar, **mensure**.
2. **Opção A é insuficiente.** Resolve duplicação e dead code, mas mantém o peso conceitual do LangGraph para um workflow que é de fato linear. Não responde à crítica central da pergunta.
3. **Opção B é o pivot certo.** Extrai o `core_engine/`, elimina duplicação textual, mantém compatibilidade, abre porta para Opção C de forma incremental. Cada modo (single_shot vs orchestrated) é trivialmente comparável porque ambos consomem o mesmo motor.
4. Após a migração para B, executar a ablation matrix do `ROADMAP.md` § CP-A1. Se ablation mostrar que **table-selection + CoT são os únicos componentes que entregam EX**, migrar para Opção C com `enable_table_selection_pre_pass=true` por default e tudo o mais removido.

### 8.3 Sequência recomendada

1. **Fase 1 (Opção B core)** — extrair `core_engine/`, criar dois modos, remover LangGraph.
2. **Fase 2 (Ablation)** — rodar matrix completa do CP-A1 sobre o orchestrated mode com flags.
3. **Fase 3 (decisão)** — se Hard tier cair < 80 % com table-selection desligado → manter B; se Hard tier ficar estável sem table-selection → migrar para C.

---

## 9. Implementation Checkpoints

### P0 — essenciais (bloqueiam clareza arquitetural)

- [ ] Apagar `src/application/config/table_templates_backup.py` (1.094 LoC zumbi)
- [ ] Apagar `src/agent/nodes.py` se nada importar `set_global_llm_manager` por outro caminho; senão mover para `src/agent/llm_manager.py`
- [ ] Remover `src/agent/result_synthesizer.py`, `multi_executor.py`, `multi_verifier.py`, `query_planner.py`, `plan_gate.py` e seus edges no `workflow.py` e seu campo no `state.py` — caminho multi é dead code (F1) (~1.185 LoC)
- [ ] Remover `vote_sql_node` do grafo ou reduzir `PRIMARY_OVERRIDE_MIN_SIZE` para 2 (manter como guardrail útil) (F2)
- [ ] Substituir `_estimate_query_complexity` + `recursion_limit` adaptativo por limite fixo `recursion_limit=50` (F9)
- [ ] Extrair `RULES_AO`, `SUS_MAPPINGS`, `_build_pregeneration_hints` para `src/core_engine/prompts/` e atualizar agente + baseline para importarem do mesmo lugar (resolve F4)
- [ ] Migrar `evaluation/dag/tasks.py:evaluate_questions` para chamar **CM, EM e EX** para o agente (resolve F8 — eval atualmente assimétrico)
- [ ] Padronizar `evaluation/results/` como única pasta de saída; remover duplicatas em `evaluation/dag/*.json`
- [ ] Adicionar `seed=42` em `baselines/rich_prompt_baseline/llm_client.py:23` (paridade com agente)

### P1 — importantes (rumo Opção B)

- [ ] Criar `src/core_engine/` com módulos: `prompts/`, `schema/`, `generation.py`, `validation.py`, `execution.py`, `repair.py`. Migrar lógica respectiva sem mudar comportamento
- [ ] Criar `src/modes/single_shot.py` e `src/modes/orchestrated.py` que consomem `core_engine/`
- [ ] Aposentar `baselines/rich_prompt_baseline/` movendo seu pipeline para `src/modes/single_shot.py` (preservar artefatos históricos em `evaluation/archive/baseline_legacy/`)
- [ ] Refatorar `src/interfaces/api/main.py` para aceitar parâmetro `mode: 'single' | 'orchestrated'` e rotear
- [ ] Quebrar `orchestrator.py` em `LangGraphOrchestrator` (núcleo) + `MetricsCollector` + `LoggingSetup` + `WorkflowVisualizer` + `InteractiveCLISession`
- [ ] Quebrar `state.py` em `state_models.py` (TypedDict + dataclasses) + `state_helpers.py`
- [ ] Promover `evaluation/metrics/improved_sql_parser.py` a guardrail pré-execução em `core_engine/validation.py`
- [ ] Implementar logs JSON por estágio em `core_engine/` com schema `{query_id, stage, latency_ms, tokens, cost, status, error_kind}`
- [ ] Implementar campo `tables_used: list[str]` e `requires_window: bool` em `SQLOutput` para reduzir erros de RULE J
- [ ] Adicionar métricas extras no relatório: `valid_sql_rate`, `first_pass_success`, `repair_rescued_rate`, `tokens_per_correct_query`, `p95_latency`
- [ ] Substituir LangGraph orchestrator por pipeline Python puro (`functools.reduce` ou cadeia explícita) em `src/modes/orchestrated.py`. Remover dependências `langgraph` e `langgraph-checkpoint-sqlite` se nada mais usa
- [ ] Persistir `failure_taxonomy` consistentemente em todo path de erro

### P2 — futuras (após decidir entre B e C)

- [ ] Rodar ablation matrix do `ROADMAP.md` CP-A1 sobre `orchestrated` mode
- [ ] Decisão B vs C com base em ablation; se C, deletar `src/modes/orchestrated.py` e degradar a feature pre-pass de table-selection
- [ ] Treinar classificador denso supervisionado para schema linking (logreg sobre embeddings) e comparar com cascata atual
- [ ] Implementar `result_set_containment` e `column_alignment_score` em `evaluation/metrics/`
- [ ] Adicionar LLM-as-judge calibrado para `answer_relevance` e `clinical_safety_flag`
- [ ] Snapshot de DB reproduzível + `db_snapshot_sha256` em cada run JSON
- [ ] Versionar prompts em `prompts/v1/` com hash gravado em cada run (`prompt_version`, `git_sha`)
- [ ] Pasta `evaluation/results/<git_sha>_<ts>/` com `agent.json + baseline.json + report.md + env.json`; índice CSV agregando todas as runs
- [ ] CI: lint (ruff) + typecheck (mypy strict) + regression set 40 queries (≤ 5 min) em todo PR
- [ ] Mutation testing nos módulos críticos: `core_engine/validation.py`, `core_engine/repair.py`, `evaluation/metrics/execution_accuracy.py`
- [ ] Avaliar Claude Sonnet 4.6 como modelo alternativo via `core_engine/llm.py` adapter
- [ ] Audit-trail signing (SHA-256 chained log) para deploy clínico
- [ ] Frontend chama API em modo `single` por default e oferece toggle "modo cuidadoso (orchestrated)" para queries Hard

---

## 10. Final Recommendation

### O que MANTER

- **`src/core_engine/` recém-extraído** — RULES A–O, SUS_MAPPINGS, schema enhancement, `_build_pregeneration_hints`, structured output `SQLOutput`, validators semânticos. **Esse é o ativo intelectual real do projeto.**
- **`evaluation/dag/` + `evaluation/metrics/`** — boa engenharia, vale evoluir.
- **`rich_prompt_baseline` como controle metodológico** — mas reposicionado como `src/modes/single_shot.py`, consumindo o core_engine.
- **`improved_sql_parser.py`** — promover a guardrail.
- **Schema cache + enhanced list_tables tool**.
- **Multi-turn memory via SQLite checkpointer** — só se houver caso de uso claro em produção; senão, remover.

### O que SIMPLIFICAR

- **State e workflow:** trocar `MessagesStateTXT2SQL` (711 LoC) por dataclasses pequenos por estágio. Um `RunContext` pequeno carrega `query`, `selected_tables`, `schema`, `sql`, `errors[]` — o resto sai.
- **Repair loop:** colapsar `repair_sql_node` + lógica de loop_detection + recursion_limit em uma função `repair(query, sql, error) -> sql | RepairFailure` com retry budget claro (`max_attempts=2`) e early exit em SQL repetida.
- **Prompts:** modularizar RULES em arquivos individuais; carregar com hash; testar isoladamente.
- **Logging/observability:** evento JSON único por estágio em vez do mix atual de `add_ai_message`/`add_tool_call_result`/`logger.info`.

### O que REMOVER

| Item | LoC | Por quê |
|---|---|---|
| Multi-query path inteiro (`plan_gate`, `query_planner`, `multi_executor`, `multi_verifier`, `result_synthesizer`) | ~1.185 | 0 pp medido em 120 queries (F1) |
| `_estimate_query_complexity` + adaptive recursion limit | ~60 | Redundante com `total_workflow_cycles` (F9) |
| `vote_sql_node` na config atual (ou ajustar threshold) | 155 | `MIN_SIZE=3, N=3` torna override quase impossível (F2) |
| `nodes.py` (re-exports vazios) | 86 | Resíduo de refactor (F6) |
| `table_templates_backup.py` | 1.094 | Lixo commitado (F7) |
| Possivelmente o LangGraph inteiro | ~700 (workflow.py) + state | Sob avaliação na ablation (decisão B vs C) |

### O que REESTRUTURAR

- Pasta `src/agent/` deixa de existir como tal — vira `src/core_engine/` + `src/modes/`.
- Pasta `baselines/` é absorvida em `src/modes/single_shot.py`. Histórico vai para `evaluation/archive/`.
- Pasta `evaluation/results/` torna-se canônica; dados duplicados em `evaluation/dag/` removidos.
- Pasta `src/interfaces/` mantém estrutura, mas API e CLI passam a aceitar `mode={single, orchestrated}` em vez de só "agent".

### Resumo executivo (1 frase)

> **A diferença real entre o agente LangGraph e a "API separada" é menor que
> o erro estatístico do benchmark; a maior parte do valor está em prompts,
> validators semânticos e structured output — não no orquestrador. Extraia
> esse núcleo para um `core_engine/`, transforme o agente e o baseline em
> dois modos consumidores do mesmo motor, e decida sobre LangGraph depois
> da ablation por estágio.**

---

## Apêndice A — Incertezas e questões em aberto

- **Multi-turn memory**: o checkpointer SQLite é provisionado mas o evaluation usa session_id por query. Não há evidência de que ele agregue EX. Para confirmar, seria necessário um benchmark conversacional (multi-turn) — não existe hoje.
- **`reasoning` (CoT) node**: o paper atribui parte do ganho Hard a ele, mas sem ablation isolada. Pode ser o estágio de maior leverage no Hard tier — ou pode ser ruído. Manter até a ablation rodar.
- **Score do baseline em runs anteriores**: o eval mais recente foi 90 %; runs anteriores do baseline (`rich_prompt_baseline_20260301_*` etc.) podem mostrar variação. Análise de variância entre runs com mesmo prompt mostraria se o ruído inerente do LLM já é maior que o gap de +3,3 pp.
- **Evaluator do agente não computou CM/EM** no run mais recente, apenas EX. Não está claro se é bug ou design — deve ser conferido em `evaluation/dag/tasks.py:evaluate_questions`.
- **`force_single_query=True`** está ativo por default em `execute_sql_workflow` (`workflow.py:558`) mas não em `process_query` (`orchestrator.py:245`). O eval roda com `force_single_query=False` (orchestrator path). Isso cria dois sub-comportamentos do agente (CLI/API vs eval) com configurações diferentes — vale checar se o eval está realmente medindo o caminho que produção usa.
