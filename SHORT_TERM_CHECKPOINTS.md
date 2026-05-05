# Checkpoints de Curto Prazo - Agente Text-to-SQL

Data de criacao: 2026-05-05

Objetivo: acompanhar a implementacao das melhorias de curto prazo para robustez semantica do agente, sem ajustar regras para perguntas especificas do benchmark.

## Escopo

As tasks de curto prazo atacam falhas semanticas recorrentes em queries hard:

- output shape incorreto
- top-N por grupo
- denominadores de taxas
- comparacoes temporais
- anti-condicoes
- granularidade e agrupamento
- preservacao de identificadores na resposta final
- observabilidade do workflow real via CLI

## Checkpoint 1 - Semantic plan antes da SQL

Status: concluido

Implementacao:

- [x] Criar modelos tipados para contrato semantico: intent, metricas, dimensoes, filtros, shape da resposta e constraints.
- [x] Criar planner inicial independente do benchmark.
- [x] Detectar padroes genericos: ranking, taxa, tendencia, distribuicao, count e anti-condicao.
- [x] Detectar top-N global versus top-N por grupo.
- [x] Detectar preservacao de denominador em taxas.
- [x] Detectar politica para bucket de valores desconhecidos ou sem informacao.
- [x] Armazenar `semantic_plan` no state do workflow.

Arquivos:

- `src/semantic/plan_schema.py`
- `src/semantic/planner.py`
- `src/agent/plan_gate.py`
- `src/agent/state_models.py`
- `src/agent/state_helpers.py`

Teste:

- [x] Teste unitario para top-N por grupo.
- [x] Teste unitario para taxa de mortalidade sem filtro de desfecho no denominador.
- [x] Teste unitario para anti-condicao.
- [x] Teste unitario para evitar falso positivo de `idade` dentro de `mortalidade`.
- [x] Teste unitario para detectar `para cada sexo` como top-N por grupo.

Evidencia:

- `pytest tests/test_semantic_layer.py -q`
- Resultado observado: 10 testes passando.

## Checkpoint 2 - Injecao do plano semantico no prompt SQL

Status: concluido

Implementacao:

- [x] Renderizar o `SemanticPlan` como bloco explicito no prompt.
- [x] Injetar o bloco na pergunta usada pelo gerador SQL.
- [x] Manter o plano generico, sem IDs de ground truth ou regras especificas de benchmark.

Arquivos:

- `src/semantic/plan_schema.py`
- `src/agent/sql_generation.py`

Teste:

- [x] Teste unitario garantindo que SQL generation continua funcionando com o novo state.
- [x] Execucao real via CLI em queries hard.

Evidencia:

- `pytest tests/test_sql_generation_module_split.py -q`
- CLI hard query top-N por grupo gerou janela com `ROW_NUMBER() OVER (PARTITION BY ...)`.

## Checkpoint 3 - Validacao semantica da SQL

Status: concluido

Implementacao:

- [x] Bloquear top-N por grupo sem window function particionada.
- [x] Bloquear taxa de mortalidade com `WHERE MORTE = true`, pois isso corrompe o denominador.
- [x] Bloquear anti-condicao sem `NOT EXISTS`, `LEFT JOIN ... IS NULL` ou aggregate-zero.
- [x] Bloquear casos de "sem informacao" sem politica explicita de nulos.
- [x] Integrar validacao semantica ao node de validacao antes da execucao.

Arquivos:

- `src/semantic/validators.py`
- `src/agent/validation.py`

Teste:

- [x] Teste unitario rejeitando `LIMIT` global para top-N por grupo.
- [x] Teste unitario aceitando window function por grupo.
- [x] Teste unitario rejeitando denominador filtrado por obito.
- [x] Teste unitario aceitando aggregate-zero para ausencia.

Evidencia:

- `pytest tests/test_semantic_layer.py -q`

Risco residual:

- Validacao ainda e baseada em padroes textuais. Proximo passo recomendado: AST SQL para reduzir falsos positivos e falsos negativos.

## Checkpoint 4 - Defaults de table selection sem mascarar preset

Status: concluido

Implementacao:

- [x] Remover defaults explicitos que impediam o preset `llm_best` de resolver corretamente.
- [x] Ajustar config para `table_selection_mode`, `table_selection_description_variant` e `table_selection_prompt_variant` usarem `None` quando nao sobrescritos.
- [x] Ajustar CLI para nao sobrescrever o preset com defaults antigos.

Arquivos:

- `src/application/config/simple_config.py`
- `src/interfaces/cli/agent.py`
- `tests/test_table_selection_benchmark.py`

Teste:

- [x] Teste unitario confirmando resolucao do preset `llm_best`.
- [x] Execucao real via CLI usando selecao LLM.

Evidencia:

- `pytest tests/test_table_selection_benchmark.py -q`
- Em query de procedimento, selector escolheu `internacoes`, `atendimentos`, `procedimentos`.
- Em query de taxa por estado, selector escolheu `internacoes`, `municipios`.

## Checkpoint 5 - Observabilidade do workflow real

Status: concluido

Implementacao:

- [x] Corrigir CLI que passava kwargs nao suportados para `process_query`.
- [x] Corrigir exibicao incorreta de roteamento no debug.
- [x] Exibir `semantic_plan` no step `PLAN_GATE`.
- [x] Validar pelo agente real, nao apenas por testes unitarios.

Arquivos:

- `src/interfaces/cli/agent.py`

Teste:

- [x] `python src/interfaces/cli/agent.py --health-check`
- [x] `python src/interfaces/cli/agent.py --query "<hard query>" --debug-steps --timeout 180`

Evidencia:

- Health check: passou.
- Debug CLI mostrou `Semantic Plan` antes de `GENERATE_SQL`.

## Checkpoint 6 - Validacao real em queries hard

Status: concluido

Queries testadas:

1. Top-N por grupo:

Pergunta:

`Quais sao os 5 procedimentos mais comuns para cada sexo em internacoes que resultaram em obito?`

Resultado esperado:

- [x] Selecionar `internacoes`, `atendimentos`, `procedimentos`.
- [x] Plano semantico com `top_n_scope = per_group`.
- [x] Constraint `top_n_per_group_requires_window_partition`.
- [x] SQL com `ROW_NUMBER() OVER (PARTITION BY i."SEXO" ...)`.
- [x] SQL executada com sucesso.

2. Taxa com denominador:

Pergunta:

`Qual a evolucao anual da taxa de mortalidade por estado para SP e RJ?`

Resultado esperado:

- [x] Selecionar `internacoes`, `municipios`.
- [x] Plano semantico com metrica `taxa_mortalidade`.
- [x] Constraint `rate_denominator_must_preserve_full_scope`.
- [x] SQL sem `WHERE i."MORTE" = true`.
- [x] SQL usando `COUNT(*)` como denominador e `SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END)` como numerador.
- [x] SQL executada com sucesso.

3. Anti-condicao:

Pergunta:

`Quais hospitais com mais de 1000 internacoes nunca tiveram internacao em UTI?`

Resultado esperado:

- [x] Plano semantico com constraint `absence_condition_requires_antijoin_or_aggregate_zero`.
- [x] SQL com `HAVING COUNT(*) > 1000`.
- [x] SQL com `NOT EXISTS` correlacionado por `CNES`.
- [x] SQL executada com sucesso.
- [x] Resposta final preservando `CNES`, sem inventar nomes de hospitais.
- [x] Resposta final limitada a 10 itens visiveis em lista longa.

## Checkpoint 7 - Resposta final fiel ao resultado

Status: concluido

Implementacao:

- [x] Reforcar prompt de sintese para preservar identificadores.
- [x] Proibir rotulos inventados como `Hospital 1`.
- [x] Evitar inventar totalizacoes quando o resultado estiver truncado.
- [x] Limitar listas longas a 10 itens.

Arquivos:

- `src/agent/response.py`

Teste:

- [x] Reteste da query de hospitais sem UTI via CLI.

Evidencia:

- Resposta final passou a retornar `CNES 2772299`, `CNES 2457121`, etc.

## Checkpoint 8 - Guardrails contra benchmark hacking

Status: concluido

Validacoes:

- [x] Nao adicionar regras para IDs de ground truth.
- [x] Nao hardcodar perguntas especificas.
- [x] Nao adicionar valores esperados de resposta.
- [x] Manter constraints como padroes semanticos gerais.

Comando usado:

`rg -n "GT[0-9]{3}|ground_truth|benchmark" src/semantic src/agent/validation.py src/agent/plan_gate.py src/agent/sql_generation.py`

Resultado:

- Apenas comentarios de protecao contra benchmark-specific foram encontrados.

## Checkpoint 9 - Suite de regressao local

Status: concluido

Comandos:

- [x] `pytest tests/test_semantic_layer.py tests/test_table_selection_benchmark.py tests/test_sql_generation_module_split.py -q`
- [x] `python -m compileall src/semantic src/agent src/application/config tests/test_semantic_layer.py`
- [x] `git diff --check`

Resultado observado:

- `24 passed` na suite selecionada.
- Compile passou.
- `git diff --check` sem problemas.

## Pendencias tecnicas para proximo ciclo

Status: pendente

- [ ] Trocar validadores textuais por validacao baseada em AST SQL.
- [ ] Criar camada semantica declarativa versionada com metricas, dimensoes, regras e macros SQL.
- [ ] Adicionar data profiling para cardinalidade, nulos, dominios de codigos e ranges temporais.
- [ ] Criar avaliacao por taxonomia de erro semantico, nao apenas execution accuracy.
- [ ] Adicionar semantic equivalence checks para SQLs diferentes com mesma intencao.
- [ ] Criar conjunto de testes adversariais fora do ground truth atual.
- [ ] Persistir telemetria do `semantic_plan`, SQL validada, constraints aplicadas e motivos de rejeicao.
- [ ] Melhorar parsing de resultados do executor para evitar `row_count = 1` quando o retorno vem como string contendo varias tuplas.

## Estado atual

Resumo:

- Camada semantica inicial implementada.
- Workflow real validado por CLI.
- Tres classes hard testadas com sucesso: top-N por grupo, taxa com denominador e anti-condicao.
- Resposta final melhorada para nao inventar rotulos e para limitar listas longas.
- Ainda falta evoluir a validacao para AST e transformar o planner inicial em camada semantica declarativa.
