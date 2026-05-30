# Plano profundo de refatoracao do chatbot Text-to-SQL

Data: 2026-05-29

Responsavel: AI Engineering

Status: proposto

Escopo: agente LangGraph/Text-to-SQL para responder perguntas analiticas sobre o
banco DuckDB SIH-RD/DataSUS configurado no projeto.

## 1. Objetivo

O objetivo desta refatoracao e simplificar o projeto sem reduzir a capacidade do
chatbot de responder perguntas gerais sobre o banco. A direcao correta nao e
remover regras de dominio indiscriminadamente, mas reduzir os pontos onde a
mesma decisao e tomada varias vezes.

O agente deve continuar capaz de:

- Identificar se a pergunta e respondida pelo schema disponivel.
- Selecionar as tabelas e joins corretos para perguntas sobre internacoes,
  mortalidade, diagnosticos, procedimentos, hospitais, municipios e indicadores
  socioeconomicos.
- Gerar SQL DuckDB seguro, somente leitura, com limites e sem consultas
  destrutivas.
- Explicar limites do dado quando a pergunta pede algo fora do schema.
- Responder de forma generalizavel, sem depender de dezenas de casos especiais
  espalhados por prompts, validadores e macros SQL.

O resultado esperado e um runtime mais curto, mais previsivel e mais facil de
testar:

```text
pergunta
  -> roteador leve
  -> recuperacao de contexto do schema
  -> plano semantico unico
  -> compilador SQL por familia de pergunta
  -> validacao de invariantes
  -> execucao read-only
  -> resposta deterministica/leve
```

## 2. Principio de simplificacao

Simplificar este projeto significa remover duplicidade de responsabilidade.
Hoje o mesmo conhecimento aparece em varios lugares:

- prompts de selecao de tabela;
- descricoes manuais de tabelas;
- templates longos de schema;
- `semantic/catalog.yml`;
- `src/semantic/planner.py`;
- macros deterministicas em `src/agent/sql_generation.py`;
- validadores hardcoded em `src/agent/validation.py`;
- respostas especiais em `src/agent/response.py`;
- plano multi-query e passos extras do grafo.

A refatoracao deve convergir para uma fonte canonica de semantica, usada pelos
demais componentes. Camadas posteriores devem validar e executar uma decisao, e
nao reinventar a decisao.

## 3. Fatos do banco analisado

### 3.1 Banco e runtime

O `.env` aponta para:

```text
duckdb:///C:/Users/Kevyn/Projects/databases/datasus/sihrd5.duckdb/sihrd5.duckdb?access_mode=read_only
```

O banco existe localmente e foi aberto em modo read-only. O arquivo tem cerca de
25 GiB. Os artefatos gerados em `src/application/schema/generated` indicam que
o metadata runtime foi gerado em 2026-05-13, com limite de memoria em torno de
12.4 GiB e acesso read-only.

### 3.2 Tabelas principais

Tabelas com maior impacto analitico:

| Tabela | Papel | Volume aproximado |
| --- | --- | ---: |
| `internacoes` | fato principal de internacoes hospitalares | 183,877,219 linhas |
| `internacao_procedimento` | fato de procedimentos por AIH | 187,957,888 linhas |
| `socioeconomico` | indicadores municipais/anuais | 72,395 linhas |
| `cid` | dimensao de CID/diagnostico | 14,253 linhas |
| `hospital` | dimensao de hospital/CNES | 6,873 linhas |
| `tempo` | dimensao calendario | 6,210 linhas |
| `municipios` | dimensao territorial | 5,589 linhas |
| `procedimentos` | dimensao de procedimento SIGTAP | 5,394 linhas |

Tabelas menores funcionam como dimensoes/codigos: `sexo`, `raca_cor`,
`complexidade`, `especialidade`, `car_int`, `marca_uti`, `cbor`,
`nacionalidade`, `etnia`, `instrucao`, `vincprev`, `contraceptivos`.

### 3.3 Cobertura temporal e metricas basicas

Consultas diretas no DuckDB confirmaram:

| Metrica | Valor |
| --- | ---: |
| Total de internacoes | 183,877,219 |
| Total de mortes (`MORTE = true`) | 7,907,788 |
| Primeira `DT_INTER` | 2000-01-01 |
| Ultima `DT_INTER` | 2023-12-31 |
| Hospitais distintos | 6,873 |
| Municipios de residencia distintos | 5,588 |
| Diagnosticos principais distintos | 11,830 |

Os checks de qualidade indicam 27 registros com `DT_INTER` fora de 2007-2023.
Na pratica, o chatbot deve considerar que a serie operacional cobre 2007-2023,
mas validadores e respostas nao devem quebrar se aparecerem residuos historicos
de 2000-2001 em consultas globais.

### 3.4 Regras semanticas essenciais

Estas regras devem permanecer como contrato do agente:

- `internacoes` e a tabela fato padrao para contagens de internacoes,
  mortalidade, diagnosticos, idade, sexo, raca/cor, municipio de residencia,
  hospital e valores pagos.
- `N_AIH` identifica a AIH. Em contagens de internacao, usar `COUNT(*)` sobre
  `internacoes`, salvo pergunta explicita sobre procedimentos.
- `MORTE` e booleano e deve ser usado para obitos/mortalidade hospitalar.
- `DIAG_PRINC` e o diagnostico padrao para perguntas sobre CID, causa,
  doenca ou diagnostico. `CID_MORTE`, `DIAG_SECUN` e diagnosticos secundarios
  nao devem ser usados sem pedido explicito.
- `DIAS_PERM` deve ser usado para permanencia. Nao recomputar duracao com
  `date_diff` como default, porque os checks mostram divergencia grande entre
  a coluna de negocio e a diferenca calendario.
- `DT_INTER` e a data padrao para analises temporais de internacao. `DT_SAIDA`
  so deve ser usada quando a pergunta falar de alta/saida.
- `MUNIC_RES` representa municipio de residencia do paciente.
- Localizacao do hospital exige `internacoes.CNES -> hospital.CNES` e, quando
  precisar de nome/codigo municipal, `hospital.MUNIC_MOV -> municipios.CO_MUNICIPIO_6D`.
- `internacoes.SEXO` observado na fato usa codigos `1` e `3`. A dimensao
  `sexo` tambem contem `2`, entao filtros devem se basear no perfil da fato e
  nao apenas na tabela de lookup.
- `internacoes.RACA_COR` contem valor `99` em volume relevante. Joins com
  `raca_cor` nao devem descartar desconhecidos silenciosamente.
- `internacao_procedimento` deve ser usada quando a pergunta for sobre
  procedimento realizado, quantidade de procedimentos, valor por procedimento
  ou relacionamento AIH-procedimento.
- `socioeconomico` usa grao municipio/ano. Perguntas socioeconomicas devem
  fazer join com `municipios` por `CO_MUNICIPIO_6D`.
- Perguntas de grafico devem ser pos-processamento do resultado tabular. O SQL
  nao deve mudar so porque o usuario pediu grafico, salvo necessidade de serie
  ou agrupamento.

### 3.5 Politica de joins baseada nos perfis gerados

Joins seguros por default:

| Origem | Destino | Politica |
| --- | --- | --- |
| `internacoes.CNES` | `hospital.CNES` | confirmado, inner join permitido |
| `hospital.MUNIC_MOV` | `municipios.CO_MUNICIPIO_6D` | confirmado, inner join permitido |
| `internacoes.SEXO` | `sexo.SEXO` | confirmado |
| `internacoes.DIAG_PRINC` | `cid.CID` | confirmado |
| `internacao_procedimento.N_AIH` | `internacoes.N_AIH` | confirmado |
| `internacao_procedimento.PROC_REA` | `procedimentos.PROC_REA` | confirmado |
| `socioeconomico.CO_MUNICIPIO_6D` | `municipios.CO_MUNICIPIO_6D` | confirmado |

Joins que exigem cuidado:

| Origem | Destino | Motivo |
| --- | --- | --- |
| `internacoes.MUNIC_RES` | `municipios.CO_MUNICIPIO_6D` | cobertura alta, mas deve preferir left join ou escopo explicito |
| `internacoes.RACA_COR` | `raca_cor.RACA_COR` | valor `99` nao mapeado; nao usar inner join por default |
| `internacoes.ETNIA`, `INSTRU`, `VINCPREV`, `CBOR` | lookups | cobertura baixa; usar apenas com regra explicita |
| `internacoes.CID_MORTE`, `DIAG_SECUN` | `cid.CID` | nao sao default para diagnostico |

## 4. Como o chatbot deve responder perguntas

### 4.1 Familias suportadas por default

O chatbot deve reconhecer e responder estas familias:

| Familia | Exemplos | Tabelas principais | Estrategia |
| --- | --- | --- | --- |
| Contagem simples | "quantas internacoes em 2020?" | `internacoes` | `COUNT(*)` com filtros |
| Mortalidade | "taxa de mortalidade por sexo" | `internacoes`, `sexo` | numerador `MORTE`, denominador internacoes |
| Diagnostico/CID | "internacoes por pneumonia" | `internacoes`, `cid` | filtrar `DIAG_PRINC` ou prefixos CID resolvidos |
| Ranking | "top 10 municipios por obitos" | `internacoes`, `municipios` | agrupamento + order + limit |
| Tendencia temporal | "evolucao anual de internacoes" | `internacoes` | `date_part` ou `date_trunc` sobre `DT_INTER` |
| Permanencia | "media de dias de permanencia" | `internacoes` | usar `DIAS_PERM` |
| Valor | "valor total por hospital" | `internacoes`, `hospital` | soma de `VAL_TOT`, `VAL_SH`, `VAL_SP`, `VAL_UTI` |
| UTI | "internacoes com UTI" | `internacoes` | usar campos UTI/valor UTI conforme intencao |
| Procedimentos | "procedimentos mais comuns" | `internacao_procedimento`, `procedimentos` | fato de procedimento |
| Socioeconomico | "PIB per capita por municipio" | `socioeconomico`, `municipios` | grao municipio/ano |
| Catalogo | "o que significa CID J189?" | `cid` | lookup sem fato se pergunta for definicional |

### 4.2 Perguntas que devem virar recusa ou esclarecimento

O agente deve recusar ou pedir esclarecimento quando a pergunta exigir dado fora
do schema. Exemplos:

- exames laboratoriais, hemograma, glicemia, imagem ou sinais vitais;
- medicamento administrado, prescricao ou dose;
- reinternacao real do mesmo paciente se nao houver identificador longitudinal
  confiavel;
- bairro, endereco completo ou unidade intra-municipal ausente;
- renda individual, escolaridade individual detalhada fora dos codigos
  disponiveis;
- acompanhamento ambulatorial, consulta fora de internacao ou desfecho depois da
  alta;
- causa clinica nao representada por CID/procedimento no banco.

O comportamento correto e explicar o limite do banco e, quando possivel, sugerir
uma pergunta equivalente suportada. Exemplo: para "hemograma por pneumonia",
responder que o banco nao contem exames laboratoriais, mas pode responder
internacoes por pneumonia, mortalidade ou permanencia.

### 4.3 Ambiguidade que merece pergunta de follow-up

Nem toda ambiguidade deve gerar recusa. O agente deve perguntar ou assumir com
transparencia quando:

- "municipio" pode significar residencia do paciente ou local do hospital;
- "causa de morte" pode significar `DIAG_PRINC` em internacoes com morte ou
  `CID_MORTE` explicitamente;
- "por idade" pode exigir faixa etaria ou idade exata;
- "comparar anos" sem anos especificos pode usar periodo disponivel, mas deve
  informar o criterio;
- "maior" pode significar maior contagem, maior taxa ou maior valor.

Regra pratica: assumir defaults documentados quando o risco e baixo; pedir
esclarecimento quando duas interpretacoes produzem respostas substancialmente
diferentes.

## 5. Problemas atuais de arquitetura

### 5.1 Grafo com etapas redundantes

O grafo atual ja foi parcialmente simplificado pela remocao do no
`intent_planning`, que duplicava classificacao e planejamento semantico. Ainda
existem outros passos com potencial de simplificacao:

- `plan_gate` construi parte do plano semantico e tambem faz roteamento.
- `semantic_planner` tambem interpreta pergunta e popula `semantic_plan`.
- `query_planner` so e necessario para casos multi-query, mas permanece no
  fluxo como capacidade geral.
- `reasoning_node` adiciona custo/latencia e pode encorajar raciocinio textual
  que nao vira contrato verificavel.
- validacao e reparo podem reescrever a decisao em vez de bloquear invariantes.

### 5.2 Conhecimento de schema duplicado

Arquivos observados com sobreposicao de responsabilidade:

- `src/application/config/table_descriptions.py`
- `src/application/config/table_templates.py`
- `src/application/prompts/*`
- `src/application/schema/generated/*`
- `src/semantic/catalog.yml`
- `src/semantic/planner.py`
- `src/agent/schema_node.py`
- `src/agent/table_selection.py`
- `src/agent/sql_generation.py`
- `src/agent/validation.py`

Sintomas:

- regras repetidas ficam inconsistentes;
- numeros de documentacao podem ficar obsoletos;
- o LLM recebe contexto longo e heterogeneo;
- testes precisam cobrir comportamento emergente de varias camadas, nao uma
  decisao clara;
- adicionar nova regra exige alterar multiplos pontos.

### 5.3 Gerador SQL monolitico

`src/agent/sql_generation.py` concentra muitas responsabilidades:

- heuristicas de pergunta;
- macros deterministicas;
- selecao de estrategia;
- prompt LLM;
- fallback;
- regras de grafico;
- logica analitica especial;
- remendos de SQL.

Esse desenho aumenta o custo de mudanca. O objetivo nao deve ser transformar
tudo em LLM nem tudo em regex. O objetivo e separar:

1. resolucao semantica;
2. escolha de estrategia;
3. compilacao SQL;
4. fallback LLM;
5. validacao.

### 5.4 Planner semantico grande demais

`src/semantic/planner.py` ja e a direcao correta porque cria uma representacao
intermediaria. O problema e que o arquivo ficou grande e com muitos padroes
inline. Isso torna dificil saber se uma nova regra e:

- regra de metrica;
- sinonimo de dimensao;
- filtro temporal;
- conceito clinico;
- regra de recusa;
- regra de resposta;
- tratamento de benchmark.

O plano e preservar a interface publica do planner e quebrar internamente em
resolvers pequenos.

### 5.5 Validacao como segunda inteligencia

`src/agent/validation.py` mistura:

- checagem de SQL read-only;
- validacao de schema;
- validacao por LLM;
- validacao contra plano semantico;
- regras legadas com mensagens de "FIX EXACTLY";
- validacao de grafico;
- decisoes sobre reparo.

O validador deve ser guardrail, nao outro planejador. Ele deve bloquear apenas
invariantes confiaveis e devolver warnings quando a decisao for debatida mas nao
claramente incorreta.

### 5.6 Resposta final com LLM onde nao precisa

Para resultados tabulares simples, o agente consegue responder de forma
deterministica:

- valor unico;
- serie temporal;
- ranking;
- distribuicao;
- taxa com numerador/denominador;
- lookup de catalogo.

LLM na resposta final deve ser reservado para explicacao curta, limites do dado
e perguntas conversacionais. Quanto mais o resultado numerico passar por LLM,
maior o risco de alucinacao de texto ou interpretacao.

## 6. Arquitetura alvo

### 6.1 Fluxo alvo

```text
UserQuestion
  -> classify_question()
  -> retrieve_schema_context()
  -> build_semantic_plan()
  -> choose_sql_strategy()
  -> compile_sql()
  -> validate_sql()
  -> execute_sql()
  -> render_answer()
```

O grafo LangGraph pode continuar existindo, mas com menos nos e menos branches
default. A capacidade de ablation deve ser preservada atras de flags, nao como
caminho principal.

### 6.2 Componentes alvo

| Componente | Responsabilidade |
| --- | --- |
| `QuestionRoute` | classificar entre analitica, catalogo, conversa, schema-unavailable, clarificacao |
| `SchemaContext` | contexto minimo de tabelas, colunas, joins e exemplos baseado nos artefatos gerados |
| `SemanticPlan` | contrato unico: metrica, grao, filtros, joins, periodo, shape de resposta |
| `SQLStrategyRouter` | escolher compilador deterministico ou fallback LLM |
| `SQLCompiler` | compilar SQL para uma familia especifica |
| `SQLValidator` | bloquear somente violacoes confiaveis |
| `AnswerRenderer` | formatar resultado sem alterar numeros |

### 6.3 Contrato do `SemanticPlan`

O plano semantico deve ser suficiente para responder:

- Qual e a metrica?
- Qual e o denominador, se houver taxa?
- Qual tabela fato e usada?
- Qual data e usada?
- Quais filtros foram inferidos?
- Quais joins sao necessarios?
- Qual e o grao de agregacao?
- A resposta e escalar, ranking, serie temporal, distribuicao, lookup ou recusa?
- Quais assumptions devem aparecer na resposta?
- Quais invariantes precisam ser validadas?

Exemplo conceitual:

```yaml
question: "taxa de mortalidade por sexo em 2020"
answer_shape: grouped_rate
fact_table: internacoes
metric:
  name: mortality_rate
  numerator: count_where(MORTE = true)
  denominator: count(*)
dimensions:
  - table: sexo
    key: internacoes.SEXO
    label: sexo.DESCRICAO
filters:
  - column: internacoes.DT_INTER
    operator: year_equals
    value: 2020
joins:
  - internacoes.SEXO = sexo.SEXO
assumptions:
  - "Data padrao: DT_INTER."
invariants:
  - read_only_sql
  - no_inner_join_on_raca_cor_unknown
  - mortality_rate_has_denominator
```

### 6.4 Fontes canonicas

Manter estas fontes como canonicas:

- `src/semantic/catalog.yml`: metricas, dimensoes, sinonimos controlados,
  politicas de join, defaults e indisponibilidades.
- `src/application/schema/generated/*.csv|json`: facts do banco gerados por
  introspeccao, como colunas, perfis, cardinalidades e cobertura de joins.
- testes/evaluations: contratos observaveis de comportamento.

Reduzir ou gerar automaticamente:

- `table_descriptions.py`;
- `table_templates.py`;
- blocos manuais longos de schema em prompts;
- regras duplicadas em `schema_node.py` e `table_selection.py`.

## 7. Plano de refatoracao por fases

### Fase 0 - Baseline e seguranca de mudanca

Objetivo: criar uma linha de base antes de remover mais codigo.

#### Tarefa 0.1 - Registrar estado atual

O que fazer:

- Registrar `git status --short`.
- Registrar versao do Python e dependencias instaladas.
- Confirmar se `uv` esta disponivel; se nao estiver, documentar comandos
  equivalentes com `python -m`.
- Confirmar acesso read-only ao DuckDB.

Arquivos provaveis:

- `docs/generated/`
- `docs/plans/`

Aceite:

- Existe um snapshot simples com branch, arquivos modificados e comandos
  disponiveis.
- Nao ha alteracao destrutiva no banco.

Validacao:

```powershell
git status --short
python --version
python -m pip show duckdb pytest ruff
python - <<'PY'
import duckdb
print(duckdb.__version__)
PY
```

#### Tarefa 0.2 - Criar smoke set representativo

O que fazer:

Criar ou consolidar uma lista pequena de perguntas que cubra as familias
principais:

1. "Quantas internacoes existem no banco?"
2. "Quantos obitos hospitalares ocorreram em 2020?"
3. "Qual a taxa de mortalidade por sexo em 2021?"
4. "Quais os 10 CIDs principais com mais internacoes?"
5. "Qual a media de permanencia por ano?"
6. "Quais municipios de residencia tiveram mais internacoes?"
7. "Quais hospitais tiveram maior valor total pago?"
8. "Quais procedimentos foram mais realizados?"
9. "Qual o PIB per capita por municipio em 2021?"
10. "O banco tem resultado de hemograma?"

Arquivos provaveis:

- `evaluation/regression_set.json`
- `evaluation/agent/`
- `docs/generated/smoke_questions_2026-05-29.md`

Aceite:

- As perguntas cobrem escalar, taxa, ranking, serie, lookup, procedimento,
  socioeconomico e recusa.
- Cada pergunta tem familia esperada e tabelas esperadas.

Validacao:

```powershell
python -m evaluation.runners.run_regression --max-queries 10
```

Se o runner exigir dependencias ou credenciais de LLM, registrar o bloqueio e
rodar pelo menos testes unitarios e consultas SQL diretas.

#### Tarefa 0.3 - Proteger comportamento ja simplificado

O que fazer:

- Manter a remocao do no `intent_planning` do fluxo principal.
- Garantir teste que verifica que o grafo nao contem esse no.

Arquivos provaveis:

- `src/agent/workflow.py`
- `tests/test_intent_workflow_integration.py`

Aceite:

- `intent_planning` nao aparece como no runtime.
- Import legado em `nodes.py` nao reintroduz o comportamento.

Validacao:

```powershell
python -m py_compile src\agent\workflow.py tests\test_intent_workflow_integration.py
python -m pytest tests\test_intent_workflow_integration.py
```

### Fase 1 - Contrato canonico de schema e semantica

Objetivo: eliminar duplicidade de regras e fazer o agente depender de um
contrato unico.

#### Tarefa 1.1 - Criar `SchemaCard`

O que fazer:

- Criar um carregador de schema que leia:
  - `table_inventory.csv`;
  - `column_catalog.csv`;
  - `column_profiles_exact.csv`;
  - `top_frequent_values.csv`;
  - `relationship_coverage.csv`;
  - `join_policy.csv`;
  - `data_quality_checks.json`.
- Expor uma estrutura pequena por tabela:
  - papel da tabela;
  - grao;
  - colunas chave;
  - colunas metricas;
  - cobertura temporal;
  - valores top para codigos;
  - joins permitidos;
  - alertas de qualidade.

Arquivos provaveis:

- `src/application/schema/schema_cards.py`
- `tests/test_schema_cards.py`

Aceite:

- `SchemaCard("internacoes")` retorna volume, data range, chaves e regras de
  join essenciais.
- `SchemaCard("socioeconomico")` retorna grao municipio/ano e indicadores.
- O carregador nao consulta o banco em runtime normal.

Validacao:

```powershell
python -m pytest tests/test_schema_cards.py
```

#### Tarefa 1.2 - Consolidar `semantic/catalog.yml`

O que fazer:

- Mover para o catalogo as regras que hoje estao duplicadas em prompts e
  templates:
  - defaults de data;
  - defaults de diagnostico;
  - politica para `MUNIC_RES` vs municipio do hospital;
  - politica para `RACA_COR = 99`;
  - indisponibilidades de schema;
  - sinonimos de metricas;
  - joins aprovados e joins arriscados.
- Adicionar referencias de evidencia:
  - arquivo de perfil que sustenta a regra;
  - query direta, quando relevante;
  - teste que cobre a regra.

Arquivos provaveis:

- `src/semantic/catalog.yml`
- `src/semantic/catalog_loader.py`
- `tests/test_semantic_catalog_contract.py`

Aceite:

- Toda regra de dominio critica tem identificador estavel.
- Regras usadas em prompts/validadores sao renderizadas a partir do catalogo.
- Nao ha regra critica mantida somente em string solta de prompt.

Validacao:

```powershell
python -m pytest tests/test_semantic_catalog_contract.py tests/test_semantic_layer.py
```

#### Tarefa 1.3 - Deprecar templates manuais longos

O que fazer:

- Substituir blocos longos de `table_templates.py` por renderizacao derivada de
  `SchemaCard` + `semantic/catalog.yml`.
- Manter descricoes curtas apenas quando forem realmente texto humano util.
- Corrigir numeros obsoletos, como contagens antigas de `internacoes`.

Arquivos provaveis:

- `src/application/config/table_templates.py`
- `src/application/config/table_descriptions.py`
- `src/agent/schema_node.py`
- `tests/test_new_schema_contract.py`
- `tests/test_llamaindex_context.py`

Aceite:

- O contexto de schema para `internacoes` cabe em uma pagina curta.
- Numeros de linhas e perfis vem de artefatos gerados.
- Prompts nao duplicam listas extensas de regras.

Validacao:

```powershell
python -m pytest tests/test_new_schema_contract.py tests/test_llamaindex_context.py
```

### Fase 2 - Simplificar roteamento e grafo

Objetivo: reduzir o numero de nos e branches padrao, preservando flags de
ablation.

#### Tarefa 2.1 - Definir rotas minimas

O que fazer:

Substituir a classificacao em camadas por uma rota operacional simples:

- `analytical_query`;
- `catalog_lookup`;
- `schema_question`;
- `clarification_needed`;
- `schema_unavailable`;
- `conversation`.

LLM pode continuar como fallback, mas heuristicas e catalogo devem resolver os
casos obvios.

Arquivos provaveis:

- `src/agent/classification.py`
- `src/agent/plan_gate.py`
- `src/agent/workflow.py`
- `tests/test_routing.py`

Aceite:

- Perguntas unsupported param antes de gerar SQL.
- Perguntas analiticas comuns seguem para `SemanticPlan`.
- Perguntas de catalogo nao passam por gerador SQL analitico complexo.

Validacao:

```powershell
python -m pytest tests/test_routing.py tests/test_semantic_layer.py
```

#### Tarefa 2.2 - Desligar multi-query como default

O que fazer:

- Manter `query_planner` atras de flag explicita.
- Default: uma pergunta analitica deve gerar uma consulta SQL, exceto se a
  resposta realmente exigir verificacao secundaria.
- Transformar multi-query em capacidade opt-in e avaliada separadamente.

Arquivos provaveis:

- `src/agent/workflow.py`
- `src/agent/query_planner.py`
- `src/agent/orchestrator.py`
- `evaluation/runners/run_ablation.py`

Aceite:

- Fluxo default nao chama LLM de multi-query.
- Testes confirmam que perguntas simples nao entram em `query_planner`.
- Capacidade antiga ainda pode ser ativada por ablation flag.

Validacao:

```powershell
python -m pytest tests/test_routing.py tests/test_evaluation_result_matching.py
python -m evaluation.runners.run_ablation --variants V0 --max-queries 6
```

#### Tarefa 2.3 - Remover CoT textual do caminho padrao

O que fazer:

- Transformar `reasoning_node` em no opcional para diagnostico/ablation.
- Fazer o plano semantico carregar a explicacao estrutural necessaria.
- Evitar raciocinio livre que nao seja validado por contrato.

Arquivos provaveis:

- `src/agent/workflow.py`
- `src/agent/sql_generation.py`
- `src/agent/state.py`
- `tests/test_workflow.py` ou teste equivalente

Aceite:

- Nenhuma pergunta comum exige `reasoning_node` para gerar SQL.
- Logs ainda mostram `SemanticPlan` para depuracao.
- Ablation consegue comparar com e sem CoT.

Validacao:

```powershell
python -m pytest tests/test_sql_generation_module_split.py tests/test_routing.py
```

### Fase 3 - Refatorar o planner semantico

Objetivo: preservar comportamento, mas quebrar o arquivo grande em resolvers
coerentes.

#### Tarefa 3.1 - Criar resolvers internos

O que fazer:

Extrair de `src/semantic/planner.py`:

- `metric_resolver.py`: internacoes, obitos, taxa, valor, permanencia,
  procedimento, socioeconomico.
- `dimension_resolver.py`: sexo, raca/cor, idade, municipio, hospital,
  diagnostico, tempo.
- `filter_resolver.py`: anos, periodos, UF, municipio, CID, sexo, idade.
- `clinical_resolver.py`: conceitos clinicos para CID/prefixos.
- `unsupported_resolver.py`: exames, medicamentos, bairro, renda individual,
  readmissao, sinais vitais.
- `shape_resolver.py`: escalar, ranking, serie, distribuicao, lookup, chart.

Arquivos provaveis:

- `src/semantic/planner.py`
- `src/semantic/resolvers/*.py`
- `tests/test_domain_resolvers.py`
- `tests/test_semantic_layer.py`

Aceite:

- `build_semantic_plan(question)` continua sendo a API publica.
- Testes atuais passam sem precisar mudar callers.
- Cada resolver tem responsabilidade clara.

Validacao:

```powershell
python -m pytest tests/test_semantic_layer.py tests/test_domain_resolvers.py
```

#### Tarefa 3.2 - Tipar o `SemanticPlan`

O que fazer:

- Definir modelo Pydantic/dataclass para plano semantico.
- Reduzir dependencia de dicionarios livres.
- Adicionar campos para assumptions e invariants.

Arquivos provaveis:

- `src/semantic/types.py`
- `src/semantic/planner.py`
- `src/agent/state.py`
- `tests/test_semantic_plan_types.py`

Aceite:

- Plano invalido falha cedo em teste.
- Compiladores SQL consomem campos tipados.
- Metadata antiga continua disponivel temporariamente para compatibilidade.

Validacao:

```powershell
python -m pytest tests/test_semantic_plan_types.py tests/test_semantic_layer.py
```

#### Tarefa 3.3 - Isolar regras de benchmark

O que fazer:

- Identificar padroes que existem apenas para passar perguntas especificas de
  benchmark.
- Converter em regras gerais ou remover.
- Quando a regra for necessaria, anexar evidencia de dominio e teste de
  familia.

Arquivos provaveis:

- `src/semantic/resolvers/*`
- `evaluation/ground_truth_*.json`
- `tests/test_generalization_question_loader.py`

Aceite:

- Nenhuma regra depende de ID de pergunta ou frase exata sem justificativa.
- Regressao e generalizacao ficam separadas por manifesto.

Validacao:

```powershell
python -m pytest tests/test_generalization_question_loader.py tests/test_semantic_layer.py
```

### Fase 4 - Refatorar geracao SQL

Objetivo: transformar o gerador SQL em estrategias pequenas e testaveis.

#### Tarefa 4.1 - Criar `SQLStrategyRouter`

O que fazer:

Mapear `SemanticPlan.answer_shape` e `metric.family` para uma estrategia:

- `scalar_count_compiler`;
- `grouped_metric_compiler`;
- `rate_compiler`;
- `time_series_compiler`;
- `ranking_compiler`;
- `catalog_lookup_compiler`;
- `procedure_compiler`;
- `socioeconomic_compiler`;
- `llm_sql_fallback`.

Arquivos provaveis:

- `src/agent/sql_generation.py`
- `src/agent/sql_strategy.py`
- `src/agent/sql_compilers/*.py`
- `tests/test_sql_strategy_router.py`

Aceite:

- Perguntas basicas nao entram no fallback LLM.
- A estrategia escolhida fica registrada em metadata.
- Cada estrategia tem teste unitario com plano semantico sintetico.

Validacao:

```powershell
python -m pytest tests/test_sql_strategy_router.py tests/test_sql_generation_module_split.py
```

#### Tarefa 4.2 - Extrair compiladores deterministas

O que fazer:

Mover macros existentes de `sql_generation.py` para compiladores pequenos.
Prioridade:

1. contagem e soma simples;
2. mortalidade/taxa;
3. agrupamento/ranking;
4. tendencia temporal;
5. lookup CID/procedimento/municipio;
6. procedimento;
7. socioeconomico.

Arquivos provaveis:

- `src/agent/sql_compilers/base.py`
- `src/agent/sql_compilers/internacoes.py`
- `src/agent/sql_compilers/procedures.py`
- `src/agent/sql_compilers/socioeconomic.py`
- `src/agent/sql_compilers/catalog.py`
- `tests/test_sql_compilers_*.py`

Aceite:

- Cada compilador recebe `SemanticPlan` e retorna `CompiledSQL`.
- `CompiledSQL` inclui SQL, parametros se houver, tabelas usadas, joins usados e
  assumptions.
- SQL gerado e DuckDB valido.

Validacao:

```powershell
python -m pytest tests/test_sql_compilers_internacoes.py tests/test_sql_compilers_catalog.py
python -m compileall src\agent -q
```

#### Tarefa 4.3 - Manter fallback LLM pequeno e controlado

O que fazer:

- Fallback LLM so deve receber:
  - pergunta;
  - `SemanticPlan`;
  - schema cards relevantes;
  - politicas de join;
  - exemplos minimos.
- Remover prompt longo com regras duplicadas.
- Validar fortemente SQL produzido por fallback.

Arquivos provaveis:

- `src/agent/sql_generation.py`
- `src/application/prompts/sql_generation/*`
- `tests/test_llm_sql_fallback_prompt.py`

Aceite:

- Prompt fallback nao contem todo o schema.
- Fallback nunca ignora `schema_unavailable`.
- Fallback nao pode usar tabela fora do contexto selecionado sem justificativa.

Validacao:

```powershell
python -m pytest tests/test_llm_sql_fallback_prompt.py tests/test_sql_execution_block.py
```

### Fase 5 - Simplificar validacao e reparo

Objetivo: deixar validacao previsivel e reduzir loops de correcao.

#### Tarefa 5.1 - Separar validadores por severidade

O que fazer:

Criar validadores com saida padronizada:

- `BLOCK`: viola read-only, usa tabela inexistente, join proibido, taxa sem
  denominador, SQL invalido.
- `WARN`: assumption nao exibida, join arriscado mas permitido, granularidade
  possivelmente ambigua.
- `INFO`: escolhas de default, limites de dado.

Arquivos provaveis:

- `src/agent/validation.py`
- `src/agent/validators/*.py`
- `tests/test_semantic_validators.py`

Aceite:

- Bloqueios sao poucos e explicaveis.
- Warnings podem ir para metadata e resposta.
- Mensagens "FIX EXACTLY" saem do caminho principal.

Validacao:

```powershell
python -m pytest tests/test_semantic_validators.py tests/test_sql_execution_block.py
```

#### Tarefa 5.2 - Reparo unico e direcionado

O que fazer:

- Permitir no maximo uma tentativa de reparo por default.
- Reparar apenas quando o erro for sintatico ou de coluna/tabela conhecida.
- Nao usar reparo para mudar metrica ou interpretacao da pergunta.

Arquivos provaveis:

- `src/agent/validation.py`
- `src/agent/repair.py`
- `src/agent/workflow.py`
- `tests/test_sql_repair.py`

Aceite:

- Loop de reparo nao mascara plano semantico errado.
- Erros de schema-unavailable viram resposta ao usuario, nao tentativa SQL.

Validacao:

```powershell
python -m pytest tests/test_sql_repair.py tests/test_routing.py
```

#### Tarefa 5.3 - Validar joins criticos por contrato

O que fazer:

- Bloquear inner join em `RACA_COR -> raca_cor` quando isso descarta `99` sem
  tratamento.
- Validar que diagnostico usa `DIAG_PRINC` por default.
- Validar que permanencia usa `DIAS_PERM`.
- Validar que municipio de residencia e municipio do hospital aparecem
  diferenciados no plano.

Arquivos provaveis:

- `src/agent/validators/semantic_invariants.py`
- `tests/test_semantic_validators.py`

Aceite:

- Cada regra critica tem teste unitario.
- O validador consome `SemanticPlan`, nao regex solta sobre a pergunta.

Validacao:

```powershell
python -m pytest tests/test_semantic_validators.py
```

### Fase 6 - Simplificar resposta final

Objetivo: preservar numeros executados e reduzir alucinacao textual.

#### Tarefa 6.1 - Criar `AnswerContract`

O que fazer:

Padronizar a saida da execucao:

- pergunta original;
- SQL executado;
- linhas retornadas;
- tipo de resposta;
- assumptions;
- warnings;
- limites do dado;
- campos numericos formatados;
- grafico opcional.

Arquivos provaveis:

- `src/agent/response.py`
- `src/agent/answer_contract.py`
- `tests/test_response.py`

Aceite:

- Resposta escalar nao chama LLM.
- Rankings e series usam renderer deterministico.
- LLM so reescreve texto curto sem alterar numeros ou labels.

Validacao:

```powershell
python -m pytest tests/test_response.py
```

#### Tarefa 6.2 - Templates de resposta por shape

O que fazer:

Criar renderers:

- `scalar`;
- `rate`;
- `ranking`;
- `time_series`;
- `distribution`;
- `catalog_lookup`;
- `schema_unavailable`;
- `clarification`.

Arquivos provaveis:

- `src/agent/response_renderers/*.py`
- `tests/test_response_renderers.py`

Aceite:

- Numeros da resposta batem exatamente com resultado SQL.
- Respostas incluem assumptions importantes, como `DT_INTER` e `DIAG_PRINC`.
- Recusas explicam o limite do schema em linguagem direta.

Validacao:

```powershell
python -m pytest tests/test_response_renderers.py tests/test_response.py
```

### Fase 7 - Avaliacao de robustez e generalizacao

Objetivo: provar que a simplificacao preserva ou melhora qualidade.

#### Tarefa 7.1 - Separar tres suites

O que fazer:

Manter tres conjuntos:

- `dev_smoke`: 10-20 perguntas rapidas para iteracao local.
- `regression_failure_focused`: perguntas historicamente frageis.
- `holdout_generalization`: perguntas nao usadas para guiar regra especifica.

Arquivos provaveis:

- `evaluation/dev_smoke.json`
- `evaluation/regression_set.json`
- `evaluation/holdout_generalization.json`
- `evaluation/runners/*`

Aceite:

- Cada pergunta tem familia, dificuldade, tabelas esperadas e comportamento
  esperado.
- Regression e holdout nao sao confundidos em metricas de produto.

Validacao:

```powershell
python -m pytest tests/test_generalization_question_loader.py
python -m evaluation.runners.run_regression --max-queries 20
```

#### Tarefa 7.2 - Gates de qualidade

Gates minimos antes de trocar o default:

| Gate | Criterio |
| --- | --- |
| SQL read-only | 100% |
| Sem tabela inexistente | 100% |
| Recusa de schema-unavailable | >= 95% |
| Table selection em gold set | >= 95% |
| Perguntas smoke | 100% sem erro runtime |
| EX no regression set | sem queda material contra baseline |
| Latencia/custo | reduzir p50 ou tokens em pelo menos 20% nas perguntas comuns |
| Fallback LLM | usado apenas quando compilador deterministico nao cobre |

Validacao:

```powershell
python -m pytest
python -m evaluation.runners.run_regression --threshold 0.90
python -m evaluation.runners.run_ablation --variants V0 V2 V4 V10 --max-queries 30
```

#### Tarefa 7.3 - Metricas por familia

O que fazer:

Reportar qualidade por familia:

- contagem;
- taxa;
- ranking;
- serie temporal;
- CID;
- procedimento;
- socioeconomico;
- catalogo;
- unsupported/recusa;
- chart.

Arquivos provaveis:

- `evaluation/metrics/*`
- `evaluation/runners/run_ablation.py`
- `evaluation/runners/run_regression.py`
- `tests/test_evaluation_result_matching.py`

Aceite:

- Uma regressao em CID nao fica escondida em media global.
- Relatorio mostra latencia, custo, tokens, EX e erro por familia.

Validacao:

```powershell
python -m pytest tests/test_evaluation_result_matching.py
```

### Fase 8 - Limpeza final e documentacao

Objetivo: remover codigo morto depois que o caminho novo estiver validado.

#### Tarefa 8.1 - Remover compatibilidade morta

O que fazer:

- Remover reexports nao usados em `src/agent/nodes.py`.
- Remover funcoes antigas de `sql_generation.py` apos migracao.
- Remover prompts obsoletos.
- Remover regras duplicadas em table templates.

Arquivos provaveis:

- `src/agent/nodes.py`
- `src/agent/sql_generation.py`
- `src/application/prompts/*`
- `src/application/config/*`

Aceite:

- `rg` nao encontra chamadas para APIs removidas.
- Testes passam sem fixtures legadas.

Validacao:

```powershell
rg "intent_planning|legacy|FIX EXACTLY|table_template" src tests
python -m pytest
```

#### Tarefa 8.2 - Atualizar README operacional

O que fazer:

- Documentar fluxo simplificado.
- Documentar fontes canonicas de semantica.
- Documentar comandos de teste com `uv` e fallback `python -m`.
- Documentar diferenca entre regression failure-focused e holdout.

Arquivos provaveis:

- `README.md`
- `docs/architecture.md`

Aceite:

- Novo engenheiro entende como adicionar uma metrica sem tocar cinco camadas.
- README nao promete componentes que nao existem mais no fluxo default.

Validacao:

```powershell
python -m pytest tests/test_readme_contract.py
```

Criar esse teste apenas se o projeto ja tiver padrao de testar documentacao.

## 8. Ordem recomendada de implementacao

Ordem conservadora:

1. Fechar Fase 0 para baseline.
2. Implementar `SchemaCard` e consolidar catalogo.
3. Extrair resolvers do planner sem mudar API.
4. Criar `SQLStrategyRouter` e mover dois compiladores simples.
5. Migrar familias uma a uma para compiladores.
6. Desligar multi-query e CoT no default depois de medir.
7. Reescrever validacao como invariantes.
8. Simplificar resposta final.
9. Rodar regression/ablation.
10. Remover codigo legado.

Essa ordem evita uma reescrita grande sem evidencia. Cada fase deve passar
testes antes da proxima.

## 9. Primeiros cortes de maior retorno

Se o objetivo for reduzir overengineering rapido, priorizar:

1. Manter `intent_planning` removido.
2. Desligar `query_planner` multi-query por default.
3. Desligar `reasoning_node` por default.
4. Criar `SchemaCard` para substituir contexto manual longo.
5. Extrair compiladores para contagem, taxa, ranking e serie temporal.
6. Transformar validadores em invariantes claras.
7. Tornar resposta escalar/ranking deterministica.

Esses cortes reduzem custo e complexidade sem mexer inicialmente em todo o
dominio.

## 10. Estrategia de teste detalhada

### 10.1 Testes unitarios

Rodar por fase:

```powershell
python -m pytest tests/test_semantic_layer.py
python -m pytest tests/test_domain_resolvers.py
python -m pytest tests/test_routing.py
python -m pytest tests/test_sql_generation_module_split.py
python -m pytest tests/test_semantic_validators.py
python -m pytest tests/test_response.py
```

### 10.2 Testes de contrato do banco

Criar testes read-only que validem fatos basicos:

```sql
SELECT COUNT(*) FROM internacoes;
SELECT COUNT(*) FROM internacoes WHERE MORTE = true;
SELECT MIN(DT_INTER), MAX(DT_INTER) FROM internacoes;
SELECT COUNT(DISTINCT CNES) FROM hospital;
SELECT COUNT(DISTINCT MUNIC_RES) FROM internacoes;
SELECT COUNT(DISTINCT DIAG_PRINC) FROM internacoes;
```

Aceite:

- Os testes nao dependem de escrever no banco.
- Quando o banco mudar, o snapshot esperado e atualizado explicitamente.

### 10.3 Smoke E2E

Rodar perguntas representativas pelo orquestrador/API. Para cada uma, validar:

- rota escolhida;
- tabelas usadas;
- SQL read-only;
- resultado nao vazio quando esperado;
- assumptions exibidas;
- ausencia de fallback LLM quando compilador deterministico cobre.

### 10.4 Regression e ablation

Comandos alvo:

```powershell
python -m evaluation.runners.run_regression --threshold 0.90
python -m evaluation.runners.run_ablation --variants V0 V2 V4 V10 --max-queries 30
```

Quando `uv` estiver disponivel:

```powershell
uv run python -m evaluation.runners.run_regression --threshold 0.90
uv run python -m evaluation.runners.run_ablation --variants V0 V2 V4 V10 --max-queries 30
```

### 10.5 Performance

Medir:

- chamadas LLM por pergunta;
- tokens por pergunta;
- latencia p50/p95;
- numero de tentativas de reparo;
- porcentagem de fallback LLM;
- tempo de execucao SQL para queries grandes;
- numero de linhas retornadas.

Metas:

- perguntas simples: 1 consulta SQL e 0-1 chamada LLM;
- sem multi-query default;
- sem CoT textual default;
- limite explicito para rankings;
- query sempre read-only.

## 11. Riscos e mitigacoes

| Risco | Impacto | Mitigacao |
| --- | --- | --- |
| Remover regra que protegia caso real | alto | mover regra para catalogo com teste antes de remover origem antiga |
| Simplificar demais e perder generalizacao | alto | medir por familia, nao so media global |
| Fallback LLM gerar SQL incorreto | medio | fallback com schema card pequeno e validacao forte |
| Joins descartarem dados silenciosamente | alto | invariantes para `RACA_COR`, municipio e diagnostico |
| Avaliacao ficar overfit no regression set | medio | separar smoke, regression e holdout |
| Banco grande causar queries caras | medio | limites, agregacoes e evitar SELECT * |
| Mudanca de schema quebrar regras hardcoded | medio | carregar fatos de artefatos gerados |
| Dependencias locais ausentes | baixo | documentar fallback `python -m` e instalar extras dev no ambiente |

## 12. Criterio final de sucesso

A refatoracao pode ser considerada concluida quando:

- O grafo default tem menos etapas e branches que o atual.
- O no `intent_planning` continua removido.
- Multi-query e CoT estao fora do caminho default, mas disponiveis para ablation
  se ainda forem uteis.
- `semantic/catalog.yml` e `SchemaCard` sao as fontes canonicas de regras.
- `sql_generation.py` deixa de ser monolito e delega para compilers.
- Validacao bloqueia invariantes confiaveis e nao atua como segundo planner.
- Resposta final preserva numeros executados e usa LLM apenas quando necessario.
- Smoke E2E passa.
- Regression nao apresenta queda material.
- Latencia ou tokens caem de forma mensuravel nas perguntas comuns.
- Documentacao explica como adicionar uma nova familia de pergunta.

## 13. Decisoes ja tomadas

- O no `intent_planning` era redundante com classificacao, `plan_gate` e
  `semantic_planner`; ele foi removido do fluxo principal.
- Imports de `set_global_llm_manager` foram simplificados para usar
  `llm_manager` diretamente.
- O teste de integracao do workflow deve proteger contra reintroducao do no
  removido.

## 14. Perguntas abertas

Estas decisoes devem ser fechadas durante a Fase 0/1:

- O produto deve considerar 2007-2023 como cobertura oficial, ignorando os 27
  residuos de `DT_INTER` antes de 2007, ou deve reportar 2000-2023 em perguntas
  globais?
- Para sexo feminino, o default deve filtrar `SEXO = 3` com base na fato, ou
  aceitar tambem `2` por compatibilidade com a dimensao?
- Para raca/cor, o valor `99` deve aparecer como "ignorado/desconhecido" em
  distribuicoes por default?
- Multi-query tem casos reais indispensaveis ou deve virar apenas experimento?
- A resposta final deve sempre mostrar SQL ao usuario ou apenas em modo debug?

## 15. Checklist executivo

- [ ] Criar baseline de runtime e smoke set.
- [ ] Criar `SchemaCard`.
- [ ] Consolidar regras em `semantic/catalog.yml`.
- [ ] Reduzir prompts/templates manuais.
- [ ] Separar resolvers do planner semantico.
- [ ] Criar `SQLStrategyRouter`.
- [ ] Extrair compiladores deterministas.
- [ ] Controlar fallback LLM.
- [ ] Reescrever validacao como invariantes.
- [ ] Simplificar renderizacao de resposta.
- [ ] Rodar smoke, regression e ablation.
- [ ] Remover codigo legado.
- [ ] Atualizar README/arquitetura.
