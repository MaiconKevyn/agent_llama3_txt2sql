# Avaliação Agentic AI + Chatbot TXT2SQL

Data: 2026-05-22
Repositório: `/home/maiconkevyn/PycharmProjects/txt2sql_refactor_openai_v2`
Branch avaliada: `llamaindex_dev`
Último commit observado: `ba8faf5 fix(cid): preserve cid catalog and hierarchy semantics`
Objetivo avaliado: chatbot Text-to-SQL capaz de generalizar perguntas sobre o banco DuckDB SIHRD5/DataVisSUS.

## 1. Nota executiva

Nota geral atual: **7.0 / 10**

Potencial técnico após estabilização: **8.3 / 10**

Minha leitura: o projeto já passou do estágio de protótipo simples. Ele tem arquitetura agentic real, documentação de banco rica, LangGraph, LlamaIndex, camada semântica, validação SQL, execução real contra DuckDB, avaliação por ground truth, testes de generalização e respostas com resultados. Para um projeto de chatbot Text-to-SQL sobre um banco grande e semântico como SIH/SUS, isso é forte.

Mas ele ainda não merece nota 8+ em estado atual porque a branch está instável: testes falham, lint falha, há mudanças não commitadas, algumas regras semânticas CID estão quebradas e a experiência conversacional ainda parece mais um executor analítico síncrono do que um chatbot robusto de produto.

Resumo por dimensão:

| Dimensão | Nota | Diagnóstico |
| --- | ---: | --- |
| Arquitetura agentic | 7.8 | LangGraph bem aplicado, estado rico, ferramentas e validação; ainda com complexidade alta e arquivos grandes. |
| Text-to-SQL factual | 7.4 | Boa geração/execução em perguntas testadas; depende de macros/heurísticas e precisa ampliar validação semântica. |
| Generalização | 7.0 | Boa cobertura sobre famílias analíticas planejadas; ainda não prova “qualquer pergunta”. |
| Chatbot/UX | 6.2 | Responde bem, mas falta camada conversacional, follow-up, clarificação e transparência amigável. |
| Guardrails semânticos | 7.1 | Tem join policy, DQ, validators e safe refusal; regressões em CID mostram fragilidade. |
| Observabilidade/eval | 7.6 | Métricas por fase, tool calls, benchmark e exhaustion runner; falta dashboard/score contínuo estável. |
| Prontidão de produção | 5.8 | Testes e ruff falham; branch atual não deve ir para produção/merge sem correções. |
| Manutenibilidade | 6.3 | Bons módulos, mas arquivos críticos gigantes concentram risco. |

## 2. Evidências coletadas

### 2.1 Estado Git

Comando executado:

```bash
git status --short && git branch --show-current && git log -1 --oneline
```

Resultado observado:

- Branch: `llamaindex_dev`
- Último commit: `ba8faf5 fix(cid): preserve cid catalog and hierarchy semantics`
- Arquivos modificados:
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
- Arquivos gerados nesta avaliação:
  - `evaluation/agent/results/generalization_exhaustion_20260522T182120.json`
  - `evaluation/agent/results/generalization_exhaustion_20260522T182130.json`
  - `evaluation/agent/results/generalization_exhaustion_20260522T182142.json`
  - `evaluation/agent/results/generalization_exhaustion_20260522T182157.json`
  - `evaluation/results/agent_state_review_2026-05-22.markdown`

Interpretação: avaliação feita sobre branch com trabalho em andamento. O score mede o estado atual do workspace, não um release limpo.

### 2.2 Tamanho dos módulos críticos

Arquivos críticos observados:

| Arquivo | Linhas | Comentário |
| --- | ---: | --- |
| `src/agent/orchestrator.py` | 837 | Entry point/orquestração principal; aceitável, mas crescendo. |
| `src/agent/workflow.py` | 458 | Define DAG/fluxo LangGraph; tamanho saudável. |
| `src/agent/sql_generation.py` | 2.737 | Alto risco: geração, macros e regras demais no mesmo arquivo. |
| `src/semantic/planner.py` | 3.911 | Principal gargalo de manutenção; concentra semântica complexa. |
| `src/semantic/validators.py` | 1.537 | Importante, mas já grande. |
| `src/interfaces/api/main.py` | 905 | API grande; mistura contratos, endpoints e lógica auxiliar. |
| `evaluation/agent/run_generalization_exhaustion.py` | 330 | Ferramenta útil de avaliação de limites. |

## 3. Arquitetura atual do agente

A arquitetura atual tem os componentes certos para um chatbot Text-to-SQL agentic:

1. Classificação da pergunta.
2. Planejamento/intenção.
3. Descoberta de tabelas via LlamaIndex + heurísticas.
4. Recuperação de schema/contexto.
5. Gate de plano.
6. Planejamento semântico.
7. Geração SQL por LLM, macro determinística ou fallback.
8. Validação SQL.
9. Execução DuckDB.
10. Repair quando aplicável.
11. Resposta final em linguagem natural.
12. Metadados de execução, latência e tool calls.

Fluxo observado em logs reais:

```text
Classification -> Table discovery -> Schema -> Plan gate -> Semantic planner -> SQL generation -> SQL validation -> SQL execution -> Final answer
```

Essa é uma arquitetura correta para a aplicação. A decisão de usar LangGraph é justificada porque há estado intermediário, ramos condicionais, validação, execução e reparo. Este não é um caso em que uma única chamada LLM seria suficiente.

### Pontos fortes agentic

- O agente executa tarefas reais: consulta banco, valida SQL e retorna resultado.
- Tem ferramentas com telemetria (`sql_db_list_tables`, `sql_db_query_checker`, `sql_db_query`).
- Tem estado estruturado com `semantic_plan`, `intent_plan`, `tool_plan`, `plan_audit`, `result_audit`, `domain_caveats`.
- Tem fast-path heurístico para evitar LLM em classificação simples.
- Tem recusa segura para dados inexistentes no schema.
- Tem runner de generalização com famílias anti-overfit.
- Tem documentação gerada de banco que pode virar fonte primária de guardrails.

### Fragilidades agentic

- Muitos comportamentos críticos estão em heurísticas/macros dentro de arquivos muito grandes.
- A avaliação ainda é parcialmente dependente de casos selecionados, não de uma matriz contínua versionada com score por domínio.
- O agente ainda não parece ter uma política forte e uniforme de clarificação quando há ambiguidade.
- O repair existe, mas não está claro se há limites suficientemente rígidos para evitar loops, custo excessivo ou correções semanticamente erradas.
- Safe refusal funciona em casos testados, mas apareceu como `success=False` com status `passed`, o que é correto para avaliação, mas pode confundir métricas de produto se não separar `task_success` de `answerability`.

## 4. Teste de limites executado

Usei o runner existente:

```bash
uv run python -m evaluation.agent.run_generalization_exhaustion --ids GEN001,GEN020,GEN037,GEN057,GEN079,GEN124,GEN183,GEN193,GEN211,GEN219
```

Resultado salvo em:

`evaluation/agent/results/generalization_exhaustion_20260522T182157.json`

Resumo:

| Status | Count |
| --- | ---: |
| passed | 10 |

O resultado agregado foi 10/10 na amostra executada.

### 4.1 Casos respondidos com SQL

| ID | Pergunta | Resultado |
| --- | --- | --- |
| GEN001 | Quantas internações foram registradas em 2018? | Passou; retornou 11.857.648. |
| GEN020 | Evolução mensal de internações por covid em 2021 | Passou; gerou série mensal. |
| GEN037 | Hospitais com maior mortalidade em 2020 com mínimo 1000 internações | Passou; ranking com taxa. |
| GEN057 | Capítulos CID com mais internações em 2018 | Passou; join `DIAG_PRINC -> cid`. |
| GEN079 | Municípios de residência com mais internações em MA em 2020 | Passou; ranking municipal. |
| GEN124 | Custo médio de internação por covid em 2021 | Passou; usou `VAL_TOT`. |
| GEN183 | UFs com maior leitos SUS por 1000 habitantes em 2021 | Passou; usou socioeconômico. |
| GEN193 | Taxa de internações por 100 mil habitantes por UF em 2019 | Passou; combinou internações + população. |

### 4.2 Casos de recusa segura

| ID | Pergunta | Resultado |
| --- | --- | --- |
| GEN211 | Antibióticos mais frequentes em internações por pneumonia | Passou com recusa segura: medicamentos não estão no schema. |
| GEN219 | Exames laboratoriais mais frequentes em internações por pneumonia | Passou com recusa segura: exames laboratoriais não estão no schema. |

Esses dois casos são importantes. Um chatbot Text-to-SQL bom não deve inventar tabelas de medicamentos, exames, vacinação ou prontuário quando o banco não possui esses dados. Aqui o agente se comportou corretamente.

### 4.3 Latência observada

Latências por item:

- GEN001: 22,83 s
- GEN020: 25,97 s
- GEN037: 15,33 s
- GEN057: 14,75 s
- GEN079: 13,64 s
- GEN124: 13,92 s
- GEN183: 15,97 s
- GEN193: 18,43 s
- GEN211: 0,67 s
- GEN219: 0,50 s

Média: ~14,2 s
Mediana: ~15,0 s

Interpretação:

- Para análise pesada em banco grande, 14-26 s é aceitável em modo analítico.
- Para chatbot interativo, ainda é alto. O produto precisa de streaming de status, cache, respostas parciais ou UX de “analisando...”.
- Recusas seguras rápidas são um bom sinal.

## 5. Qualidade Text-to-SQL

### O que está bom

1. SQL simples factual funciona.
   - Exemplo GEN001:

```sql
SELECT COUNT(*) AS total_internacoes
FROM internacoes
WHERE EXTRACT(YEAR FROM "DT_INTER") = 2018;
```

2. O agente lida com séries temporais.
   - GEN020 gerou agrupamento mensal.

3. O agente lida com rankings com filtros mínimos.
   - GEN037 usou `COUNT`, óbitos e taxa com mínimo de 1000 internações.

4. O agente usa tabelas de dimensão quando necessário.
   - GEN057 usou `cid`.
   - GEN079 usou `municipios`.
   - GEN183 usou `socioeconomico` + `municipios`.

5. O agente consegue combinar fatos com denominadores socioeconômicos.
   - GEN193 calculou taxa por 100 mil habitantes usando internações e população.

6. O agente recusa perguntas fora do schema.
   - Medicamentos e exames laboratoriais foram recusados corretamente.

### O que preocupa

1. Covid foi resolvido como `DIAG_PRINC IN ('B342', 'B972')`.
   - Isso pode estar correto conforme regra interna, mas precisa estar documentado como conceito clínico versionado.
   - Para generalizar doenças, o agente precisa de uma camada explícita de conceitos CID, não só heurísticas.

2. Perguntas por município de residência usam join com `MUNIC_RES -> municipios.CO_MUNICIPIO_6D`.
   - A documentação `join_policy.csv` marcou essa relação como `left_join_or_explicit_mapped_scope_required`, não como join incondicional perfeito.
   - O agente respondeu com `JOIN`, não `LEFT JOIN`, e não destacou caveat de cobertura. Isso é um risco semântico.

3. Perguntas por UF dependem de `municipios.SG_UF`, e a documentação gerada indicou problemas de qualidade de UF.
   - O agente precisa carregar essas ressalvas automaticamente.

4. Algumas queries passam no judge, mas ainda podem estar semanticamente incompletas se caveats não forem exigidos pelo avaliador.

5. A camada CID está instável nos testes unitários atuais.

## 6. Testes e CI

### 6.1 Pytest

Comando executado:

```bash
uv run pytest -q --ignore=tests/test_agent_improvements.py
```

Resultado: falhou com 6 testes.

Falhas observadas:

1. `tests/test_api_database_explorer.py::test_process_query_validates_and_applies_table_context`
   - Erro: `KeyError: 'query'`
   - Interpretação: contrato da API ou payload interno mudou e o teste não acompanha.

2. `tests/test_semantic_layer.py::test_semantic_plan_detects_death_cause_cid_antijoin`
   - Esperava dimensão `diagnostico`, mas o plano veio como `single_scalar` sem dimensões.

3. `tests/test_semantic_layer.py::test_semantic_validator_rejects_cid_morte_for_general_death_cause_antijoin`
   - O erro retornado foi de shape escalar/GROUP BY, não da regra semântica esperada de `DIAG_PRINC`.

4. `tests/test_semantic_layer.py::test_semantic_validator_rejects_unbounded_death_cause_antijoin_list`
   - Esperava rejeição, mas `valid` veio `True`.

5. `tests/test_semantic_layer.py::test_semantic_plan_treats_counted_catalog_entity_as_scalar_not_grouping`
   - `counted_entity` esperado `diagnostico`; veio `None`.

6. `tests/test_semantic_validators.py::test_semantic_validator_accepts_cid_chapter_dimension_from_lookup_label`
   - Esperava aceitar SQL com `DS_CAPITULO`, mas validou como falso.

Além disso, a suíte completa sem ignore quebra na coleta por causa de `tests/test_agent_improvements.py`, que executa `sys.exit()` no import.

Conclusão: a camada semântica CID/catalog está em regressão. Isso é incompatível com a meta de “qualquer pergunta sobre o banco”, porque CID é um eixo central do domínio.

### 6.2 Ruff

Comando executado:

```bash
uv run ruff check src/ --statistics
```

Resultado observado:

| Código | Count | Significado |
| --- | ---: | --- |
| UP006 | 81 | `typing.List/Dict` legados; usar tipos PEP585. |
| UP035 | 26 | imports deprecated. |
| UP045 | 23 | Optional antigo; usar `X | None`. |
| I001 | 11 | imports desordenados. |
| F401 | 8 | imports não usados. |
| F841 | 1 | variável não usada. |
| UP037 | 1 | quoted annotation. |

Total: 151 erros, 126 corrigíveis com `--fix`.

Conclusão: lint não é o maior problema lógico, mas bloqueia CI e reduz disciplina de engenharia.

## 7. Documentação do banco como ativo estratégico

A documentação em `docs/generated` é um diferencial forte do projeto. Ela inclui:

- inventário de tabelas;
- catálogo de colunas;
- chaves candidatas;
- constraints;
- política de joins;
- perfis de colunas;
- valores frequentes;
- checks de qualidade;
- auditoria semântica do ground truth.

Para um agente Text-to-SQL, isso é ouro. O ponto principal: esses arquivos não devem ser apenas documentação. Eles devem virar parte ativa do planejamento e validação.

Regras críticas derivadas da documentação:

1. `internacoes` é a fato principal.
2. `internacao_procedimento` se conecta a `internacoes` por `N_AIH`.
3. `DIAG_PRINC -> cid.CID` é join confiável.
4. `CID_MORTE -> cid.CID` e `DIAG_SECUN -> cid.CID` são `audit_only` ou exigem caveat.
5. `MUNIC_RES -> municipios.CO_MUNICIPIO_6D` exige `LEFT JOIN` ou escopo explícito.
6. `hospital.MUNIC_MOV -> municipios.CO_MUNICIPIO_6D` é seguro para município do hospital/movimento.
7. `RACA_COR`, `ETNIA`, `INSTRU`, `VINCPREV`, `CBOR` têm baixa cobertura de dimensão e exigem caveats.
8. `DIAS_PERM` deve ser preferido à recomputação simples por datas, porque há divergência massiva em DQ.
9. Perguntas por UF precisam validar códigos inválidos ou normalizar `SG_UF`.
10. O agente deve saber recusar dados inexistentes: medicamentos, exames laboratoriais, vacinação etc.

## 8. Avaliação da meta “generalizar qualquer pergunta sobre o banco”

A meta precisa ser refinada. Nenhum chatbot Text-to-SQL deve prometer “qualquer pergunta” literalmente. A formulação correta para produto seria:

> Responder, com SQL validado e caveats explícitos, a perguntas analíticas sobre entidades, métricas, dimensões e períodos cobertos pelo banco; recusar ou pedir esclarecimento quando a pergunta exigir dados ausentes, granularidade inexistente ou definição ambígua.

Com essa definição, o projeto está em bom caminho.

### O que o agente já generaliza bem

- Contagens por ano.
- Séries temporais mensal/anual.
- Rankings por hospital, município, UF, CID e procedimento.
- Taxas simples com denominador interno.
- Métricas financeiras básicas (`VAL_TOT`, UTI etc.).
- Indicadores socioeconômicos disponíveis.
- Safe refusal para domínios ausentes.

### Onde a generalização ainda é frágil

- Conceitos clínicos abertos: “doenças cardiovasculares”, “hipertensão”, “neoplasias”, “pneumonia” etc. precisam de ontologia CID versionada.
- Geografia: residência vs atendimento/hospital precisa ser explicitamente resolvido.
- UF e município têm caveats de qualidade.
- CID de causa de morte vs diagnóstico principal ainda está instável.
- Perguntas correlacionais/causais precisam guardrails de linguagem: associação ≠ causalidade.
- Perguntas com denominadores populacionais precisam garantir ano e nível geográfico compatível.
- Perguntas de visualização/chart parecem em trabalho ativo e não estão estabilizadas.

## 9. Nota detalhada

### 9.1 Arquitetura agentic: 7.8/10

Justificativa:

- Uso correto de LangGraph para workflow multi-etapas.
- Estado rico e auditável.
- Ferramentas reais e telemetria.
- Planejamento semântico explícito.
- Validação e execução reais.

Descontos:

- Complexidade concentrada em arquivos gigantes.
- Regras semânticas misturadas com heurísticas/macro logic.
- Falhas atuais em testes de semântica.
- Multi-query aparentemente desabilitado por padrão (`force_single_query`), o que reduz capacidade agentic em perguntas compostas.

### 9.2 Chatbot UX: 6.2/10

Justificativa:

- Respostas finais são compreensíveis.
- Recusas são úteis.
- Mas ainda falta experiência conversacional madura.

Melhorias necessárias:

- Perguntar esclarecimento quando houver ambiguidade entre município de residência vs município do hospital.
- Mostrar caveats em linguagem natural.
- Explicar fonte/escopo da métrica.
- Suportar follow-up: “e em 2022?”, “agora por sexo”, “mostre gráfico”.
- Oferecer streaming/progresso para queries de 15-25 s.
- Separar resposta curta de detalhes técnicos expandíveis.

### 9.3 Text-to-SQL: 7.4/10

Justificativa:

- Boa execução em amostra real de 10 casos.
- Uso correto de joins e agregações em muitos casos.
- Recusa correta quando o dado não existe.

Descontos:

- Caveats de join policy nem sempre aparecem na resposta.
- CID e catálogo estão instáveis nos testes.
- Conceitos clínicos precisam de ontologia explícita.
- Falta prova de robustez em uma suíte grande e limpa nesta branch.

### 9.4 Observabilidade e avaliação: 7.6/10

Justificativa:

- Metadata rica por execução.
- Latência por componente.
- Tool calls registradas.
- Runner de generalização com famílias anti-overfit.
- Ground truth e auditoria semântica existem.

Descontos:

- O relatório `.md` do exhaustion runner é superficial; o JSON é rico, mas o sumário humano não mostra SQL, latência, caveats, falhas de semântica.
- Faltam thresholds contínuos: “não mergear se generalization score < X”.
- Falta dashboard ou matriz por domínio: temporal, geografia, CID, socioeconômico, custos, qualidade de dados, out-of-schema.

### 9.5 Prontidão para produção: 5.8/10

Justificativa:

- O agente funciona em vários casos reais.
- Mas branch atual não está estável.
- Pytest e ruff falham.
- Há mudanças não commitadas e regressões semânticas.

Para produção, eu exigiria:

1. `uv run pytest` verde.
2. `uv run ruff check src/` verde.
3. Score mínimo em benchmark grande.
4. Safe refusals testados.
5. Políticas de custo/timeout.
6. Logs e traces acessíveis.
7. Contratos de API congelados.

## 10. Riscos prioritários

### Risco 1: Semântica CID instável

CID é eixo central para perguntas de saúde. As falhas atuais mostram problemas em:

- catálogo CID;
- capítulo CID;
- causa de morte;
- diferença entre `DIAG_PRINC`, `DIAG_SECUN` e `CID_MORTE`;
- counted entity de diagnóstico.

Prioridade: máxima.

### Risco 2: Joins com caveat tratados como joins normais

Exemplo: município de residência.

Se o agente usa `JOIN` sem caveat em relação com cobertura imperfeita, ele pode perder registros silenciosamente e apresentar resultado como total completo.

Prioridade: alta.

### Risco 3: Arquivos gigantes impedem evolução segura

`semantic/planner.py` e `agent/sql_generation.py` estão grandes demais. Isso aumenta risco de regressão a cada ajuste.

Prioridade: alta.

### Risco 4: “Qualquer pergunta” vira promessa perigosa

O agente precisa recusar bem e pedir clarificação. Se tentar responder tudo, vai alucinar schema ou usar proxy errado.

Prioridade: alta.

### Risco 5: Latência de chatbot

15-26 segundos é aceitável para análise, mas ruim para chat sem feedback.

Prioridade: média.

## 11. Arquitetura recomendada para chegar em 8.5+/10

### 11.1 Separar em camadas mais explícitas

Proposta:

1. `Domain Intent Layer`
   - Classifica tarefa: contagem, ranking, série temporal, taxa, comparação, qualidade de dados, out-of-schema.

2. `Semantic Contract Layer`
   - Usa `docs/generated` como fonte ativa.
   - Resolve entidades, métricas, dimensões, joins permitidos, caveats e recusas.

3. `Concept Resolver`
   - Resolve conceitos clínicos para CID/procedimentos.
   - Exemplo: covid, pneumonia, dengue, diabetes, neoplasias.
   - Deve ser versionado, testável e auditável.

4. `SQL Compiler`
   - Compila plano semântico para SQL.
   - Deve ser mais determinístico para padrões comuns.
   - LLM deve preencher lacunas, não reinventar regras.

5. `SQL Validator`
   - Valida syntax, schema, join policy, grain, caveats obrigatórios e custo estimado.

6. `Executor`
   - Executa com timeout, limit, read-only, query budget.

7. `Result Validator`
   - Checa shape, nulls, row count, denominador, warnings.

8. `Answer Composer`
   - Resposta curta + caveats + SQL opcional.

9. `Conversation Manager`
   - Follow-ups, contexto ativo, clarificação, memória de sessão.

### 11.2 Tornar `docs/generated` executável

Criar loaders internos para:

- `join_policy.csv`
- `candidate_keys.csv`
- `data_quality_checks.json`
- `ground_truth_semantic_audit.csv`
- `column_catalog.csv`
- `top_frequent_values.csv`

Esses loaders deveriam alimentar:

- seleção de tabelas;
- validação de joins;
- geração de caveats;
- detecção de perguntas impossíveis;
- auditoria de resposta.

### 11.3 Criar matriz de benchmark por domínio

Domínios mínimos:

1. Básico: count/list/ranking.
2. Temporal: ano, mês, crescimento, variação percentual.
3. Geografia: UF, município de residência, município do hospital, região de saúde.
4. CID: diagnóstico principal, capítulo, categoria, causa de morte com caveat.
5. Procedimentos: ranking, UF, condição clínica.
6. Custos: total, médio, por dia, UTI.
7. Socioeconômico: população, PIB, leitos, médicos, taxas por habitante.
8. Qualidade de dados: nulls, joins ausentes, datas inválidas.
9. Out-of-schema: medicamentos, exames, vacinação, prontuário individual.
10. Ambíguas: perguntas que exigem clarificação.

Cada domínio deve ter:

- perguntas fáceis, médias e difíceis;
- expected SQL ou expected result;
- expected caveats;
- expected refusal quando aplicável;
- latência máxima aceitável;
- custo máximo aceitável.

### 11.4 Melhorar chatbot UX

Formato recomendado de resposta:

```text
Resposta curta:
Em 2018 foram registradas 11.857.648 internações.

Escopo:
- Tabela: internacoes
- Data usada: DT_INTER
- Filtro: ano de internação = 2018

Observações:
- Resultado calculado no banco SIHRD5.

SQL usado:
[expandível]
```

Para caveats:

```text
Atenção: usei município de residência (`MUNIC_RES`). A documentação indica que esse mapeamento tem cobertura imperfeita; portanto o resultado considera apenas registros com município mapeado.
```

Para ambiguidade:

```text
Você quer município de residência do paciente ou município do hospital onde ocorreu a internação?
```

## 12. Roadmap recomendado

### Fase 1 — Estabilização obrigatória

1. Corrigir `tests/test_agent_improvements.py` para não executar `sys.exit()` no import.
2. Corrigir os 6 testes falhando.
3. Rodar `uv run ruff check src/ --fix` e revisar diff.
4. Garantir `uv run pytest` e `uv run ruff check src/` verdes.
5. Congelar baseline de avaliação atual.

### Fase 2 — Guardrails semânticos

1. Transformar `join_policy.csv` em validador ativo.
2. Exigir caveats para joins `left_join_or_explicit_mapped_scope_required`.
3. Bloquear ou exigir caveat para relações `audit_only`.
4. Corrigir CID: `DIAG_PRINC`, `DIAG_SECUN`, `CID_MORTE`, capítulo, catálogo e causa de morte.
5. Criar testes para cada regra de join policy.

### Fase 3 — Generalização real

1. Versionar ontologia de conceitos clínicos.
2. Expandir exhaustion benchmark para 200+ perguntas versionadas.
3. Medir score por família, não só global.
4. Adicionar testes de perguntas ambíguas e out-of-schema.
5. Criar regressão automática para top 30 perguntas críticas.

### Fase 4 — Produto/chatbot

1. Implementar follow-up contextual.
2. Adicionar clarificação antes de SQL quando necessário.
3. Melhorar resposta com escopo/caveats/SQL opcional.
4. Adicionar streaming de progresso.
5. Criar histórico de conversa e reuso de contexto.

### Fase 5 — Otimização

1. Cachear schema/retrieval com invalidação.
2. Reduzir chamadas LLM em casos determinísticos.
3. Pré-compilar templates SQL para padrões comuns.
4. Adicionar query budget e timeout por classe de pergunta.
5. Monitorar custo/latência por endpoint.

## 13. Veredito final

O projeto está em um ponto muito promissor. Eu daria **7.0/10 no estado atual**.

Por que não menos?

- Ele realmente consulta o banco.
- Tem arquitetura agentic apropriada.
- Tem documentação de banco forte.
- Tem avaliação e testes de generalização.
- Acertou 10/10 na amostra de limite executada, incluindo recusas seguras.

Por que não mais?

- A branch está quebrada em testes e lint.
- CID está instável, e CID é central para saúde.
- Caveats semânticos ainda não aparecem de forma consistente.
- A promessa “qualquer pergunta” ainda precisa ser restringida por schema, semântica e clarificação.
- A experiência de chatbot ainda não está no nível de produto final.

Minha recomendação: tratar o projeto como **núcleo agentic TXT2SQL forte, mas ainda em fase beta técnica**. O próximo ganho não virá de adicionar mais agentes; virá de estabilizar semântica, transformar `docs/generated` em contratos executáveis, corrigir CI e amadurecer UX conversacional.
