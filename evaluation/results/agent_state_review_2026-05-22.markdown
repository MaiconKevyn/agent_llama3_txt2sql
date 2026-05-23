# Avaliação do estado atual do agente TXT2SQL

Data da avaliação: 2026-05-22T17:24:21-03:00
Repositório: `/home/maiconkevyn/PycharmProjects/txt2sql_refactor_openai_v2`
Branch: `llamaindex_dev`
Último commit: `ba8faf5 fix(cid): preserve cid catalog and hierarchy semantics`

## 1. Sumário executivo

O agente está em um estágio avançado de maturidade arquitetural para pesquisa e prototipação de AI Engineering: possui LangGraph explícito, contratos Pydantic, camada semântica rica, LlamaIndex para contexto de schema, validação SQL/semântica, reparo, rotas de visualização e uma suíte de testes ampla.

Ao mesmo tempo, o estado atual da branch não está saudável para merge/produção: há mudanças não commitadas, testes falhando, lint falhando no escopo usado pelo CI, e regressões semânticas concentradas em CID/diagnóstico. O projeto evoluiu bastante desde o roadmap inicial, mas também acumulou novamente god-files grandes, especialmente em `src/agent/sql_generation.py`, `src/agent/execution.py` e `src/semantic/planner.py`.

Veredito: bom arcabouço de agente para pesquisa aplicada; não pronto para merge sem correções. A prioridade imediata deve ser estabilizar CI/testes e reduzir regressões semânticas antes de adicionar novas features.

## 2. Evidências coletadas

### Git

`git status --short` mostra 10 arquivos modificados:

- `frontend/public/app.js`
- `frontend/server.js`
- `frontend/tests/format-message-content.test.js`
- `src/agent/orchestrator.py`
- `src/interfaces/api/main.py`
- `src/visualization/planner.py`
- `tests/test_api_chart_contract.py`
- `tests/test_frontend_chart_layout.py`
- `tests/test_visualization_orchestrator.py`
- `tests/test_visualization_planner.py`

Resumo do diff atual:

- 10 arquivos alterados
- 433 inserções
- 39 deleções

O diff adiciona principalmente suporte de visualização follow-up via `chart_from_last_result`, cache de `user_query` no último resultado de sessão e escolha mais semântica da métrica em gráficos.

### Tamanho aproximado do código

Contagem direta de linhas em arquivos relevantes:

- `src`: 94 arquivos, 32.806 linhas
- `tests`: 70 arquivos, 13.554 linhas
- `evaluation`: 38 arquivos, 13.203 linhas
- `frontend`: 361 arquivos, 58.497 linhas observadas pela contagem simples

Arquivos grandes principais:

- `src/semantic/planner.py`: 3.911 linhas
- `src/agent/sql_generation.py`: 2.737 linhas
- `src/agent/execution.py`: 2.688 linhas
- `src/semantic/validators.py`: 1.537 linhas
- `src/agent/orchestrator.py`: 837 linhas
- `src/agent/prompt_builder.py`: 843 linhas
- `src/agent/response.py`: 776 linhas
- `src/agent/analytic_sql.py`: 676 linhas
- `src/visualization/chart_plan.py`: 713 linhas
- `src/visualization/planner.py`: 635 linhas

Isso indica que CP-O2 resolveu parte da organização anterior, mas a complexidade voltou a se concentrar em módulos centrais.

## 3. Arquitetura atual observada

O grafo principal em `src/agent/workflow.py` está mais explícito e configurável que o snapshot antigo. O fluxo atual é:

`classify_query -> intent_planning -> list_tables -> get_schema -> plan_gate -> semantic_planner? -> query_planner/reasoning/generate_sql -> validate_sql? -> execute_sql -> repair_sql? -> generate_response`

Também existem caminhos para:

- consultas conversacionais;
- schema/contexto de tabela;
- multi-query;
- visualização/chart;
- ablations por flags.

Pontos positivos atuais:

1. O grafo suporta flags de ablation em `OrchestratorConfig`.
2. O projeto migrou para `pyproject.toml` + `uv.lock`.
3. Há CI em `.github/workflows/ci.yml`.
4. Há runners em `evaluation/runners/`, incluindo ablation e regression.
5. A camada semântica está extensa e cobre muitos contratos de domínio.
6. O fluxo de visualização está mais integrado ao orquestrador e API.
7. Há benchmark especializado de CID com resultado recente 80/80.

Pontos de atenção:

1. `docs/adrs/` ainda não existe.
2. `evaluation/benchmarks/` ainda não existe.
3. `src/application/config/table_templates_backup.py` ainda está versionado.
4. `nodes.py` ainda é basicamente um módulo de reexports.
5. O CI existe, mas o estado local atual não passa.

## 4. Verificação executada

### Testes

Comando:

```bash
uv run pytest -q
```

Resultado: falha de coleta por `SystemExit` em `tests/test_agent_improvements.py`.

Esse arquivo executa lógica no import e chama `sys.exit(...)`, o que quebra a coleta padrão do pytest. O CI ignora esse teste explicitamente, mas o comando padrão definido em `pyproject.toml` (`testpaths = ["tests"]`, `addopts = "-q"`) leva a uma falha para qualquer pessoa que rode `uv run pytest` sem flags.

Comando alternativo, aproximando o CI:

```bash
uv run pytest -q --ignore=tests/test_agent_improvements.py
```

Resultado: 6 falhas.

Falhas observadas:

1. `tests/test_api_database_explorer.py::test_process_query_validates_and_applies_table_context`
   - Causa provável: `process_query` agora passa `chart_from_last_result` para `_orchestrator.process_query`, mas o fake do teste não aceita esse kwarg. A exceção é engolida pelo handler genérico da API, então `captured["query"]` nunca é preenchido.

2. `tests/test_semantic_layer.py::test_semantic_plan_detects_death_cause_cid_antijoin`
   - O planner não adiciona `diagnostico` em `required_dimensions` para pergunta de CIDs como causa de morte nunca registrados como diagnóstico principal.

3. `tests/test_semantic_layer.py::test_semantic_validator_rejects_cid_morte_for_general_death_cause_antijoin`
   - A mensagem de erro esperada deveria mencionar `DIAG_PRINC`, mas a validação atual falha antes por tratar o plano como `single_scalar` incompatível com `GROUP BY`.

4. `tests/test_semantic_layer.py::test_semantic_validator_rejects_unbounded_death_cause_antijoin_list`
   - SQL com lista não limitada é aceito, mas o teste espera rejeição.

5. `tests/test_semantic_layer.py::test_semantic_plan_treats_counted_catalog_entity_as_scalar_not_grouping`
   - Para “Quantos códigos CID-10 estão disponíveis?”, `counted_entity` está `None`, mas deveria ser `diagnostico`.

6. `tests/test_semantic_validators.py::test_semantic_validator_accepts_cid_chapter_dimension_from_lookup_label`
   - Validador rejeita uma agregação por `DS_CAPITULO`/capítulo CID que deveria ser aceita.

Interpretação: há regressão em semântica de CID/catálogo/diagnóstico e um break de compatibilidade de assinatura no teste de API.

### Lint

Comando:

```bash
uv run ruff check src/
```

Resultado: 151 erros.

Categorias principais:

- imports desordenados;
- imports não usados;
- uso antigo de `typing.Dict`, `typing.List`, `typing.Optional`;
- `table_templates_backup.py` contribuindo para erros;
- módulos antigos em `src/utils` e `src/agent/tools` fora do padrão atual.

Isso é relevante porque o CI executa exatamente `uv run ruff check src/`.

Comando em todo o repo:

```bash
uv run ruff check .
```

Resultado: 449 erros, incluindo testes e baseline.

### Avaliação CID recente

Arquivo inspecionado:

`evaluation/cid_investigation/results/cid_agent_eval_20260522T161012_score.json`

Resumo:

- total: 80
- passed: 80
- failed: 0
- overall_pass_rate: 1.0

Distribuição por foco:

- ambiguity: 5 passed
- cid_join_aggregation: 8 passed
- cid_join_description: 15 passed
- cid_join_disease_family: 7 passed
- cid_lookup: 15 passed
- cid_structure: 10 passed
- disease_resolution: 20 passed

Distribuição por dificuldade:

- easy: 19 passed
- medium: 27 passed
- hard: 34 passed

Interpretação: existe evidência recente de bom desempenho no benchmark CID customizado, mas ela entra em tensão com as falhas unitárias atuais de semântica CID. O resultado de eval não substitui a necessidade de corrigir os contratos unitários, porque os testes estão apontando inconsistências específicas no planner/validator.

## 5. Avaliação por eixo

### 5.1 Confiabilidade

Estado: amarelo/vermelho.

O agente possui bons mecanismos de confiabilidade — validação, reparo, contratos estruturados, flags de ablation e regressão. Porém a branch atual não passa na suíte local aproximada do CI e o lint de `src/` falha. Isso torna o estado atual inadequado para merge.

Riscos concretos:

- exceções da API podem ser engolidas e retornar erro genérico em vez de quebrar teste rapidamente;
- compatibilidade de assinatura do orquestrador afeta fakes/testes;
- regressões semânticas em CID podem passar por avaliações agregadas se os casos unitários não forem respeitados;
- `uv run pytest` padrão quebra por teste que chama `sys.exit` no import.

### 5.2 Arquitetura agentic

Estado: bom para pesquisa, complexo para produção.

O uso de LangGraph está mais justificado que no snapshot antigo porque agora há:

- intent planning;
- semantic planner;
- flags de ablation;
- caminhos de visualização;
- multi-query;
- repair;
- execução/validação observável.

Ainda assim, muitos componentes permanecem difíceis de provar em termos de ganho marginal. O projeto deveria continuar exigindo evidência de ablation para cada etapa custosa.

Componentes com valor claro:

- seleção/contexto de schema via LlamaIndex;
- contratos Pydantic;
- validação SQL/semântica;
- execução tool-grounded em DuckDB;
- regressão/evaluation runners;
- camada semântica de domínio.

Componentes que precisam continuar sob suspeita:

- multi-query path;
- CoT reasoning separado;
- reparos muito amplos em `execution.py`;
- heurísticas acumuladas no planner sem separação por domínio;
- prompts e rules muito extensos.

### 5.3 Manutenibilidade

Estado: amarelo.

O repositório está melhor organizado que um protótipo inicial, mas ainda tem concentração excessiva em arquivos grandes. O pior ponto hoje é que `sql_generation.py`, `execution.py` e `semantic/planner.py` são grandes demais para evolução segura por agentes ou por humanos.

Risco prático: qualquer mudança semântica pequena pode alterar comportamento em múltiplos domínios e quebrar testes aparentemente distantes.

### 5.4 Avaliação e pesquisa

Estado: bom, com lacunas.

Pontos fortes:

- runners de regressão/ablation existem;
- CI tem job de regression condicionado;
- benchmarks especializados como CID existem;
- resultados são salvos em JSON;
- MLflow aparece no stack.

Lacunas:

- não encontrei `evaluation/benchmarks/`, embora roadmap previsse reorganização;
- resultados principais históricos não estavam em `evaluation/results/*.json` no padrão buscado;
- docs e resultados podem estar fragmentados entre subpastas;
- falta padronização final de onde ficam benchmark, results e reports.

### 5.5 Produto/API/frontend

Estado: em evolução ativa.

As mudanças não commitadas indicam foco atual em UX de gráficos/follow-up:

- `chart_from_last_result` na API;
- cache de último resultado por sessão;
- geração de chart com base no resultado anterior;
- escolha de métrica mais inteligente no planner de visualização;
- testes frontend e backend adicionados.

Risco: a mudança de API que adiciona `chart_from_last_result` quebrou pelo menos um teste com fake do orquestrador. Isso é pequeno, mas indica que o contrato de interface deve ser tratado explicitamente.

## 6. Principais problemas a corrigir agora

### P0 — Corrigir a suíte local/CI

1. Ajustar `tests/test_agent_improvements.py` para não chamar `sys.exit` no import.
   - Transformar em testes pytest normais ou mover para script fora de `tests/`.
   - Como o CI já ignora esse arquivo, o problema está principalmente na experiência local e no `pyproject.toml`.

2. Corrigir o fake em `test_api_database_explorer.py` ou tornar a chamada do endpoint compatível.
   - Opção simples: o fake aceitar `**kwargs`.
   - Opção mais robusta: definir protocolo/contrato para `process_query`.

3. Corrigir regressões CID no semantic planner/validator.
   - Restaurar `counted_entity="diagnostico"` para contagem de CID.
   - Garantir dimensões esperadas para anti-join de causa de morte vs diagnóstico principal.
   - Reavaliar regra de rejeição/aceite para capítulo CID (`DS_CAPITULO`).

4. Rodar novamente:

```bash
uv run pytest -q --ignore=tests/test_agent_improvements.py --ignore=tests/test_openai_api_isolated.py
uv run ruff check src/
uv run ruff format --check src/
```

### P1 — Sanear lint de `src/`

O CI exige `ruff check src/`, mas hoje há 151 erros. Sugestão:

1. Rodar `uv run ruff check src/ --fix` em branch separada.
2. Revisar manualmente os poucos casos não corrigidos automaticamente.
3. Considerar remover `src/application/config/table_templates_backup.py` se realmente for legado.
4. Só depois mexer em comportamento.

### P1 — Reduzir god-files críticos

Prioridade de extração:

1. `src/semantic/planner.py`
   - separar detectores de CID;
   - separar detectores temporais;
   - separar regras de ranking/top-N;
   - separar resolvers de dimensão;
   - adicionar testes por módulo.

2. `src/agent/sql_generation.py`
   - separar SQL determinístico de catálogo CID;
   - separar geração LLM;
   - separar fallback/repair hints;
   - separar funções de templates analíticos.

3. `src/agent/execution.py`
   - separar execução DB;
   - separar reparo pós-execução;
   - separar normalização de resultados;
   - separar tratamento de erro.

### P1 — Formalizar ADRs

`docs/adrs/` ainda está ausente. Recomendo criar pelo menos:

- ADR-001: LangGraph vs pipeline linear.
- ADR-002: LlamaIndex context mode como default.
- ADR-003: política de prompts/rules/versionamento.
- ADR-004: camada semântica determinística vs LLM planner.
- ADR-005: política de visualização opt-in e follow-up chart.

### P2 — Padronizar evaluation artifacts

Hoje há runners bons, mas outputs parecem dispersos. Sugestão:

- `evaluation/benchmarks/` para ground truths;
- `evaluation/results/regression/`;
- `evaluation/results/ablation/`;
- `evaluation/results/cid/`;
- `evaluation/results/chart/`;
- `evaluation/README.md` com matriz de comandos.

## 7. Recomendação de arquitetura mínima para o próximo ciclo

Não recomendo adicionar novos agentes/subagentes agora. O melhor próximo ciclo é estabilização.

Arquitetura alvo de curto prazo:

1. Manter LangGraph.
2. Manter LlamaIndex apenas como context retrieval default.
3. Manter SQL generation estruturado.
4. Manter validação semântica, mas modularizar por domínio.
5. Desabilitar ou medir explicitamente caminhos de baixo valor antes de expandi-los.
6. Tratar visualização como camada pós-query com contrato próprio, não como interferência no core Text-to-SQL.

Critério de saúde antes de novas features:

- CI local equivalente passando;
- ruff `src/` limpo;
- regressão CID/unitária corrigida;
- relatório de regressão salvo;
- pelo menos um ADR documentando a decisão atual de arquitetura.

## 8. Próximas ações sugeridas

Ordem recomendada:

1. Corrigir o teste API quebrado por `chart_from_last_result`.
2. Remover/reestruturar `tests/test_agent_improvements.py` para não quebrar coleta.
3. Corrigir regressões semânticas de CID.
4. Rodar CI local completo.
5. Fazer commit separado apenas de estabilização.
6. Fazer PR/refactor separado para ruff/lint automático.
7. Criar ADRs.
8. Só então continuar features de gráficos ou novas heurísticas.

## 9. Conclusão

O agente atual é forte como artefato de pesquisa aplicada: tem uma arquitetura rica, avaliação especializada, semântica de domínio e fluxo de ferramenta/execução real. O problema não é falta de capacidade; é excesso de complexidade sem estado verde de qualidade.

A melhor decisão agora é tratar a branch como instável: corrigir testes e lint, modularizar os maiores arquivos e documentar decisões arquiteturais antes de expandir autonomia ou adicionar novos caminhos agentic.
