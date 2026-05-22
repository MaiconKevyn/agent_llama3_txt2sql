# Agent Generalization Exhaustion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Testar exaustivamente o agente com perguntas novas, fora do ground truth, derivadas do conhecimento real do banco em `docs/generated/`, corrigindo falhas por causa raiz para aumentar robustez generalista sem overfitting.

**Architecture:** O trabalho deve ser um loop de avaliacao cientifica, nao uma lista manual de perguntas. Primeiro o agente gera e valida um corpus novo baseado no schema, nas politicas de join, na cobertura de relacionamentos e na qualidade dos dados; depois executa perguntas no agente, julga resposta final contra SQL/evidencia independente, classifica falhas por camada, corrige o componente geral afetado e cria casos vizinhos para provar generalizacao.

**Tech Stack:** Python 3.12, DuckDB, LangGraph agent, Pydantic, pytest, `docs/generated/`, runners em `evaluation/agent/`, SQL auditavel, JSONL/Markdown para corpus e acceptance log. Frameworks externos de avaliacao como LangSmith, Braintrust ou OpenAI Evals podem ser adicionados apenas por adaptador opcional, depois que o runner local estiver reproduzivel.

---

## Contexto Confirmado

- Ja existe um plano de expansao de ground truth em `docs/superpowers/plans/2026-05-17-ground-truth-228-extension.md`.
- Este plano e diferente: ele cria um corpus de exploracao fora do ground truth para descobrir falhas novas e reduzir fragilidade generalista.
- Ja existe um runner de exaustao em `evaluation/agent/run_health_exhaustion.py` com 50 perguntas manuais.
- Ja existe um runner analitico em `evaluation/agent/run_analytic_evaluation.py` usando `evaluation/agent/analytic_questions.json` e `evaluation/agent/analytic_rubric.py`.
- A documentacao operacional do banco esta em `docs/generated/`.
- `docs/generated/table_inventory.csv` confirma `internacoes` como fato central com 183877219 linhas e `internacao_procedimento` com 187957888 linhas.
- `docs/generated/join_policy.csv` confirma joins seguros e caveats, por exemplo:
  - `internacoes.CNES -> hospital.CNES`: confirmado.
  - `internacoes.MUNIC_RES -> municipios.CO_MUNICIPIO_6D`: provavel, exige escopo explicito ou left join.
  - `internacoes.RACA_COR -> raca_cor.RACA_COR`: rejeitado para uso analitico amplo; usar apenas com caveat/auditoria.
  - `internacoes.INSTRU -> instrucao.INSTRU` e `internacoes.VINCPREV -> vincprev.VINCPREV`: cobertura muito baixa; usar como pergunta de qualidade/caveat, nao como evidencia causal.
- Falhas historicas ja observadas em `evaluation/agent/results/health_exhaustion_20260516T234915.md` incluem: dado inexistente respondido como zero, sinonimos clinicos incompletos, denominador populacional multiplicado por join, comparacao agrupada rejeitada por validador, campo errado para cesarea, e sucesso tecnico que nao responde a pergunta.

## Resultado Esperado

Ao final, o projeto deve ter:

- Um corpus novo de perguntas fora do ground truth, versionado e rastreavel.
- Cada pergunta classificada por persona, tema, dificuldade, tabelas esperadas, resposta esperada, SQL de referencia quando aplicavel e criterio de julgamento.
- Um runner local que executa o agente, executa SQL independente quando houver referencia, aplica rubricas deterministicas e gera relatorio Markdown.
- Um protocolo de triagem que separa pergunta valida, pergunta fora do schema, pergunta subespecificada e pergunta cientificamente indevida.
- Um loop de correcao por causa raiz que sempre adiciona regressao de familia, nao apenas o caso exato.
- Evidencia de varias rodadas consecutivas sem nova classe critica de falha.

## Arquivos

- Ler: `docs/generated/table_inventory.csv`
- Ler: `docs/generated/table_metadata.csv`
- Ler: `docs/generated/column_catalog.csv`
- Ler: `docs/generated/column_profiles.csv`
- Ler: `docs/generated/column_profiles_exact.csv`
- Ler: `docs/generated/column_profiles_approx.csv`
- Ler: `docs/generated/top_frequent_values.csv`
- Ler: `docs/generated/relationship_coverage.csv`
- Ler: `docs/generated/join_policy.csv`
- Ler: `docs/generated/data_quality_checks.json`
- Ler: `docs/generated/ground_truth_semantic_audit.csv`
- Ler: `evaluation/agent/run_health_exhaustion.py`
- Ler: `evaluation/agent/run_analytic_evaluation.py`
- Ler: `evaluation/agent/analytic_rubric.py`
- Ler: `evaluation/agent/analytic_questions.json`
- Ler: `src/semantic/planner.py`
- Ler: `src/semantic/analytic_templates.py`
- Ler conforme falha: `src/agent/analytic_sql.py`
- Ler conforme falha: `src/semantic/validators.py`
- Ler conforme falha: `src/agent/plan_gate.py`
- Ler conforme falha: `src/agent/sql_generation.py`
- Ler conforme falha: `src/agent/response.py`
- Criar: `evaluation/agent/generalization_questions.jsonl`
- Criar: `evaluation/agent/generalization_rubric.py`
- Criar: `evaluation/agent/run_generalization_exhaustion.py`
- Criar: `evaluation/agent/generalization_taxonomy.yml`
- Criar: `evaluation/agent/generalization_acceptance.md`
- Criar: `docs/agent_generalization_exhaustion_worklog.md`
- Criar: `tests/test_generalization_rubric.py`
- Criar: `tests/test_generalization_question_loader.py`
- Criar conforme falha: testes unitarios na camada raiz afetada.
- Criar conforme falha: testes de regressao em `tests/test_sql_execution_block.py`, `tests/test_analytic_templates.py`, `tests/test_analytic_response.py`, `tests/test_routing.py` ou outro teste ja existente da camada.

## Definicao De Pronto

- `evaluation/agent/generalization_questions.jsonl` contem pelo menos 200 perguntas novas que nao duplicam `evaluation/ground_truth*.json`.
- Pelo menos 70% das perguntas sao answerable com o schema atual e tem SQL de referencia independente.
- Pelo menos 20% sao perguntas intencionalmente fora do schema ou subespecificadas, para testar recusa segura.
- Pelo menos 10% sao perguntas cientificas/associativas que exigem denominador, escopo, caveat e evitar causalidade indevida.
- Cada pergunta tem `id`, `persona`, `category`, `difficulty`, `question`, `expected_behavior`, `expected_tables`, `reference_sql`, `judge`, `schema_basis` e `anti_overfit_family`.
- O runner gera JSON e Markdown em `evaluation/agent/results/`.
- Toda resposta `success=true` e julgada semanticamente, nao aceita apenas por SQL executavel.
- Toda falha tem causa raiz classificada em taxonomia.
- Para cada classe de falha corrigida, existem pelo menos 1 teste unitario da camada raiz, 1 caso exato, 5 casos vizinhos e 3 parafrases.
- Nenhuma correcao usa ID de pergunta, texto literal da pergunta ou lista fechada de exemplos como regra principal.
- O conjunto completo passa em pelo menos 3 rodadas consecutivas sem nova falha critica ou alta.
- `docs/agent_generalization_exhaustion_worklog.md` registra corpus, rodadas, falhas, causas, correcoes, evidencias e riscos restantes.

## Regras De Qualidade

- Nao medir robustez por exact match de SQL.
- Nao transformar pergunta valida em pergunta mais facil para fazer o agente passar.
- Nao aceitar resposta vazia sem explicacao.
- Nao aceitar `COUNT(*) = 0` como resposta para dado ausente do schema.
- Nao aceitar resposta causal quando o banco so suporta associacao observacional.
- Nao usar joins rejeitados em `docs/generated/join_policy.csv` sem caveat explicito.
- Nao usar `DISTINCT` para mascarar fan-out.
- Nao somar populacao depois de juntar em nivel de internacao; agregue denominador territorial antes.
- Nao usar `CID_MORTE` como causa analitica padrao de morte; para causa analitica hospitalar, usar `DIAG_PRINC` com `MORTE = true`, salvo pergunta explicitamente sobre o campo observado de causa de morte.
- Nao tratar campos de baixa cobertura (`INSTRU`, `VINCPREV`, `ETNIA`) como evidencias gerais sem aviso de qualidade.
- Nao corrigir falhas com `if "frase exata" in question`.

## Personas E Familias De Perguntas

| Persona | Intencao | Exemplos de pergunta |
| --- | --- | --- |
| Pessoa comum | Entender numeros simples e comparacoes claras | "Quantas internacoes por pneumonia ocorreram em 2021?", "Qual estado teve mais internacoes?" |
| Medico pesquisador | Explorar coortes clinicas e desfechos | "Pacientes idosos com pneumonia tiveram maior mortalidade hospitalar?", "Como variou a permanencia em UTI por faixa etaria?" |
| Epidemiologista | Tendencia, sazonalidade, denominadores e comparacoes | "Doencas respiratorias aumentaram no inverno?", "Qual a taxa por 100 mil habitantes por UF?" |
| Gestor hospitalar | Custo, permanencia, hospital, procedimento, UTI | "Quais hospitais tiveram maior custo medio por dia com pelo menos 1000 internacoes?" |
| Auditor de dados | Cobertura, nulidade, join, codigos sem lookup | "Quantas internacoes tem municipio de residencia sem cadastro territorial?" |
| Usuario fora do escopo | Pede dado inexistente ou causalidade indevida | "Qual antibiotico foi usado?", "Vacina reduziu morte por covid?", "Sobrevida um ano apos alta?" |

## Categorias Minimas Do Corpus

| Categoria | Minimo | Observacoes |
| --- | ---:| --- |
| Volume e tendencia temporal | 20 | anos, meses, ultimos N anos, crescimento, sazonalidade |
| Mortalidade hospitalar | 25 | taxa, numerador/denominador, rankings, grupos |
| Diagnosticos/CID | 25 | descricoes, capitulos, sinonimos clinicos, codigos especificos |
| Geografia | 20 | UF, municipio residencia, municipio hospital, regiao saude |
| Procedimentos | 15 | `internacao_procedimento`, `procedimentos`, evitar diagnostico como proxy de procedimento |
| Custos e permanencia | 20 | `VAL_TOT`, `VAL_UTI`, `DIAS_PERM`, custo por dia, NULLS LAST |
| UTI | 15 | `MARCA_UTI`, `UTI_INT_TO`, mortalidade, custo, permanencia |
| Perfil demografico | 20 | idade, sexo, raca/cor com caveat, instrucao com caveat |
| Socioeconomico/populacao | 15 | denominador agregado antes do join com fatos |
| Qualidade de dados | 15 | nulidade, codigos sem lookup, joins com baixa cobertura |
| Fora do schema | 20 | vacina, medicamento, exame, rural/urbano, readmissao, seguimento pos-alta |
| Perguntas cientificas associativas | 20 | denominador, escopo, efeito observado, caveat de nao causalidade |

## Severidade De Falha

| Severidade | Criterio | Acao |
| --- | --- | --- |
| Critica | Resposta numerica errada com alta confianca, dado inexistente respondido como fato, causalidade indevida, SQL em tabela errada | Corrigir antes de nova rodada completa |
| Alta | SQL executa mas responde outra pergunta, denominador errado, join com fan-out, filtro temporal incorreto | Corrigir e adicionar familia de regressao |
| Media | Resposta parcial, caveat ausente, formato ruim para pesquisa | Corrigir se recorrente ou se afeta familias analiticas |
| Baixa | Texto pouco claro, arredondamento ou apresentacao | Registrar e corrigir quando tocar a camada |

## Taxonomia De Causa Raiz

Criar `evaluation/agent/generalization_taxonomy.yml` com:

```yaml
root_causes:
  intent_misclassification:
    description: "A intencao geral da pergunta foi classificada de forma errada."
  unsupported_schema_detection:
    description: "O agente nao detectou que a pergunta exige dado inexistente."
  table_selection:
    description: "Tabelas relevantes foram omitidas ou tabelas indevidas foram escolhidas."
  join_policy_violation:
    description: "O SQL usou join rejeitado, fan-out ou escopo de join sem caveat."
  clinical_concept_resolution:
    description: "Sinonimo, CID, capitulo ou conceito clinico foi resolvido incorretamente."
  denominator_error:
    description: "Taxa, proporcao ou populacao usou denominador errado."
  temporal_logic_error:
    description: "Periodo, ultimos N anos, sazonalidade ou comparacao temporal foi interpretado errado."
  aggregation_shape_error:
    description: "A resposta deveria ser escalar, ranking, grupo, serie ou comparacao e saiu em outro formato."
  sql_execution_error:
    description: "SQL invalido para DuckDB ou schema atual."
  semantic_validation_false_positive:
    description: "Validador rejeitou SQL semanticamente correto."
  semantic_validation_false_negative:
    description: "Validador aceitou SQL semanticamente errado."
  response_grounding_error:
    description: "SQL correto, mas resposta textual inventou, omitiu ou distorceu resultado."
  unsafe_causal_claim:
    description: "Resposta transformou associacao observacional em causalidade."
  performance_timeout:
    description: "Consulta valida travou ou excedeu tempo aceitavel."
```

## Formato Do Corpus

Cada linha de `evaluation/agent/generalization_questions.jsonl` deve seguir:

```json
{"id":"GEN001","persona":"epidemiologista","category":"mortalidade_hospitalar","difficulty":"medium","question":"Qual foi a taxa de mortalidade hospitalar por UF de residencia em 2021?","expected_behavior":"answer_with_sql","expected_tables":["internacoes","municipios"],"reference_sql":"SELECT mu.\"SG_UF\" AS uf_residencia, COUNT(*) AS total_internacoes, SUM(CASE WHEN i.\"MORTE\" = true THEN 1 ELSE 0 END) AS total_obitos, ROUND(SUM(CASE WHEN i.\"MORTE\" = true THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS taxa_mortalidade_percentual FROM internacoes i JOIN municipios mu ON i.\"MUNIC_RES\" = mu.\"CO_MUNICIPIO_6D\" WHERE EXTRACT(YEAR FROM i.\"DT_INTER\") = 2021 GROUP BY mu.\"SG_UF\" ORDER BY taxa_mortalidade_percentual DESC;","judge":{"type":"result_equivalence","required_columns":["uf_residencia","total_internacoes","total_obitos","taxa_mortalidade_percentual"],"tolerance":0.01},"schema_basis":["docs/generated/join_policy.csv:internacoes.MUNIC_RES->municipios.CO_MUNICIPIO_6D likely","docs/generated/table_metadata.csv:internacoes.DT_INTER,MORTE"],"anti_overfit_family":"mortalidade_por_geografia"}
```

Para perguntas fora do schema:

```json
{"id":"GEN_UNSUPPORTED_001","persona":"pessoa_comum","category":"fora_do_schema","difficulty":"easy","question":"Quais antibioticos foram mais usados em pacientes internados por pneumonia?","expected_behavior":"safe_refusal","expected_tables":[],"reference_sql":null,"judge":{"type":"unsupported_schema","must_mention":["medicamentos","nao esta disponivel","banco atual"],"must_not_claim_numeric_answer":true},"schema_basis":["docs/generated/column_catalog.csv nao contem medicamentos ou prescricoes"],"anti_overfit_family":"medicamentos_inexistentes"}
```

## Task 1: Preparar Ambiente E Worklog

**Files:**
- Ler: `.env`
- Ler: `src/application/config/simple_config.py`
- Criar: `docs/agent_generalization_exhaustion_worklog.md`

- [ ] **Step 1: Registrar estado do repo**

Run:

```bash
git status --short
git branch --show-current
git rev-parse --short HEAD
```

Expected:

- Registrar branch, commit e arquivos pre-existentes no worklog.
- Nao remover resultados nao rastreados existentes em `evaluation/agent/results/` ou `evaluation/visualization/results/`.

- [ ] **Step 2: Confirmar banco ativo**

Run:

```bash
./.venv/bin/python - <<'PY'
from src.application.config.simple_config import ApplicationConfig
cfg = ApplicationConfig()
print(cfg.database_path)
PY
```

Expected:

- Registrar o path real no worklog.
- Se o banco nao abrir em modo read-only, parar e corrigir ambiente antes de criar corpus.

- [ ] **Step 3: Criar worklog**

Create `docs/agent_generalization_exhaustion_worklog.md`:

```markdown
# Agent Generalization Exhaustion Worklog

## Ambiente
- Branch:
- Commit inicial:
- Banco ativo:
- Data de inicio:

## Corpus
- Arquivo:
- Total de perguntas:
- Answerable:
- Fora do schema:
- Associativas/cientificas:

## Rodadas

| Rodada | Data | Corpus | Total | Passou | Falhas criticas | Falhas altas | Novas classes | Evidencia |
| --- | --- | --- | ---:| ---:| ---:| ---:| ---:| --- |

## Falhas E Correcoes

| ID | Familia | Severidade | Causa raiz | Fix geral | Testes | Evidencia |
| --- | --- | --- | --- | --- | --- | --- |

## Decisoes De Nao Corrigir

| ID | Motivo | Risco | Revisitar quando |
| --- | --- | --- | --- |
```

- [ ] **Step 4: Commit**

Run:

```bash
git add docs/agent_generalization_exhaustion_worklog.md
git commit -m "docs(evaluation): add agent generalization worklog"
```

Expected:

- Commit pequeno e isolado, se o usuario estiver executando o plano em uma branch propria.

## Task 2: Criar Loader E Validacao Do Corpus

**Files:**
- Criar: `evaluation/agent/generalization_questions.jsonl`
- Criar: `evaluation/agent/generalization_rubric.py`
- Criar: `tests/test_generalization_question_loader.py`

- [ ] **Step 1: Criar corpus minimo inicial**

Create `evaluation/agent/generalization_questions.jsonl` with 12 seed cases:

```jsonl
{"id":"GEN001","persona":"epidemiologista","category":"mortalidade_hospitalar","difficulty":"medium","question":"Qual foi a taxa de mortalidade hospitalar por UF de residencia em 2021?","expected_behavior":"answer_with_sql","expected_tables":["internacoes","municipios"],"reference_sql":"SELECT mu.\"SG_UF\" AS uf_residencia, COUNT(*) AS total_internacoes, SUM(CASE WHEN i.\"MORTE\" = true THEN 1 ELSE 0 END) AS total_obitos, ROUND(SUM(CASE WHEN i.\"MORTE\" = true THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS taxa_mortalidade_percentual FROM internacoes i JOIN municipios mu ON i.\"MUNIC_RES\" = mu.\"CO_MUNICIPIO_6D\" WHERE EXTRACT(YEAR FROM i.\"DT_INTER\") = 2021 GROUP BY mu.\"SG_UF\" ORDER BY taxa_mortalidade_percentual DESC;","judge":{"type":"result_equivalence","required_columns":["uf_residencia","total_internacoes","total_obitos","taxa_mortalidade_percentual"],"tolerance":0.01},"schema_basis":["docs/generated/join_policy.csv:internacoes.MUNIC_RES->municipios.CO_MUNICIPIO_6D likely"],"anti_overfit_family":"mortalidade_por_geografia"}
{"id":"GEN002","persona":"medico_pesquisador","category":"diagnosticos_cid","difficulty":"medium","question":"Quais capitulos CID concentraram mais internacoes em 2021?","expected_behavior":"answer_with_sql","expected_tables":["internacoes","cid"],"reference_sql":"SELECT c.\"DS_CAPITULO\" AS capitulo_cid, COUNT(*) AS total_internacoes FROM internacoes i JOIN cid c ON i.\"DIAG_PRINC\" = c.\"CID\" WHERE EXTRACT(YEAR FROM i.\"DT_INTER\") = 2021 GROUP BY c.\"DS_CAPITULO\" ORDER BY total_internacoes DESC LIMIT 10;","judge":{"type":"result_equivalence","required_columns":["capitulo_cid","total_internacoes"],"tolerance":0.0},"schema_basis":["docs/generated/table_metadata.csv:cid.DS_CAPITULO","docs/generated/join_policy.csv:internacoes.DIAG_PRINC->cid.CID confirmed"],"anti_overfit_family":"cid_capitulo_ranking"}
{"id":"GEN003","persona":"gestor_hospitalar","category":"custos_permanencia","difficulty":"hard","question":"Quais hospitais tiveram maior custo medio por dia de internacao em 2021 considerando apenas hospitais com pelo menos 1000 internacoes e permanencia maior que zero?","expected_behavior":"answer_with_sql","expected_tables":["internacoes","hospital"],"reference_sql":"SELECT h.\"NO_HOSPITAL\" AS hospital, COUNT(*) AS total_internacoes, ROUND(SUM(i.\"VAL_TOT\") / NULLIF(SUM(i.\"DIAS_PERM\"), 0), 2) AS custo_medio_por_dia FROM internacoes i JOIN hospital h ON i.\"CNES\" = h.\"CNES\" WHERE EXTRACT(YEAR FROM i.\"DT_INTER\") = 2021 AND i.\"DIAS_PERM\" > 0 GROUP BY h.\"NO_HOSPITAL\" HAVING COUNT(*) >= 1000 ORDER BY custo_medio_por_dia DESC NULLS LAST LIMIT 10;","judge":{"type":"result_equivalence","required_columns":["hospital","total_internacoes","custo_medio_por_dia"],"tolerance":0.01},"schema_basis":["docs/generated/join_policy.csv:internacoes.CNES->hospital.CNES confirmed"],"anti_overfit_family":"custo_por_dia_hospital"}
{"id":"GEN004","persona":"epidemiologista","category":"socioeconomico_populacao","difficulty":"hard","question":"Qual foi a taxa de internacoes por 100 mil habitantes por UF em 2021?","expected_behavior":"answer_with_sql","expected_tables":["internacoes","municipios","socioeconomico"],"reference_sql":"WITH internacoes_por_uf AS (SELECT mu.\"SG_UF\" AS uf, COUNT(*) AS total_internacoes FROM internacoes i JOIN municipios mu ON i.\"MUNIC_RES\" = mu.\"CO_MUNICIPIO_6D\" WHERE EXTRACT(YEAR FROM i.\"DT_INTER\") = 2021 GROUP BY mu.\"SG_UF\"), populacao_por_uf AS (SELECT m.\"SG_UF\" AS uf, SUM(s.\"QT_POPULACAO\") AS populacao FROM socioeconomico s JOIN municipios m ON s.\"CO_MUNICIPIO\" = m.\"CO_MUNICIPIO_6D\" WHERE s.\"ANO\" = 2021 GROUP BY m.\"SG_UF\") SELECT i.uf, i.total_internacoes, p.populacao, ROUND(i.total_internacoes * 100000.0 / NULLIF(p.populacao, 0), 2) AS taxa_por_100k FROM internacoes_por_uf i JOIN populacao_por_uf p ON i.uf = p.uf ORDER BY taxa_por_100k DESC;","judge":{"type":"result_equivalence","required_columns":["uf","total_internacoes","populacao","taxa_por_100k"],"tolerance":0.01},"schema_basis":["docs/generated/table_metadata.csv:socioeconomico","historical failure: denominador populacional nao pode ser somado apos join com internacoes"],"anti_overfit_family":"taxa_populacional"}
{"id":"GEN005","persona":"pessoa_comum","category":"fora_do_schema","difficulty":"easy","question":"Quais antibioticos foram mais usados em pacientes internados por pneumonia?","expected_behavior":"safe_refusal","expected_tables":[],"reference_sql":null,"judge":{"type":"unsupported_schema","must_mention":["medicamentos","nao esta disponivel"],"must_not_claim_numeric_answer":true},"schema_basis":["docs/generated/column_catalog.csv nao contem medicamentos ou prescricoes"],"anti_overfit_family":"medicamentos_inexistentes"}
{"id":"GEN006","persona":"pessoa_comum","category":"fora_do_schema","difficulty":"easy","question":"Qual foi a cobertura vacinal dos pacientes que morreram por covid?","expected_behavior":"safe_refusal","expected_tables":[],"reference_sql":null,"judge":{"type":"unsupported_schema","must_mention":["vacinacao","nao esta disponivel"],"must_not_claim_numeric_answer":true},"schema_basis":["docs/generated/column_catalog.csv nao contem vacinacao"],"anti_overfit_family":"vacinacao_inexistente"}
{"id":"GEN007","persona":"medico_pesquisador","category":"pergunta_cientifica_associativa","difficulty":"hard","question":"Existe relacao entre idade e doencas respiratorias nas internacoes?","expected_behavior":"answer_with_analytic_template","expected_tables":["internacoes","cid"],"reference_sql":null,"judge":{"type":"analytic_response","required":["concept_resolution","denominator_present","group_distribution_present","comparative_metric_present","no_causal_overclaim","no_sample_only"]},"schema_basis":["src/semantic/analytic_templates.py:numeric_factor_by_condition"],"anti_overfit_family":"idade_condicao_respiratoria"}
{"id":"GEN008","persona":"epidemiologista","category":"temporal","difficulty":"hard","question":"As internacoes por doencas respiratorias aumentaram no inverno no Rio Grande do Sul em 2021?","expected_behavior":"answer_with_sql","expected_tables":["internacoes","cid","municipios"],"reference_sql":"WITH mensal AS (SELECT EXTRACT(MONTH FROM i.\"DT_INTER\") AS mes, COUNT(*) AS total_internacoes FROM internacoes i JOIN cid c ON i.\"DIAG_PRINC\" = c.\"CID\" JOIN municipios mu ON i.\"MUNIC_RES\" = mu.\"CO_MUNICIPIO_6D\" WHERE mu.\"SG_UF\" = 'RS' AND EXTRACT(YEAR FROM i.\"DT_INTER\") = 2021 AND c.\"CID\" LIKE 'J%' GROUP BY mes), comparacao AS (SELECT SUM(CASE WHEN mes IN (6,7,8) THEN total_internacoes ELSE 0 END) AS internacoes_inverno, SUM(CASE WHEN mes NOT IN (6,7,8) THEN total_internacoes ELSE 0 END) AS internacoes_outros_meses FROM mensal) SELECT internacoes_inverno, internacoes_outros_meses, ROUND(internacoes_inverno / 3.0, 2) AS media_mensal_inverno, ROUND(internacoes_outros_meses / 9.0, 2) AS media_mensal_outros_meses, ROUND((internacoes_inverno / 3.0) / NULLIF((internacoes_outros_meses / 9.0), 0), 2) AS razao_inverno_vs_outros FROM comparacao;","judge":{"type":"result_equivalence","required_columns":["internacoes_inverno","internacoes_outros_meses","media_mensal_inverno","media_mensal_outros_meses","razao_inverno_vs_outros"],"tolerance":0.01},"schema_basis":["historical failure: contar apenas inverno nao responde se aumentou"],"anti_overfit_family":"sazonalidade_comparativa"}
{"id":"GEN009","persona":"gestor_hospitalar","category":"procedimentos","difficulty":"hard","question":"Qual foi a quantidade de partos cesareos por UF de residencia em 2021?","expected_behavior":"answer_with_sql","expected_tables":["internacoes","internacao_procedimento","procedimentos","municipios"],"reference_sql":"SELECT mu.\"SG_UF\" AS uf_residencia, COUNT(*) AS total_procedimentos_cesarea FROM internacao_procedimento ip JOIN internacoes i ON ip.\"N_AIH\" = i.\"N_AIH\" JOIN procedimentos p ON ip.\"PROC_REA\" = p.\"PROC_REA\" JOIN municipios mu ON i.\"MUNIC_RES\" = mu.\"CO_MUNICIPIO_6D\" WHERE EXTRACT(YEAR FROM i.\"DT_INTER\") = 2021 AND p.\"DESCRICAO\" ILIKE '%CESAR%' GROUP BY mu.\"SG_UF\" ORDER BY total_procedimentos_cesarea DESC;","judge":{"type":"result_equivalence","required_columns":["uf_residencia","total_procedimentos_cesarea"],"tolerance":0.0},"schema_basis":["historical failure: cesarea deve usar procedimentos, nao DIAG_PRINC"],"anti_overfit_family":"procedimento_obstetrico"}
{"id":"GEN010","persona":"auditor_dados","category":"qualidade_dados","difficulty":"medium","question":"Quantas internacoes tem diagnostico principal ausente ou em branco?","expected_behavior":"answer_with_sql","expected_tables":["internacoes"],"reference_sql":"SELECT COUNT(*) AS internacoes_sem_diag_princ FROM internacoes WHERE \"DIAG_PRINC\" IS NULL OR TRIM(\"DIAG_PRINC\") = '';","judge":{"type":"result_equivalence","required_columns":["internacoes_sem_diag_princ"],"tolerance":0.0},"schema_basis":["historical failure: sem preenchimento nao e o mesmo que CID sem lookup"],"anti_overfit_family":"nulidade_diagnostico"}
{"id":"GEN011","persona":"medico_pesquisador","category":"fora_do_schema","difficulty":"medium","question":"Qual foi a taxa de reinternacao em ate 30 dias apos alta hospitalar?","expected_behavior":"safe_refusal","expected_tables":[],"reference_sql":null,"judge":{"type":"unsupported_schema","must_mention":["identificador longitudinal","reinternacao","nao esta disponivel"],"must_not_claim_numeric_answer":true},"schema_basis":["internacoes nao contem identificador longitudinal confiavel de paciente"],"anti_overfit_family":"seguimento_longitudinal_inexistente"}
{"id":"GEN012","persona":"epidemiologista","category":"mortalidade_hospitalar","difficulty":"hard","question":"Compare a taxa de mortalidade hospitalar entre Maranhao e Rio Grande do Sul em 2021.","expected_behavior":"answer_with_sql","expected_tables":["internacoes","municipios"],"reference_sql":"SELECT mu.\"SG_UF\" AS uf_residencia, COUNT(*) AS total_internacoes, SUM(CASE WHEN i.\"MORTE\" = true THEN 1 ELSE 0 END) AS total_obitos, ROUND(SUM(CASE WHEN i.\"MORTE\" = true THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS taxa_mortalidade_percentual FROM internacoes i JOIN municipios mu ON i.\"MUNIC_RES\" = mu.\"CO_MUNICIPIO_6D\" WHERE EXTRACT(YEAR FROM i.\"DT_INTER\") = 2021 AND mu.\"SG_UF\" IN ('MA','RS') GROUP BY mu.\"SG_UF\" ORDER BY uf_residencia;","judge":{"type":"result_equivalence","required_columns":["uf_residencia","total_internacoes","total_obitos","taxa_mortalidade_percentual"],"tolerance":0.01},"schema_basis":["historical failure: comparacao MA vs RS exige GROUP BY"],"anti_overfit_family":"comparacao_geografica_dupla"}
```

- [ ] **Step 2: Escrever teste de loader**

Create `tests/test_generalization_question_loader.py`:

```python
import json
from pathlib import Path

from evaluation.agent.generalization_rubric import load_generalization_questions


def test_load_generalization_questions_has_required_fields():
    questions = load_generalization_questions(Path("evaluation/agent/generalization_questions.jsonl"))

    assert len(questions) >= 12
    ids = [item.id for item in questions]
    assert len(ids) == len(set(ids))
    assert all(item.question.strip() for item in questions)
    assert all(item.expected_behavior in {"answer_with_sql", "safe_refusal", "answer_with_analytic_template"} for item in questions)
    assert any(item.expected_behavior == "safe_refusal" for item in questions)
    assert any(item.expected_behavior == "answer_with_sql" for item in questions)


def test_jsonl_is_valid_one_object_per_line():
    path = Path("evaluation/agent/generalization_questions.jsonl")
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert lines
    for line in lines:
        payload = json.loads(line)
        assert sorted(payload) == [
            "anti_overfit_family",
            "category",
            "difficulty",
            "expected_behavior",
            "expected_tables",
            "id",
            "judge",
            "persona",
            "question",
            "reference_sql",
            "schema_basis",
        ]
```

- [ ] **Step 3: Implementar modelos Pydantic**

Create `evaluation/agent/generalization_rubric.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


ExpectedBehavior = Literal["answer_with_sql", "safe_refusal", "answer_with_analytic_template"]


class GeneralizationQuestion(BaseModel):
    id: str
    persona: str
    category: str
    difficulty: Literal["easy", "medium", "hard"]
    question: str
    expected_behavior: ExpectedBehavior
    expected_tables: list[str] = Field(default_factory=list)
    reference_sql: str | None = None
    judge: dict[str, Any]
    schema_basis: list[str] = Field(default_factory=list)
    anti_overfit_family: str

    @model_validator(mode="after")
    def validate_sql_policy(self) -> "GeneralizationQuestion":
        if self.expected_behavior == "answer_with_sql" and not self.reference_sql:
            raise ValueError(f"{self.id} expects SQL but has no reference_sql")
        if self.expected_behavior == "safe_refusal" and self.reference_sql:
            raise ValueError(f"{self.id} is safe_refusal but has reference_sql")
        return self


def load_generalization_questions(path: Path | None = None) -> list[GeneralizationQuestion]:
    path = path or Path(__file__).with_name("generalization_questions.jsonl")
    questions: list[GeneralizationQuestion] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            questions.append(GeneralizationQuestion.model_validate_json(line))
        except Exception as exc:
            raise ValueError(f"Invalid generalization question at {path}:{line_number}: {exc}") from exc
    return questions
```

- [ ] **Step 4: Rodar teste e validar falha/passe**

Run:

```bash
./.venv/bin/python -m pytest tests/test_generalization_question_loader.py -q
```

Expected:

- `2 passed`.

- [ ] **Step 5: Commit**

Run:

```bash
git add evaluation/agent/generalization_questions.jsonl evaluation/agent/generalization_rubric.py tests/test_generalization_question_loader.py
git commit -m "test(evaluation): add generalization question corpus loader"
```

## Task 3: Implementar Rubricas De Julgamento Local

**Files:**
- Modificar: `evaluation/agent/generalization_rubric.py`
- Criar: `tests/test_generalization_rubric.py`

- [ ] **Step 1: Escrever testes das rubricas**

Create `tests/test_generalization_rubric.py`:

```python
from evaluation.agent.generalization_rubric import (
    judge_safe_refusal,
    score_numeric_equivalence,
)


def test_judge_safe_refusal_accepts_explicit_schema_limitation():
    result = judge_safe_refusal(
        response="O banco atual nao possui informacoes de medicamentos ou prescricoes, entao nao consigo calcular quais antibioticos foram usados.",
        judge={"must_mention": ["medicamentos", "nao possui"], "must_not_claim_numeric_answer": True},
    )

    assert result["passed"] is True
    assert result["missing"] == []


def test_judge_safe_refusal_rejects_fake_zero_answer():
    result = judge_safe_refusal(
        response="Foram encontrados 0 antibioticos usados em pacientes com pneumonia.",
        judge={"must_mention": ["medicamentos", "nao esta disponivel"], "must_not_claim_numeric_answer": True},
    )

    assert result["passed"] is False
    assert "numeric_claim_for_unsupported_schema" in result["missing"]


def test_score_numeric_equivalence_allows_small_tolerance():
    expected = [{"uf": "MA", "taxa": 10.01}, {"uf": "RS", "taxa": 9.99}]
    actual = [{"uf": "MA", "taxa": 10.02}, {"uf": "RS", "taxa": 9.98}]

    result = score_numeric_equivalence(expected, actual, required_columns=["uf", "taxa"], tolerance=0.02)

    assert result["passed"] is True


def test_score_numeric_equivalence_rejects_missing_required_column():
    result = score_numeric_equivalence(
        [{"uf": "MA", "taxa": 10.0}],
        [{"uf": "MA"}],
        required_columns=["uf", "taxa"],
        tolerance=0.01,
    )

    assert result["passed"] is False
    assert "missing_column:taxa" in result["missing"]
```

- [ ] **Step 2: Implementar rubricas deterministicas**

Append to `evaluation/agent/generalization_rubric.py`:

```python
import re


def _normalize_text(value: str) -> str:
    return (
        value.lower()
        .replace("ã", "a")
        .replace("á", "a")
        .replace("à", "a")
        .replace("â", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
        .replace("ç", "c")
    )


def judge_safe_refusal(*, response: str, judge: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_text(response or "")
    missing: list[str] = []
    for token in judge.get("must_mention", []):
        if _normalize_text(str(token)) not in normalized:
            missing.append(f"missing_token:{token}")
    if judge.get("must_not_claim_numeric_answer") and re.search(r"\b\d+(?:[.,]\d+)?\b", normalized):
        if not any(token in normalized for token in ["nao", "indisponivel", "nao possui", "nao esta disponivel"]):
            missing.append("numeric_claim_for_unsupported_schema")
    return {"passed": not missing, "missing": missing}


def score_numeric_equivalence(
    expected_rows: list[dict[str, Any]],
    actual_rows: list[dict[str, Any]],
    *,
    required_columns: list[str],
    tolerance: float,
) -> dict[str, Any]:
    missing: list[str] = []
    if len(expected_rows) != len(actual_rows):
        missing.append(f"row_count:{len(actual_rows)}!={len(expected_rows)}")
    for column in required_columns:
        if expected_rows and column not in expected_rows[0]:
            missing.append(f"expected_missing_column:{column}")
        if actual_rows and column not in actual_rows[0]:
            missing.append(f"missing_column:{column}")
    if missing:
        return {"passed": False, "missing": missing}

    for index, (expected, actual) in enumerate(zip(expected_rows, actual_rows, strict=False)):
        for column in required_columns:
            expected_value = expected.get(column)
            actual_value = actual.get(column)
            if isinstance(expected_value, int | float) and isinstance(actual_value, int | float):
                if abs(float(expected_value) - float(actual_value)) > tolerance:
                    missing.append(f"value_mismatch:{index}:{column}")
            elif str(expected_value) != str(actual_value):
                missing.append(f"value_mismatch:{index}:{column}")
    return {"passed": not missing, "missing": missing}
```

- [ ] **Step 3: Rodar testes**

Run:

```bash
./.venv/bin/python -m pytest tests/test_generalization_rubric.py tests/test_generalization_question_loader.py -q
```

Expected:

- Todos passam.

- [ ] **Step 4: Commit**

Run:

```bash
git add evaluation/agent/generalization_rubric.py tests/test_generalization_rubric.py
git commit -m "test(evaluation): add generalization judging rubrics"
```

## Task 4: Implementar Runner De Exaustao Generalista

**Files:**
- Criar: `evaluation/agent/run_generalization_exhaustion.py`
- Modificar: `evaluation/agent/generalization_rubric.py`
- Criar: `tests/test_generalization_runner_smoke.py`

- [ ] **Step 1: Criar teste smoke sem chamar o agente**

Create `tests/test_generalization_runner_smoke.py`:

```python
from evaluation.agent.run_generalization_exhaustion import summarize_items


def test_summarize_items_counts_statuses_and_root_causes():
    payload = [
        {"status": "passed", "root_cause": None, "severity": None},
        {"status": "failed", "root_cause": "denominator_error", "severity": "high"},
        {"status": "failed", "root_cause": "unsupported_schema_detection", "severity": "critical"},
    ]

    summary = summarize_items(payload)

    assert summary["status_counts"] == {"passed": 1, "failed": 2}
    assert summary["root_cause_counts"]["denominator_error"] == 1
    assert summary["severity_counts"]["critical"] == 1
```

- [ ] **Step 2: Implementar runner com modo `--limit` e `--dry-run`**

Create `evaluation/agent/run_generalization_exhaustion.py`:

```python
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from evaluation.agent.analytic_rubric import score_analytic_response
from evaluation.agent.generalization_rubric import (
    judge_safe_refusal,
    load_generalization_questions,
)
from src.agent.orchestrator import LangGraphOrchestrator
from src.application.config.simple_config import OrchestratorConfig


def summarize_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status_counts": dict(Counter(item.get("status") for item in items)),
        "root_cause_counts": dict(Counter(item.get("root_cause") for item in items if item.get("root_cause"))),
        "severity_counts": dict(Counter(item.get("severity") for item in items if item.get("severity"))),
    }


def classify_failure(item: dict[str, Any]) -> tuple[str | None, str | None]:
    response = str(item.get("response") or "").lower()
    error = str(item.get("error") or "").lower()
    sql = str(item.get("sql") or "").lower()
    expected_behavior = item.get("expected_behavior")
    if item.get("status") == "passed":
        return None, None
    if expected_behavior == "safe_refusal" and any(token in response for token in ["0 ", "zero", "foram encontrados"]):
        return "unsupported_schema_detection", "critical"
    if "binder error" in error or "does not exist" in error:
        return "sql_execution_error", "high"
    if "populacao" in sql and "join internacoes" in sql:
        return "denominator_error", "high"
    if "cid_morte" in sql and "causa" in item.get("question", "").lower():
        return "clinical_concept_resolution", "high"
    return "response_grounding_error", "medium"


def evaluate_response(question: Any, result: dict[str, Any]) -> dict[str, Any]:
    response = result.get("response") or result.get("final_response") or ""
    sql = result.get("sql_query") or result.get("generated_sql") or ""
    if question.expected_behavior == "safe_refusal":
        judgement = judge_safe_refusal(response=response, judge=question.judge)
        return {"passed": judgement["passed"], "judge": judgement}
    if question.expected_behavior == "answer_with_analytic_template":
        score = score_analytic_response(
            question=question.question,
            response=response,
            sql=sql,
            semantic_plan=(result.get("metadata") or {}).get("semantic_plan") or {},
        )
        return {"passed": score.score >= 0.85 and not score.missing, "judge": score.model_dump()}
    return {"passed": bool(result.get("success")) and bool(response), "judge": {"type": "needs_reference_sql_execution"}}


def run_items(*, limit: int | None, dry_run: bool) -> list[dict[str, Any]]:
    questions = load_generalization_questions()
    selected = questions[:limit] if limit else questions
    if dry_run:
        return [
            {
                "id": item.id,
                "question": item.question,
                "expected_behavior": item.expected_behavior,
                "status": "dry_run",
                "root_cause": None,
                "severity": None,
            }
            for item in selected
        ]

    orchestrator = LangGraphOrchestrator(
        orchestrator_config=OrchestratorConfig(
            enable_llamaindex_context=True,
            llamaindex_mode="context",
        ),
        environment="testing",
    )
    results: list[dict[str, Any]] = []
    for item in selected:
        raw = orchestrator.process_query(
            item.question,
            session_id=f"generalization_{item.id.lower()}",
            force_single_query=True,
        )
        judgement = evaluate_response(item, raw)
        output = {
            "id": item.id,
            "persona": item.persona,
            "category": item.category,
            "difficulty": item.difficulty,
            "question": item.question,
            "expected_behavior": item.expected_behavior,
            "anti_overfit_family": item.anti_overfit_family,
            "status": "passed" if judgement["passed"] else "failed",
            "judge": judgement["judge"],
            "success": raw.get("success"),
            "response": raw.get("response") or raw.get("final_response"),
            "sql": raw.get("sql_query") or raw.get("generated_sql"),
            "metadata": raw.get("metadata") or {},
            "error": raw.get("error_message") or raw.get("error"),
        }
        root_cause, severity = classify_failure(output)
        output["root_cause"] = root_cause
        output["severity"] = severity
        results.append(output)
    return results


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    summary = payload["summary"]
    lines = [
        "# Agent Generalization Exhaustion",
        "",
        f"- Run: `{payload['run_id']}`",
        f"- Total: {len(payload['items'])}",
        "",
        "## Status",
        "",
        "| Status | Count |",
        "| --- | ---:|",
    ]
    for status, count in sorted(summary["status_counts"].items()):
        lines.append(f"| `{status}` | {count} |")
    lines.extend(["", "## Failures", "", "| ID | Severity | Root cause | Question |", "| --- | --- | --- | --- |"])
    for item in payload["items"]:
        if item.get("status") != "failed":
            continue
        question = str(item["question"]).replace("|", "\\|")
        lines.append(f"| {item['id']} | `{item.get('severity')}` | `{item.get('root_cause')}` | {question} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    items = run_items(limit=args.limit, dry_run=args.dry_run)
    run_id = datetime.now().strftime("generalization_exhaustion_%Y%m%dT%H%M%S")
    output_dir = Path("evaluation/agent/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        "summary": summarize_items(items),
        "items": items,
    }
    json_path = output_dir / f"{run_id}.json"
    md_path = output_dir / f"{run_id}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, md_path)
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Rodar testes e dry-run**

Run:

```bash
./.venv/bin/python -m pytest tests/test_generalization_runner_smoke.py tests/test_generalization_rubric.py tests/test_generalization_question_loader.py -q
./.venv/bin/python -m evaluation.agent.run_generalization_exhaustion --dry-run --limit 3
```

Expected:

- Testes passam.
- Dry-run cria JSON e MD em `evaluation/agent/results/`.

- [ ] **Step 4: Commit**

Run:

```bash
git add evaluation/agent/run_generalization_exhaustion.py tests/test_generalization_runner_smoke.py
git commit -m "feat(evaluation): add generalization exhaustion runner"
```

## Task 5: Adicionar Execucao De SQL De Referencia

**Files:**
- Modificar: `evaluation/agent/run_generalization_exhaustion.py`
- Modificar: `evaluation/agent/generalization_rubric.py`
- Modificar: `tests/test_generalization_rubric.py`

- [ ] **Step 1: Adicionar comparacao por resultado**

Atualizar `evaluate_response` para:

- executar `reference_sql` no DuckDB ativo;
- executar o SQL gerado pelo agente quando existir;
- comparar colunas e valores com `score_numeric_equivalence`;
- salvar preview de ambos os resultados;
- marcar como falha se o agente respondeu texto mas o SQL gerado nao bateu com a referencia.

Use `src.infrastructure.database.connection_service` ou o padrao ja usado por runners existentes. Se esse caminho estiver pesado, criar helper local pequeno que usa `duckdb.connect` com `ApplicationConfig().database_path`.

- [ ] **Step 2: Testar comparador sem banco grande**

Adicionar teste usando listas em memoria, nao o banco real:

```python
def test_result_equivalence_rejects_wrong_ordered_values():
    expected = [{"uf": "MA", "total": 10}, {"uf": "RS", "total": 20}]
    actual = [{"uf": "MA", "total": 10}, {"uf": "RS", "total": 21}]

    result = score_numeric_equivalence(expected, actual, required_columns=["uf", "total"], tolerance=0.0)

    assert result["passed"] is False
    assert "value_mismatch:1:total" in result["missing"]
```

- [ ] **Step 3: Rodar subset live**

Run:

```bash
./.venv/bin/python -m evaluation.agent.run_generalization_exhaustion --limit 3
```

Expected:

- O runner salva SQL gerado, resposta, julgamento e causa raiz.
- Se falhar, nao corrigir ainda; registrar a falha no worklog para Task 7.

## Task 6: Expandir Corpus Para 200+ Perguntas Fora Do Ground Truth

**Files:**
- Modificar: `evaluation/agent/generalization_questions.jsonl`
- Modificar: `docs/agent_generalization_exhaustion_worklog.md`
- Opcional criar: `tmp/generalization_candidate_questions.json`
- Opcional criar: `tmp/generalization_duplicate_report.json`

- [ ] **Step 1: Extrair perguntas existentes para evitar duplicidade**

Run:

```bash
./.venv/bin/python - <<'PY'
import json
from pathlib import Path

paths = sorted(Path("evaluation").glob("ground_truth*.json"))
questions = []
for path in paths:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("question"):
                questions.append((path.name, item.get("id"), item["question"]))
print("ground_truth_questions", len(questions))
for row in questions[:20]:
    print(row)
PY
```

Expected:

- Registrar total aproximado no worklog.
- Nao adicionar perguntas que sejam apenas parafrases triviais do ground truth.

- [ ] **Step 2: Usar `docs/generated/` como fonte de cobertura**

Run:

```bash
./.venv/bin/python - <<'PY'
import csv
from pathlib import Path

for name in ["table_inventory.csv", "join_policy.csv", "column_catalog.csv"]:
    path = Path("docs/generated") / name
    print(f"## {name}")
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for index, row in zip(range(12), reader, strict=False):
            print(row)
PY
```

Expected:

- Construir matriz manual de cobertura por tabela, join e familia.
- Toda pergunta nova deve apontar para pelo menos uma evidência em `schema_basis`.

- [ ] **Step 3: Expandir por familias, nao por frases**

Adicionar perguntas ate bater os minimos da secao "Categorias Minimas Do Corpus".

Para cada familia, gerar:

- 1 pergunta direta.
- 2 variacoes de persona.
- 2 parafrases com vocabulario diferente.
- 1 pergunta com periodo explicito.
- 1 pergunta com caveat de denominador ou filtro minimo.
- 1 pergunta fora do schema vizinha, quando aplicavel.

- [ ] **Step 4: Validar formato**

Run:

```bash
./.venv/bin/python -m pytest tests/test_generalization_question_loader.py -q
```

Expected:

- Passa com 200+ perguntas.

- [ ] **Step 5: Commit**

Run:

```bash
git add evaluation/agent/generalization_questions.jsonl docs/agent_generalization_exhaustion_worklog.md
git commit -m "test(evaluation): expand generalization exhaustion corpus"
```

## Task 7: Rodar Loop De Falha, Investigacao E Correcao

**Files:**
- Modificar conforme causa raiz.
- Modificar: `docs/agent_generalization_exhaustion_worklog.md`
- Modificar: `evaluation/agent/generalization_acceptance.md`
- Criar/modificar testes conforme falha.

- [ ] **Step 1: Rodar corpus focado**

Run:

```bash
./.venv/bin/python -m evaluation.agent.run_generalization_exhaustion --limit 25
```

Expected:

- Gerar JSON e MD.
- Registrar falhas criticas/altas no worklog.

- [ ] **Step 2: Para cada falha critica/alta, abrir trace e classificar causa**

Para cada item falho, registrar:

```markdown
### GENxxx

- Pergunta:
- Resposta do agente:
- SQL gerado:
- SQL de referencia:
- Diferenca observada:
- Causa raiz:
- Severidade:
- Camada a corrigir:
- Familia anti-overfit:
```

- [ ] **Step 3: Escrever teste unitario antes do fix**

Exemplos de mapeamento:

| Causa | Teste provavel |
| --- | --- |
| `unsupported_schema_detection` | `tests/test_routing.py` |
| `clinical_concept_resolution` | `tests/test_sql_execution_block.py` ou teste de concept resolver |
| `denominator_error` | `tests/test_sql_execution_block.py` |
| `temporal_logic_error` | `tests/test_sql_execution_block.py` |
| `aggregation_shape_error` | `tests/test_semantic_plan_reconciliation.py` |
| `response_grounding_error` | `tests/test_analytic_response.py` |
| `semantic_validation_false_positive` | `tests/test_semantic_validators.py` |

- [ ] **Step 4: Implementar correcao geral**

Regra:

- A correcao deve ser uma regra semantica, template, validador, detector de unsupported schema, politica de join ou formatador de resposta.
- A correcao nao pode depender do ID `GENxxx`.
- A correcao nao pode comparar a pergunta inteira.
- Se usar sinonimos, adicionar familia clinica ampla com fonte no catalogo `cid`, nao so a palavra do exemplo.

- [ ] **Step 5: Adicionar casos vizinhos**

Para cada falha corrigida, adicionar ao corpus:

- 1 caso exato que falhou.
- 5 casos vizinhos da mesma familia.
- 3 parafrases com vocabulario diferente.

Exemplo para `taxa_populacional`:

```jsonl
{"id":"GEN_POP_NEIGHBOR_001","persona":"epidemiologista","category":"socioeconomico_populacao","difficulty":"hard","question":"Compare a taxa de internacoes por 100 mil habitantes entre MA e RS em 2021.","expected_behavior":"answer_with_sql","expected_tables":["internacoes","municipios","socioeconomico"],"reference_sql":"WITH internacoes_por_uf AS (SELECT mu.\"SG_UF\" AS uf, COUNT(*) AS total_internacoes FROM internacoes i JOIN municipios mu ON i.\"MUNIC_RES\" = mu.\"CO_MUNICIPIO_6D\" WHERE EXTRACT(YEAR FROM i.\"DT_INTER\") = 2021 AND mu.\"SG_UF\" IN ('MA','RS') GROUP BY mu.\"SG_UF\"), populacao_por_uf AS (SELECT m.\"SG_UF\" AS uf, SUM(s.\"QT_POPULACAO\") AS populacao FROM socioeconomico s JOIN municipios m ON s.\"CO_MUNICIPIO\" = m.\"CO_MUNICIPIO_6D\" WHERE s.\"ANO\" = 2021 AND m.\"SG_UF\" IN ('MA','RS') GROUP BY m.\"SG_UF\") SELECT i.uf, i.total_internacoes, p.populacao, ROUND(i.total_internacoes * 100000.0 / NULLIF(p.populacao, 0), 2) AS taxa_por_100k FROM internacoes_por_uf i JOIN populacao_por_uf p ON i.uf = p.uf ORDER BY i.uf;","judge":{"type":"result_equivalence","required_columns":["uf","total_internacoes","populacao","taxa_por_100k"],"tolerance":0.01},"schema_basis":["denominador populacional agregado por UF antes do join"],"anti_overfit_family":"taxa_populacional"}
```

- [ ] **Step 6: Rodar regressao focada**

Run:

```bash
./.venv/bin/python -m pytest tests/test_sql_execution_block.py tests/test_generalization_rubric.py -q
./.venv/bin/python -m evaluation.agent.run_generalization_exhaustion --limit 25
```

Expected:

- O caso corrigido passa.
- Casos vizinhos passam ou revelam nova causa raiz.

- [ ] **Step 7: Commit por classe de falha**

Run:

```bash
git add src/semantic/planner.py src/agent/analytic_sql.py tests/test_sql_execution_block.py evaluation/agent/generalization_questions.jsonl docs/agent_generalization_exhaustion_worklog.md
git commit -m "fix(agent): improve population-rate generalization"
```

## Task 8: Rodadas Completas E Criterio De Confianca

**Files:**
- Modificar: `docs/agent_generalization_exhaustion_worklog.md`
- Modificar: `evaluation/agent/generalization_acceptance.md`

- [ ] **Step 1: Rodar corpus completo**

Run:

```bash
./.venv/bin/python -m evaluation.agent.run_generalization_exhaustion
```

Expected:

- Gerar JSON e Markdown completos.
- Registrar totais por status, severidade, categoria e familia.

- [ ] **Step 2: Corrigir todas as falhas criticas e altas**

Repetir Task 7 ate:

- `critical == 0`
- `high == 0`
- falhas medias conhecidas documentadas com decisao explicita

- [ ] **Step 3: Rodar tres rodadas completas consecutivas**

Run:

```bash
./.venv/bin/python -m evaluation.agent.run_generalization_exhaustion
./.venv/bin/python -m evaluation.agent.run_generalization_exhaustion
./.venv/bin/python -m evaluation.agent.run_generalization_exhaustion
```

Expected:

- Nenhuma nova classe critica/alta.
- Variacao aceitavel apenas em apresentacao ou latencia.
- Se houver falha intermitente, classificar como estabilidade/performance e corrigir antes de aceitar.

- [ ] **Step 4: Criar acceptance report**

Create `evaluation/agent/generalization_acceptance.md`:

```markdown
# Agent Generalization Acceptance

## Escopo
- Corpus:
- Total de perguntas:
- Answerable:
- Fora do schema:
- Associativas/cientificas:

## Resultado Final

| Rodada | Arquivo | Pass rate | Criticas | Altas | Medias | Baixas |
| --- | --- | ---:| ---:| ---:| ---:| ---:|

## Classes Corrigidas

| Classe | Sintoma | Fix geral | Testes | Evidencia |
| --- | --- | --- | --- | --- |

## Riscos Restantes

| Risco | Impacto | Mitigacao |
| --- | --- | --- |

## Conclusao

Declarar se ha grande confianca operacional para perguntas comuns, perguntas de medico pesquisador, perguntas quantitativas e perguntas cientificas observacionais.
```

- [ ] **Step 5: Verificacao final**

Run:

```bash
git diff --check
./.venv/bin/python -m pytest tests/test_generalization_question_loader.py tests/test_generalization_rubric.py tests/test_generalization_runner_smoke.py -q
```

Expected:

- Sem whitespace errors.
- Testes locais passam.

## Task 9: Opcional, Integrar Framework Externo De Evals

**Files:**
- Opcional criar: `evaluation/agent/export_generalization_eval.py`
- Opcional criar: `docs/agent_eval_framework_adapter.md`

So executar esta task se o runner local estiver estavel e houver ganho claro de rastreabilidade.

- [ ] **Step 1: Criar exportador neutro**

Exportar `generalization_questions.jsonl` e resultados para formato generico:

```json
{
  "input": "pergunta do usuario",
  "expected": {
    "behavior": "answer_with_sql",
    "reference_sql": "SELECT COUNT(*) AS total_internacoes FROM internacoes WHERE EXTRACT(YEAR FROM \"DT_INTER\") = 2021;"
  },
  "metadata": {
    "id": "GEN001",
    "family": "mortalidade_por_geografia",
    "category": "mortalidade_hospitalar"
  }
}
```

- [ ] **Step 2: Manter runner local como fonte da verdade**

Mesmo usando ferramenta externa:

- corpus canonico fica em `evaluation/agent/generalization_questions.jsonl`;
- resultados canonicos ficam em `evaluation/agent/results/`;
- CI e reproducibilidade nao dependem de servico externo.

## Politica De Iteracao Profunda

O processo so deve parar quando uma destas condicoes for verdadeira:

- O corpus completo tem 3 rodadas consecutivas sem falha critica ou alta.
- Uma falha depende de dado realmente ausente e foi convertida para recusa segura com teste.
- Uma falha depende de mudanca estrutural grande demais para a rodada atual e foi registrada como risco com plano separado.

Durante a iteracao:

- Corrigir uma familia por vez.
- Commitar por classe de falha.
- Reexecutar o subset afetado antes do corpus completo.
- Atualizar worklog a cada rodada.
- Priorizar falhas com maior risco de resposta clinica ou quantitativa errada.

## Self-Review Do Plano

- Cobertura do pedido: o plano cria um arquivo `.md`, define corpus diferente do ground truth, usa `docs/generated/`, avalia resposta do agente, investiga causa, corrige sem overfitting e itera ate alta confianca.
- Controle anti-overfit: cada falha exige familia, vizinhos e parafrases; proibido usar ID ou frase exata.
- Generalidade: inclui pessoa comum, medico pesquisador, epidemiologista, gestor e auditor.
- Profundidade: cobre perguntas cientificas, quantitativas, associativas, fora do schema e qualidade de dados.
- Execucao: cada tarefa tem arquivos, comandos e criterio esperado.
