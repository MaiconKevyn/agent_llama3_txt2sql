# Plano iterativo de refactor arquitetural do agente

Data: 2026-05-22
Branch alvo: `llamaindex_dev`
Escopo: god-files do core, join policy, budget/timeout/custo, testes e validacao em agente real.

## Objetivo

Evoluir a arquitetura sem reescrever o projeto, sem criar multi-agent, sem espalhar regras hardcoded e sem multiplicar arquivos desnecessariamente. A funcionalidade publica deve continuar igual, mas com limites mais claros entre responsabilidades, melhor testabilidade e guardrails operacionais mais consistentes.

Este plano substitui a ideia de "quebrar tudo em muitos modulos" por uma migracao iterativa: medir, extrair apenas responsabilidades estaveis, manter facades publicas, validar comportamento existente e so entao consolidar a nova estrutura.

## Principios de design

1. Preservar comportamento antes de melhorar estrutura.
2. Preferir contratos gerais a regras especificas no codigo.
3. Separar responsabilidade quando isso reduz leitura, duplicacao ou risco de regressao.
4. Evitar abstracoes genericas sem uso real.
5. Manter poucos arquivos, com nomes de dominio claros.
6. Usar dados/configuracao tipada para politicas, nao `if` espalhado por caso.
7. Medir melhoria com gates objetivos: testes, benchmarks, tamanho de arquivos, metadata e smoke no agente real.
8. Qualquer mudanca de arquitetura precisa ter caminho de rollback simples.

## Nao objetivos

- Nao migrar para multi-agent.
- Nao trocar LangGraph, LlamaIndex ou stack principal.
- Nao reescrever SQL generation do zero.
- Nao transformar cada helper em um arquivo proprio.
- Nao criar regras hardcoded para cada tabela, CID ou pergunta.
- Nao aceitar queda de comportamento em benchmark para ganhar organizacao.

## Problemas tratados

### 1. God-files grandes

Arquivos atuais de maior risco:

- `src/semantic/planner.py`
- `src/agent/execution.py`
- `src/agent/sql_generation.py`
- `src/semantic/validators.py`
- `src/agent/response.py`

Problema: muita decisao de dominio, validacao, reparo, execucao e formatacao esta concentrada em arquivos que exigem contexto demais para uma revisao segura.

Direcao: modularizar por responsabilidade estavel, mantendo APIs publicas e evitando dezenas de microarquivos.

### 2. Join policy parcialmente caveat-first

Estado atual: ha bloqueio pre-execucao para joins `audit_only` criticos, mas a aplicacao da politica nao e universal nem expressa como contrato central. Algumas decisoes vivem em validadores e caveats de resposta.

Direcao: criar uma politica geral de enforcement baseada no contrato de join, com estados declarativos e testes parametrizados para todos os casos do catalogo.

### 3. Budget, timeout e custo parciais

Estado atual: ha timeout de LLM, tracking de custo e bloqueio de SQL nao-SELECT, mas nao ha politica central aplicada de ponta a ponta para chamadas LLM, retries, execucao SQL, proxy frontend e metadados.

Direcao: introduzir uma politica simples de runtime budget, observavel e testavel, sem framework novo.

## Arquitetura alvo

### Estrutura de arquivos esperada

O plano permite poucos arquivos novos. A meta e reduzir god-files sem transformar o repo em labirinto.

Arquivos ou pacotes candidatos:

```text
src/agent/
  sql_generation.py              # facade publica temporaria
  sql_builders.py                # builders deterministas estaveis
  sql_fallback.py                # fallback LLM e parsing de resultado estruturado
  execution.py                   # facade publica temporaria
  execution_contracts.py         # contratos pre/post execucao
  runtime_budget.py              # budget, timeout, custo e retries
  response.py                    # facade publica temporaria
  response_caveats.py            # caveats baseados em contratos

src/semantic/
  planner.py                     # facade publica temporaria
  plan_inference.py              # inferencia de filtros, metricas e dimensoes
  validators.py                  # facade publica temporaria
  validation_contracts.py        # validacoes gerais orientadas por contrato

src/semantic/contracts/
  join_policy.py                 # fonte tipada da politica de join
```

Limite de simplicidade: cada iteracao pode adicionar no maximo 2 arquivos novos de producao, exceto testes. Se uma extracao exigir mais que isso, a tarefa deve ser quebrada.

### APIs que devem permanecer estaveis

- `build_semantic_plan(...)`
- `validate_sql_against_semantic_plan(...)`
- `generate_sql_node(...)`
- `execute_sql_node(...)`
- `generate_response_node(...)`
- `execute_sql_workflow(...)`
- formato legado retornado por `state_to_legacy_format(...)`

## Plano de implementacao

### Iteracao 0 - Baseline mensuravel

Objetivo: congelar comportamento e criar uma linha de base antes de qualquer refactor.

Tarefas:

1. Registrar tamanho dos arquivos core com `wc -l`.
2. Registrar imports publicos usados por testes/scripts.
3. Rodar testes focados de join policy, SQL safety, semantic layer, response caveats e benchmark runner.
4. Rodar benchmark v1 atual e threshold check.
5. Registrar smoke real do agente com 5 perguntas se `DATABASE_URL` estiver disponivel.

Criterios de aceite:

- Baseline salvo em arquivo pequeno de texto ou markdown allowlisted.
- Score e threshold atuais conhecidos.
- Lista de APIs publicas congelada.
- Nenhum refactor iniciado antes do baseline.

Validacao:

```bash
wc -l src/semantic/planner.py src/agent/execution.py src/agent/sql_generation.py src/semantic/validators.py src/agent/response.py
rg "from src.agent.sql_generation|from src.agent.execution|from src.semantic.planner|from src.semantic.validators" src tests evaluation
./.venv/bin/pytest tests/test_join_policy_contracts.py tests/test_sql_execution_block.py tests/test_response_domain_caveats.py tests/test_generalization_benchmark_runner.py tests/test_release_thresholds.py -q
./.venv/bin/python -m evaluation.agent.release_thresholds evaluation/agent/results/generalization_exhaustion_20260522T205851.json
```

Checkpoint:

- Se qualquer teste focado falhar, corrigir ou registrar como baseline quebrado antes de continuar.

### Iteracao 1 - Join policy como contrato de enforcement

Objetivo: substituir decisao seletiva hardcoded por uma politica declarativa geral, sem perder os bloqueios atuais.

Design:

- `JoinPolicy` deve expor uma decisao unica: `enforcement`.
- Valores permitidos:
  - `allow`: join permitido sem caveat obrigatorio.
  - `allow_with_caveat`: join permitido, mas resposta precisa explicar cobertura/escopo.
  - `block`: join rejeitado antes de execucao.
- O mapeamento deve vir do contrato existente (`accepted_usage_policy`, cobertura e confianca), nao de `if` por pergunta.
- Caso uma excecao de dominio seja inevitavel, ela deve entrar como dado versionado no contrato, nao como condicional espalhada no validator.

Tarefas:

1. Adicionar metodo/propriedade `enforcement` em `src/semantic/contracts/join_policy.py`.
2. Fazer `validators.py` consumir `policy.enforcement == "block"`.
3. Fazer `response_caveats` ou `response.py` consumir `policy.enforcement == "allow_with_caveat"`.
4. Remover ou reduzir hard-code seletivo do validator, mantendo compatibilidade dos casos atuais.
5. Criar testes parametrizados lendo todas as policies carregadas.

Criterios de aceite:

- Todo `audit_only` tem comportamento explicitamente testado.
- Nenhum join bloqueado hoje passa a executar sem decisao explicita.
- Nenhum caveat aparece para joins `allow` sem necessidade.
- O contrato explica o motivo da decisao em metadata ou mensagem de validacao.

Validacao:

```bash
./.venv/bin/pytest tests/test_join_policy_contracts.py tests/test_response_domain_caveats.py -q
./.venv/bin/pytest tests/test_semantic_validators.py -q
rg "_join_policy_is_hard_blocked|CID_MORTE|DIAG_SECUN" src/semantic src/agent tests
```

Garantia de melhoria:

- Antes: enforcement parcial, com bloqueio seletivo no validator.
- Depois: todas as policies carregadas possuem decisao declarativa e teste parametrizado.

### Iteracao 2 - RuntimeBudgetPolicy para LLM, DB e frontend

Objetivo: criar um contrato simples e central para timeout, custo e retries por pergunta.

Design:

Um `RuntimeBudgetPolicy` deve representar:

- `request_timeout_seconds`
- `llm_timeout_seconds`
- `sql_timeout_seconds`
- `max_llm_calls`
- `max_retries`
- `max_total_tokens`
- `max_estimated_cost_usd`
- `frontend_timeout_seconds`

O primeiro passo pode ser observability-first com fail-closed apenas para limites seguros e claros. O plano nao deve bloquear usuarios por estimativas frageis de custo. Onde nao houver medicao confiavel, registrar metadata e criar gate de regressao.

Tarefas:

1. Criar `src/agent/runtime_budget.py` com dataclass simples e helpers puros.
2. Integrar o budget ao workflow state/metadata sem alterar resposta publica.
3. Contar chamadas LLM via wrapper central em `llm_manager.invoke_chat` e `invoke_chat_structured`.
4. Aplicar timeout real em execucao SQL quando suportado pelo backend; caso contrario, registrar que o backend nao suporta timeout hard.
5. Trocar `fetch(..., timeout: ...)` do frontend por `AbortController`.
6. Padronizar erro de budget/timeout como resposta recuperavel e metadata auditavel.

Criterios de aceite:

- Toda chamada LLM feita via manager atualiza contadores.
- Timeout do frontend e real, nao apenas propriedade ignorada pelo `fetch`.
- Timeout SQL e aplicado ou explicitamente marcado como unsupported no metadata.
- Excesso de retries ou chamadas LLM interrompe o fluxo com erro claro.
- Resultado final inclui `runtime_budget` em metadata.

Validacao:

```bash
./.venv/bin/pytest tests/test_orchestrator_support.py tests/test_sql_execution_block.py tests/test_api_debug_contract.py -q
./.venv/bin/pytest tests/test_runtime_budget.py -q
node --check frontend/server.js
```

Testes novos esperados:

- Budget inicial usa defaults atuais.
- Contador de LLM incrementa em `invoke_chat`.
- Contador de LLM incrementa em `invoke_chat_structured`.
- Max retries respeita config existente.
- Timeout frontend usa `AbortController`.
- Query SQL nao-SELECT continua bloqueada antes de tocar DB.
- Quando SQL timeout nao for suportado, metadata explicita isso.

Garantia de melhoria:

- Antes: custo/timeout existiam como partes soltas.
- Depois: budget vira contrato unico, visivel em metadata e testado em pontos de entrada.

### Iteracao 3 - Extrair SQL generation sem mudar comportamento

Objetivo: reduzir `src/agent/sql_generation.py` mantendo a API publica.

Design:

Extrair apenas blocos com responsabilidade estavel:

- builders deterministas;
- fallback LLM;
- parsing/normalizacao do output SQL.

Nao criar arquivo por tipo de query. Usar no maximo dois arquivos novos nesta iteracao.

Tarefas:

1. Criar `src/agent/sql_builders.py` com builders deterministas ja existentes.
2. Criar `src/agent/sql_fallback.py` se o fallback LLM estiver misturado demais.
3. Manter `generate_sql_node` em `sql_generation.py` como facade.
4. Migrar testes para validar comportamento pela API publica, nao pelo helper privado.
5. Medir reducao de linhas e manter cobertura dos casos atuais.

Criterios de aceite:

- `generate_sql_node` continua importavel do mesmo lugar.
- Resultado SQL dos testes existentes nao muda.
- Nenhum helper extraido depende de `MessagesStateTXT2SQL` se puder receber argumentos simples.
- Arquivos novos ficam abaixo de 1.000 linhas.

Validacao:

```bash
./.venv/bin/pytest tests/test_sql_generation_module_split.py tests/test_semantic_layer.py tests/test_llamaindex_sql_generator.py -q
./.venv/bin/ruff check src/agent/sql_generation.py src/agent/sql_builders.py src/agent/sql_fallback.py
wc -l src/agent/sql_generation.py src/agent/sql_builders.py src/agent/sql_fallback.py
```

Garantia de melhoria:

- Reducao de blast radius sem mudanca de API.
- Builders passam a ser testaveis sem montar workflow completo.

### Iteracao 4 - Extrair execution contracts e response caveats

Objetivo: separar execucao, contratos pre/post execucao e caveats de resposta.

Design:

- `execution.py` continua dono do node.
- `execution_contracts.py` concentra checks gerais pre/post execucao.
- `response_caveats.py` concentra caveats derivados de contratos e metadata.
- A resposta final continua usando o mesmo formato.

Tarefas:

1. Mover checks pre-execucao gerais para `execution_contracts.py`.
2. Mover checks post-execucao gerais para `execution_contracts.py`.
3. Mover caveats de join/data quality/domain para `response_caveats.py` quando forem puramente derivados de contrato.
4. Preservar funcoes publicas e imports antigos temporariamente.

Criterios de aceite:

- SQL nao-SELECT continua bloqueado antes de DB.
- Caveats existentes continuam aparecendo nos mesmos cenarios.
- `response.py` fica focado em montagem de resposta, nao em politica de dominio.

Validacao:

```bash
./.venv/bin/pytest tests/test_sql_execution_block.py tests/test_response_domain_caveats.py tests/test_api_debug_contract.py -q
./.venv/bin/pytest tests/test_join_policy_contracts.py -q
wc -l src/agent/execution.py src/agent/execution_contracts.py src/agent/response.py src/agent/response_caveats.py
```

Garantia de melhoria:

- Politicas ficam testaveis como funcoes puras.
- Node de execucao fica mais legivel sem perder guardrails.

### Iteracao 5 - Simplificar semantic planner e validators

Objetivo: reduzir tamanho e acoplamento do planejamento semantico sem virar rule engine complexa.

Design:

Extrair uma unica camada de inferencia:

- `plan_inference.py`: funcoes puras de inferencia de filtros, metricas e dimensoes.
- `validation_contracts.py`: validacoes gerais orientadas por contrato.

Nao criar subpastas por dominio inicialmente.

Tarefas:

1. Mover funcoes puras de normalizacao/inferencia para `plan_inference.py`.
2. Manter `build_semantic_plan` como facade em `planner.py`.
3. Mover validacoes orientadas por contrato para `validation_contracts.py`.
4. Manter regras especificas apenas quando derivadas de contrato tipado ou schema.
5. Criar testes de invariancia para planos semanticos representativos.

Criterios de aceite:

- `build_semantic_plan` retorna planos equivalentes para suite representativa.
- `validators.py` delega contratos gerais sem perder mensagens atuais.
- Nenhum novo registry generico e criado sem consumidor real.

Validacao:

```bash
./.venv/bin/pytest tests/test_semantic_layer.py tests/test_semantic_validators.py tests/test_semantic_planner_node.py -q
./.venv/bin/ruff check src/semantic/planner.py src/semantic/plan_inference.py src/semantic/validators.py src/semantic/validation_contracts.py
wc -l src/semantic/planner.py src/semantic/plan_inference.py src/semantic/validators.py src/semantic/validation_contracts.py
```

Garantia de melhoria:

- Planejamento fica mais localmente testavel.
- Validacao passa a depender menos de condicionais espalhadas.

### Iteracao 6 - Teste exaustivo e agente real

Objetivo: provar que a versao final refatorada manteve comportamento e melhorou manutencao.

Testes automatizados obrigatorios:

```bash
./.venv/bin/ruff check src/ evaluation/agent tests/
./.venv/bin/ruff format --check src/ evaluation/agent tests/
./.venv/bin/pytest tests/ --ignore=tests/test_agent_improvements.py --ignore=tests/test_openai_api_isolated.py -q
./.venv/bin/pytest tests/test_join_policy_contracts.py tests/test_runtime_budget.py tests/test_sql_execution_block.py tests/test_response_domain_caveats.py tests/test_generalization_benchmark_runner.py tests/test_release_thresholds.py -q
```

Benchmark obrigatorio:

```bash
./.venv/bin/python -m evaluation.agent.run_generalization_exhaustion --benchmark evaluation/benchmarks/v1
./.venv/bin/python -m evaluation.agent.release_thresholds <novo_resultado_json>
```

Smoke real obrigatorio se `DATABASE_URL` estiver configurado:

1. Contagem simples de internacoes.
2. Pergunta temporal.
3. Pergunta com CID principal.
4. Pergunta com join que exige caveat.
5. Pergunta que deve bloquear join `audit_only`.
6. Pergunta fora do schema.
7. Pergunta com grafico.
8. Pergunta longa que force budget/retry metadata.

Criterios de aceite final:

- Benchmark v1 nao cai abaixo dos thresholds atuais.
- Casos de `audit_only` bloqueados continuam bloqueados.
- Casos `allow_with_caveat` continuam respondendo com caveat.
- SQL nao-SELECT continua bloqueado.
- Metadata inclui budget/custo/timeout de forma consistente.
- Nenhum arquivo core novo passa de 1.000 linhas.
- Pelo menos dois god-files reduzem tamanho sem troca de API publica.
- Nenhum modulo novo existe apenas como wrapper vazio.

## Matriz de melhoria

| Area | Medida antes | Medida depois esperada | Prova |
| --- | ---: | ---: | --- |
| SQL generation | arquivo grande e misto | facade + builders/fallback testaveis | `wc -l`, testes SQL |
| Execution | execucao + contratos mistos | node + contratos puros | testes execution/block |
| Join policy | hard-block seletivo | enforcement declarativo por policy | testes parametrizados |
| Budget | tracking parcial | contrato unico em metadata | `tests/test_runtime_budget.py` |
| Frontend timeout | `fetch timeout` ignoravel | `AbortController` | teste/unit ou `node --check` + smoke |
| Semantic planner | inferencia concentrada | facade + inferencia pura | semantic tests |

## Controle anti-overfitting

- Toda nova regra precisa vir de contrato, schema, metadata ou policy geral.
- Nenhum teste deve depender de uma pergunta unica se o comportamento e geral.
- Casos de benchmark devem cobrir dominios, nao memorizar strings.
- Mensagens podem variar, mas categoria de erro, bloqueio e metadata devem ser estaveis.
- Regras de join devem ser parametrizadas por catalogo, nao por nome de pergunta.
- Budget deve operar por limites gerais de request, nao por modelo especifico.

## Controle anti-overengineering

- No maximo 2 arquivos novos de producao por iteracao.
- Sem interfaces ou factories antes de haver duas implementacoes reais.
- Sem registry generico se uma dataclass e funcoes puras resolverem.
- Sem mover codigo que nao reduza linhas, dependencia ou duplicacao.
- Toda extracao precisa preservar facade publica ate o final.
- Se um modulo novo tiver menos de 80 linhas e um unico caller, reavaliar se ele deve existir.

## Checklist de entrega por iteracao

Cada iteracao so pode ser concluida quando:

- [ ] O diff e pequeno o bastante para revisao.
- [ ] As APIs publicas continuam importaveis.
- [ ] Testes focados passam.
- [ ] O resultado comportamental foi comparado com baseline quando aplicavel.
- [ ] O plano foi atualizado com resultado real, nao expectativa.
- [ ] Nenhuma mudanca nao relacionada foi misturada.

## Checklist final antes de merge

- [ ] `ruff check` passa.
- [ ] `ruff format --check` passa.
- [ ] Pytest completo passa ou falhas conhecidas estao documentadas com motivo.
- [ ] Benchmark v1 passa threshold.
- [ ] Smoke real do agente foi executado.
- [ ] Relatorio final registra score, latencia, erros, budget metadata e diff de tamanho dos arquivos.
- [ ] Commits estao fatiados por tema.
- [ ] Artefatos volumosos de avaliacao nao foram adicionados por acidente.

## Ordem recomendada de commits

1. `test(architecture): capture refactor baseline`
2. `refactor(join-policy): centralize enforcement semantics`
3. `feat(runtime): add request budget policy`
4. `refactor(sql): extract deterministic builders`
5. `refactor(execution): extract execution contracts`
6. `refactor(response): extract contract caveats`
7. `refactor(semantic): extract plan inference contracts`
8. `test(evaluation): validate refactored agent release gates`

## Resultado esperado

Ao final, o projeto deve continuar simples de entender:

- workflow principal igual;
- entrypoints publicos iguais;
- menos codigo critico concentrado em arquivos gigantes;
- politicas de join e budget explicitas;
- testes cobrindo contratos gerais;
- agente real validado com benchmark e smoke.

Melhoria nao sera declarada por percepcao. Ela sera aceita apenas se os gates de comportamento continuarem verdes e os indicadores de manutencao melhorarem de forma mensuravel.
