# Chart Agent Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer o agente gerar graficos de forma production-ready para perguntas reais do banco SIHRD5, sem expor erros internos de planejamento e sem corrigir por overfitting em exemplos isolados.

**Architecture:** O agente ja tem pipeline com semantic planner, SQL generation, semantic validators, ChartPlan, ChartSpec, presentation pass, ECharts e frontend. Este plano adiciona uma camada de avaliacao exaustiva e uma rotina de correcao por causa raiz: cada falha vira um caso reproduzivel, uma classe de erro, uma correcao generalizavel e uma familia de regressao vizinha.

**Tech Stack:** Python 3.12, pytest, DuckDB, Pydantic, LangGraph, OpenAI API, runner de avaliacao `evaluation/runners/run_chart_evaluation.py`, frontend vanilla + ECharts.

---

## Contexto E Incidente

O exemplo:

```text
Quais sao os municipios com maior taxa de mortalidade? Mostre em grafico
```

gerou erro visivel para o usuario:

```text
SEMANTIC PLAN ERROR: Sex-grouped output must return human-readable labels
('Masculino'/'Feminino' or 'homens'/'mulheres') via CASE or the sexo lookup,
not raw SEXO codes.
```

Esse erro e sintoma de falha anterior ao renderizador de graficos. O agente provavelmente gerou ou reconciliou um plano/SQL com dimensao `sexo` mesmo que a pergunta pedisse `municipios`, ou carregou uma constraint de sexo indevida para uma pergunta de mortalidade por municipio. O fix correto nao e adicionar essa frase exata ao gold set e pronto. O fix correto e:

- reproduzir a falha com trace completo;
- identificar a camada que introduziu `sexo`;
- corrigir a regra geral de inferencia de dimensao/metricas;
- adicionar regressao para perguntas vizinhas de taxa por municipio, UF, regiao, CID, especialidade, sexo e faixa etaria;
- impedir que erros internos de semantic/chart plan vazem para o usuario final.

## Base Local Confirmada

Banco ativo:

```text
/home/maiconkevyn/PycharmProjects/health-system-chatbot/sihrd5.duckdb
```

Tabelas principais confirmadas:

- `internacoes`: fato central, 183877219 linhas, periodo `2000-01-01` a `2023-12-31`.
- `municipios`: municipio, UF, regiao de saude, latitude e longitude.
- `sexo`: lookup de sexo; em `internacoes`, valores observados para sexo sao `1` e `3`.
- `raca_cor`, `especialidade`, `procedimentos`, `cid`, `socioeconomico`.

Regras de dominio que precisam virar invariantes de teste:

- Mortalidade hospitalar vem de `internacoes.MORTE`, nao de `socioeconomico`.
- Mortalidade infantil vem de `socioeconomico.VL_MORT_INFANTIL`, nao de `internacoes.MORTE`.
- Taxa de mortalidade hospitalar usa numerador `SUM(CASE WHEN MORTE THEN 1 ELSE 0 END)` e denominador `COUNT(*)`.
- Perguntas por municipio devem agrupar por `municipios.NO_MUNICIPIO` ou codigo/nome equivalente, nao por `SEXO`.
- Quando a dimensao for sexo, o output deve trazer label humano, por `CASE` ou lookup `sexo`, nunca codigo bruto.
- Perguntas financeiras de internacao usam `internacoes.VAL_TOT`, `VAL_SH`, `VAL_SP` ou `VAL_UTI`, nao `socioeconomico`.
- Graficos de categoria clinica devem excluir categorias incompletas quando a resposta for ranking visual.

## Fontes Usadas Para O Desenho Do Processo

- OpenAI Agent Evals: traces, graders, datasets e eval runs para melhorar qualidade de agentes. Fonte: https://developers.openai.com/api/docs/guides/agent-evals
- LangSmith Evaluation Concepts: definir "good" por componente critico, criar exemplos curados e usar offline evals para regressao. Fonte: https://docs.langchain.com/langsmith/evaluation-concepts
- LangSmith Evaluation Types: combinar pre-deployment offline evaluation com online monitoring e feedback loop. Fonte: https://docs.langchain.com/langsmith/evaluation-types
- Google ADK Evaluate Agents: avaliar trajetoria do agente, nao so resposta final. Fonte: https://adk.dev/evaluate/
- Google ADK Criteria: criterios de tool trajectory, response match, hallucination, multi-turn task success e tool use quality. Fonte: https://adk.dev/evaluate/criteria/
- Braintrust Evaluate: ciclo completo com dataset, task, scores, CI/CD e feedback de producao para datasets. Fonte: https://www.braintrust.dev/docs/evaluate

## Principio De Correcao

Toda falha precisa ser tratada assim:

1. Reproduzir o erro com o menor caso real.
2. Capturar query, semantic plan, selected tables, schema context, generated SQL, repaired SQL, ChartPlan, ChartSpec e erro final.
3. Classificar a camada raiz:
   - intent;
   - table selection;
   - schema context;
   - semantic planner;
   - SQL generation;
   - semantic validator;
   - repair;
   - chart plan;
   - chart spec;
   - presentation/ECharts;
   - frontend;
   - user-facing error boundary.
4. Corrigir a regra geral, nao a frase exata.
5. Adicionar pelo menos:
   - 1 teste unitario da camada raiz;
   - 1 caso gold exato do incidente;
   - 5 casos vizinhos com mesma classe semantica;
   - 3 parafrases com vocabulario diferente.
6. Rodar avaliacao focada, familia afetada, offline completa e online completa.
7. Registrar causa raiz, fix, evidencia e limitacao no acceptance log.

## Resultado Esperado

O agente deve:

- aceitar perguntas reais sobre graficos sem o usuario precisar saber nomes de colunas;
- escolher a dimensao correta para municipio, UF, regiao, sexo, raca/cor, especialidade, CID, procedimento, idade, ano e mes;
- escolher a metrica correta para internacoes, mortes, taxa de mortalidade, receita, permanencia, idade media, custo medio, leitos, medicos, populacao e mortalidade infantil;
- gerar SQL executavel e auditable;
- nunca vazar `SEMANTIC PLAN ERROR`, `CHART PLAN ERROR`, binder errors, stack traces ou mensagens internas na UI;
- quando nao conseguir responder com seguranca, retornar uma pergunta de esclarecimento ou fallback tabular seguro;
- gerar `ChartSpec` com `presentation`;
- gerar ECharts valido ou fallback de tabela;
- preservar legibilidade em desktop e mobile.

## Arquivos A Criar Ou Modificar

- Create: `evaluation/visualization/chart_agent_prod_cases.jsonl`
- Create: `evaluation/visualization/chart_agent_error_taxonomy.yml`
- Create: `evaluation/visualization/chart_agent_prod_acceptance.md`
- Create: `evaluation/runners/run_chart_agent_prod_eval.py`
- Modify: `evaluation/runners/run_chart_evaluation.py`
- Modify: `evaluation/visualization/chart_gold.json`
- Modify: `src/semantic/planner.py`
- Modify as needed: `src/semantic/validators.py`
- Modify as needed: `src/agent/table_selection.py`
- Modify as needed: `src/agent/schema_node.py`
- Modify as needed: `src/agent/execution.py`
- Modify as needed: `src/agent/sql_generation.py`
- Modify as needed: `src/visualization/chart_plan.py`
- Modify as needed: `src/interfaces/api/main.py`
- Modify as needed: `frontend/public/app.js`
- Test: `tests/test_semantic_layer.py`
- Test: `tests/test_semantic_validators.py`
- Test: `tests/test_llamaindex_workflow_routing.py`
- Test: `tests/test_visualization_chart_plan.py`
- Test: `tests/test_chart_agent_prod_eval.py`
- Test: `tests/test_api_chart_contract.py`

## Definicao De Pronto

- O incidente `Quais sao os municipios com maior taxa de mortalidade? Mostre em grafico` passa online sem erro interno.
- Zero pergunta valida de grafico no corpus production canary retorna erro bruto interno.
- `agent_success_rate == 1.0` no corpus curado production canary.
- `agent_echarts_validity == 1.0` para todos os casos chartable.
- `presentation_validity == 1.0`.
- Zero `ChartSpec` com coluna inexistente.
- Zero SQL com tabela errada para metrica sensivel:
  - `taxa_mortalidade` hospitalar em `socioeconomico`;
  - `mortalidade_infantil` em `internacoes`;
  - `receita_total` em `socioeconomico`.
- Zero sexo raw code quando a dimensao visual for sexo.
- Pelo menos duas execucoes online completas consecutivas sem nova classe de falha.
- Smoke visual desktop/mobile para barras, linhas, area, pizza, donut, scatter, KPI e tabela.
- Acceptance log atualizado com falhas, causa raiz, fix e evidencia.

## Corpus Inicial De Perguntas Reais

Estes exemplos devem alimentar `chart_agent_prod_cases.jsonl`. Eles nao devem ser tratados como frases para decorar; cada grupo representa uma classe semantica que precisa generalizar.

### Taxa De Mortalidade Por Localidade

| ID | Pergunta | Grafico esperado | Invariantes |
| --- | --- | --- | --- |
| PROD_MORT_LOC_001 | Quais sao os municipios com maior taxa de mortalidade? Mostre em grafico. | bar | x=municipio, y=taxa_mortalidade, usa `internacoes` + `municipios`, nao agrupa por sexo |
| PROD_MORT_LOC_002 | Gere um grafico de barras com os 10 municipios de maior mortalidade hospitalar. | bar | municipio + taxa, denominador completo |
| PROD_MORT_LOC_003 | Mostre em colunas a taxa de mortalidade por UF de residencia. | bar | UF + taxa |
| PROD_MORT_LOC_004 | Quais estados tiveram maior taxa de mortalidade? Gere um grafico. | bar | estado + taxa |
| PROD_MORT_LOC_005 | Mostre a taxa de mortalidade por regiao de saude em grafico de barras. | bar | regiao de saude + taxa |
| PROD_MORT_LOC_006 | Compare os municipios com maior taxa de mortalidade, considerando pelo menos 1000 internacoes. | bar | HAVING count >= 1000 |
| PROD_MORT_LOC_007 | Ranking dos municipios por mortalidade hospitalar, com minimo de 5000 internacoes, em grafico. | bar | filtro minimo + taxa |
| PROD_MORT_LOC_008 | Gere um grafico dos estados com menor taxa de mortalidade hospitalar. | bar | ordenacao ascendente |
| PROD_MORT_LOC_009 | Mostre os municipios com maior numero de mortes e a taxa de mortalidade. | bar/table | se duas metricas, escolher chart seguro ou fallback tabular |
| PROD_MORT_LOC_010 | Visualize a mortalidade hospitalar por municipio no periodo mais recente disponivel. | bar | periodo derivado sem sexo indevido |

### Series Temporais

| ID | Pergunta | Grafico esperado | Invariantes |
| --- | --- | --- | --- |
| PROD_TIME_001 | Gere um grafico de linhas com internacoes por ano. | line | x=ano ordenado |
| PROD_TIME_002 | Mostre mortes por ano em grafico de linha. | line | MORTE=true |
| PROD_TIME_003 | Gere um line chart da taxa de mortalidade por ano. | line | taxa, nao ranking |
| PROD_TIME_004 | Mostre internacoes por mes em grafico. | line | x=mes/ano, ordem temporal |
| PROD_TIME_005 | Mostre a receita total das internacoes ao longo dos anos em grafico de area. | area | SUM(VAL_TOT), `internacoes` |
| PROD_TIME_006 | Evolucao da permanencia media por ano em grafico de linha. | line | AVG(DIAS_PERM) |
| PROD_TIME_007 | Evolucao da idade media dos pacientes por ano. | line | AVG(IDADE), filtro null se necessario |
| PROD_TIME_008 | Mostre a taxa de mortalidade nos ultimos 5 anos em linha. | line | janela recente |
| PROD_TIME_009 | Compare mortes de homens e mulheres ao longo dos anos. | line | sexo label humano |
| PROD_TIME_010 | Compare internacoes por UF ao longo dos anos. | line | multi-serie controlada/top-N se necessario |

### Sexo, Raca/Cor E Perfil Demografico

| ID | Pergunta | Grafico esperado | Invariantes |
| --- | --- | --- | --- |
| PROD_DEMO_001 | Gere um grafico de pizza das mortes por sexo. | pie | labels Masculino/Feminino, nao codigo |
| PROD_DEMO_002 | Donut chart das internacoes por sexo. | donut | labels humanos |
| PROD_DEMO_003 | Mostre mortes entre homens e mulheres em barras. | bar | sexo label humano |
| PROD_DEMO_004 | Gere um grafico de pizza das internacoes por raca/cor. | pie | lookup `raca_cor` |
| PROD_DEMO_005 | Mostre taxa de mortalidade por raca/cor em barras. | bar | taxa com denominador completo |
| PROD_DEMO_006 | Mostre internacoes por faixa etaria em grafico. | bar | faixas ordenadas |
| PROD_DEMO_007 | Grafico de mortes por faixa etaria. | bar | MORTE=true |
| PROD_DEMO_008 | Compare idade media por sexo em grafico. | bar | sexo labels humanos |
| PROD_DEMO_009 | Mostre taxa de mortalidade por sexo em grafico. | bar | labels humanos + taxa |
| PROD_DEMO_010 | Distribuicao de internacoes por nacionalidade em grafico. | bar/pie | lookup `nacionalidade`, limitar cardinalidade |

### Diagnosticos, CID E Causas

| ID | Pergunta | Grafico esperado | Invariantes |
| --- | --- | --- | --- |
| PROD_CID_001 | Quais capitulos CID tiveram mais internacoes? Gere um grafico de barras. | bar | join `cid`, labels clinicos |
| PROD_CID_002 | Mostre as 10 principais causas de morte em grafico. | bar/pie | MORTE=true, exclui categorias incompletas |
| PROD_CID_003 | Gere um grafico dos grupos CID com maior taxa de mortalidade. | bar | taxa + denominador por grupo |
| PROD_CID_004 | Mostre internacoes por categoria CID em barras. | bar | limite top-N |
| PROD_CID_005 | Quais diagnosticos principais geram maior valor total? Mostre em grafico. | bar | SUM(VAL_TOT), join `cid` |
| PROD_CID_006 | Grafico de mortes por capitulo CID ao longo dos anos. | line | ano + capitulo, top-N |
| PROD_CID_007 | Pizza das 5 principais causas de morte. | pie | top 5 + outros se aplicavel |
| PROD_CID_008 | Mostre taxa de mortalidade por diagnostico principal com minimo de 1000 internacoes. | bar | HAVING count >= 1000 |
| PROD_CID_009 | Compare idade media por capitulo CID em grafico. | bar | AVG(IDADE) |
| PROD_CID_010 | Mostre os CIDs com maior media de permanencia hospitalar. | bar | AVG(DIAS_PERM) |

### Procedimentos E Especialidade

| ID | Pergunta | Grafico esperado | Invariantes |
| --- | --- | --- | --- |
| PROD_PROC_001 | Gere um donut chart dos procedimentos mais frequentes. | donut | join `internacao_procedimento` + `procedimentos` |
| PROD_PROC_002 | Mostre os procedimentos com maior valor total em barras. | bar | valor vindo de internacoes/procedimentos conforme contrato |
| PROD_PROC_003 | Quais procedimentos tiveram maior taxa de mortalidade? Gere um grafico. | bar | denominador por procedimento |
| PROD_PROC_004 | Grafico de internacoes por especialidade medica. | bar/pie | lookup `especialidade` |
| PROD_PROC_005 | Gere um grafico do valor total por especialidade. | bar | SUM(VAL_TOT) |
| PROD_PROC_006 | Mostre taxa de mortalidade por especialidade em barras. | bar | taxa correta |
| PROD_PROC_007 | Compare permanencia media por especialidade. | bar | AVG(DIAS_PERM) |
| PROD_PROC_008 | Mostre especialidades com maior numero de mortes. | bar | MORTE=true |
| PROD_PROC_009 | Grafico de procedimentos mais comuns em obstetricia. | bar | filtro ESPEC se planejado |
| PROD_PROC_010 | Procedimentos mais frequentes por ano em linha. | line | top-N + ano |

### Financeiro, Permanencia E UTI

| ID | Pergunta | Grafico esperado | Invariantes |
| --- | --- | --- | --- |
| PROD_FIN_001 | Mostre o valor total das internacoes por ano em grafico. | area/line | SUM(VAL_TOT), `internacoes` |
| PROD_FIN_002 | Gere um grafico de barras do custo medio por municipio. | bar | AVG(VAL_TOT), join municipio |
| PROD_FIN_003 | Receita total por estado em grafico de barras. | bar | SUM(VAL_TOT) |
| PROD_FIN_004 | Custo medio por especialidade em grafico. | bar | AVG(VAL_TOT) |
| PROD_FIN_005 | Valor total de UTI por ano em grafico de linha. | line | SUM(VAL_UTI) |
| PROD_FIN_006 | Permanencia media por municipio em grafico. | bar | AVG(DIAS_PERM) |
| PROD_FIN_007 | Compare receita total e taxa de mortalidade por estado em scatter. | scatter | x/y numericos coerentes |
| PROD_FIN_008 | Scatter entre permanencia media e custo medio por municipio. | scatter | AVG(DIAS_PERM), AVG(VAL_TOT) |
| PROD_FIN_009 | KPI com valor total das internacoes. | kpi | receita_total |
| PROD_FIN_010 | KPI com permanencia media geral. | kpi | AVG(DIAS_PERM) |

### Socioeconomico E Indicadores Municipais

| ID | Pergunta | Grafico esperado | Invariantes |
| --- | --- | --- | --- |
| PROD_SOCIO_001 | Mostre mortalidade infantil media por ano em grafico. | line | `socioeconomico.VL_MORT_INFANTIL` |
| PROD_SOCIO_002 | Grafico de leitos SUS por UF. | bar | `socioeconomico`, agregado por UF |
| PROD_SOCIO_003 | Mostre medicos por 1000 habitantes por ano. | line | `VL_MEDICOS_1000` |
| PROD_SOCIO_004 | Compare PIB per capita e mortalidade infantil em scatter. | scatter | `socioeconomico` |
| PROD_SOCIO_005 | Populacao por estado no ultimo ano disponivel em grafico. | bar | `QT_POPULACAO`, ultimo ano |
| PROD_SOCIO_006 | Leitos SUS por 1000 habitantes por municipio em barras. | bar | alto volume top-N |
| PROD_SOCIO_007 | Scatter entre medicos por 1000 habitantes e mortalidade infantil. | scatter | `socioeconomico` |
| PROD_SOCIO_008 | Evolucao da populacao total por ano. | line | soma populacao |
| PROD_SOCIO_009 | Municipios com maior PIB per capita em grafico. | bar | top-N |
| PROD_SOCIO_010 | Compare taxa de mortalidade hospitalar e leitos SUS por UF. | scatter | combina internacoes + socioeconomico com ano/UF claro |

### Auto Chart, Ambiguidade E Fallback Seguro

| ID | Pergunta | Grafico esperado | Invariantes |
| --- | --- | --- | --- |
| PROD_AUTO_001 | Visualize a evolucao das internacoes. | line | inferir tempo |
| PROD_AUTO_002 | Mostre graficamente as principais diferencas por sexo. | bar/table | se ambiguo, pedir esclarecimento ou usar metrica padrao segura |
| PROD_AUTO_003 | Gere um grafico disso. | follow-up | usa resultado anterior se existir |
| PROD_AUTO_004 | Transforme o resultado anterior em barras. | follow-up | preserva dados anteriores |
| PROD_AUTO_005 | Me mostre uma visualizacao mais legivel desse ranking. | follow-up | presentation-only |
| PROD_AUTO_006 | Quero um grafico com mortalidade. | clarification/table | se dimensao ausente, perguntar ou default documentado |
| PROD_AUTO_007 | Mostre custos por perfil. | clarification | perfil ambiguo |
| PROD_AUTO_008 | Grafico de cidade e mortes. | bar | municipio + mortes |
| PROD_AUTO_009 | Compare estados. | clarification | metrica ausente |
| PROD_AUTO_010 | Mostre relacao entre idade e morte. | scatter/bar | se shape nao confiavel, fallback seguro |

## Task 1: Registrar Incidente E Criar Taxonomia De Falhas

**Files:**
- Create: `evaluation/visualization/chart_agent_error_taxonomy.yml`
- Create: `evaluation/visualization/chart_agent_prod_acceptance.md`

- [ ] **Step 1: Criar taxonomia**

Create `evaluation/visualization/chart_agent_error_taxonomy.yml`:

```yaml
layers:
  intent:
    description: "Falha ao reconhecer pedido explicito ou implicito de grafico."
  table_selection:
    description: "Tabelas selecionadas nao contem a metrica/dimensao pedida."
  schema_context:
    description: "Prompt recebeu contexto de tabela removida ou ausente."
  semantic_planner:
    description: "Plano semantico inferiu metrica, dimensao, filtro ou constraint errada."
  sql_generation:
    description: "SQL gerado nao segue o plano ou nao executa."
  semantic_validator:
    description: "Validador bloqueou corretamente ou incorretamente uma query."
  repair:
    description: "Reparo nao convergiu para SQL valido ou mudou semantica."
  chart_plan:
    description: "Contrato de grafico exige colunas/labels diferentes do SQL."
  chart_spec:
    description: "ChartSpec referencia coluna inexistente ou shape inadequado."
  presentation:
    description: "Grafico valido, mas ilegivel ou sem metadata final."
  frontend:
    description: "Payload correto, renderizacao quebrada."
  user_error_boundary:
    description: "Erro interno vazou para o usuario final."

severity:
  P0: "Erro interno ou SQL invalido visivel ao usuario em pergunta valida."
  P1: "Grafico renderiza, mas responde metrica/dimensao errada."
  P2: "Grafico correto, mas ilegivel ou sem contexto."
  P3: "Caso ambiguo precisa de esclarecimento melhor."
```

- [ ] **Step 2: Criar acceptance log**

Create `evaluation/visualization/chart_agent_prod_acceptance.md`:

```markdown
# Chart Agent Production Acceptance Log

## Incidentes

| Data | Caso | Sintoma | Camada raiz | Fix generalizavel | Evidencia | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-05-21 | PROD_MORT_LOC_001 | erro bruto de sex_label_output_required em pergunta por municipio | under_investigation | under_investigation | pending | open |

## Gates

| Gate | Target | Resultado | Evidencia |
| --- | --- | --- | --- |
| Curated prod canary | 100% success | not_run | pending |
| Online full repeat 1 | 100% success | not_run | pending |
| Online full repeat 2 | 100% success | not_run | pending |
| Zero raw internal errors | 0 | not_run | pending |
| Frontend smoke | pass | not_run | pending |
```

- [ ] **Step 3: Commit**

Run:

```bash
git add evaluation/visualization/chart_agent_error_taxonomy.yml evaluation/visualization/chart_agent_prod_acceptance.md
git commit -m "docs(visualization): track production chart agent failures"
```

## Task 2: Criar Corpus Production Canary

**Files:**
- Create: `evaluation/visualization/chart_agent_prod_cases.jsonl`
- Test: `tests/test_chart_agent_prod_eval.py`

- [ ] **Step 1: Definir schema JSONL**

Each line must follow this shape:

```json
{
  "id": "PROD_MORT_LOC_001",
  "query": "Quais sao os municipios com maior taxa de mortalidade? Mostre em grafico.",
  "expected": {
    "requested": true,
    "chart_types": ["bar"],
    "tables_any": ["internacoes", "municipios"],
    "x_any": ["municipio", "no_municipio", "NO_MUNICIPIO"],
    "y_any": ["taxa_mortalidade"],
    "forbidden_dimensions": ["sexo"],
    "forbidden_sql_patterns": ["GROUP BY.*SEXO", "socioeconomico.*MORTE"],
    "required_sql_patterns": ["MORTE", "COUNT", "taxa_mortalidade"]
  },
  "tags": ["mortality_rate", "municipality", "incident", "bar"]
}
```

- [ ] **Step 2: Popular corpus inicial**

Add at least all cases from the "Corpus Inicial De Perguntas Reais" section. The first line must be the incident case `PROD_MORT_LOC_001`.

- [ ] **Step 3: Testar schema do corpus**

Create `tests/test_chart_agent_prod_eval.py` with:

```python
import json
from pathlib import Path


def test_chart_agent_prod_cases_are_valid_jsonl():
    path = Path("evaluation/visualization/chart_agent_prod_cases.jsonl")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    assert len(rows) >= 80
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))
    assert "PROD_MORT_LOC_001" in ids

    for row in rows:
        assert row["query"].strip()
        assert row["expected"]["requested"] is True
        assert row["tags"]
```

- [ ] **Step 4: Run**

```bash
./.venv/bin/python -m pytest tests/test_chart_agent_prod_eval.py -q
```

Expected: PASS.

## Task 3: Implementar Runner Production Eval

**Files:**
- Create: `evaluation/runners/run_chart_agent_prod_eval.py`
- Test: `tests/test_chart_agent_prod_eval.py`

- [ ] **Step 1: Criar avaliador de invariantes**

The runner must load JSONL, call the existing offline/online agent path, and score:

- no exception;
- no raw internal error in final response;
- `chart.requested == true`;
- `chart.spec.presentation` exists;
- ECharts valid when chartable;
- expected chart type allowed;
- expected x/y matched when present;
- SQL required patterns present;
- SQL forbidden patterns absent;
- forbidden dimensions absent from semantic plan/chart plan.

- [ ] **Step 2: Adicionar CLI**

Supported commands:

```bash
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --only PROD_MORT_LOC
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --limit 20 --run-agent
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --shuffle --seed 20260521 --run-agent
```

- [ ] **Step 3: Relatorio**

Output JSON must include:

```json
{
  "metrics": {
    "success_rate": 1.0,
    "no_raw_internal_error": 1.0,
    "chart_contract_validity": 1.0,
    "sql_invariant_validity": 1.0,
    "semantic_dimension_validity": 1.0
  },
  "failures": []
}
```

- [ ] **Step 4: Commit**

```bash
git add evaluation/runners/run_chart_agent_prod_eval.py tests/test_chart_agent_prod_eval.py
git commit -m "test(visualization): add production chart agent eval runner"
```

## Task 4: Reproduzir E Corrigir O Incidente Sem Overfitting

**Files:**
- Modify as needed: `src/semantic/planner.py`
- Modify as needed: `src/semantic/validators.py`
- Modify as needed: `src/agent/execution.py`
- Modify as needed: `src/visualization/chart_plan.py`
- Test: `tests/test_semantic_layer.py`
- Test: `tests/test_semantic_validators.py`
- Test: `tests/test_visualization_chart_plan.py`

- [ ] **Step 1: Rodar reproducer online**

```bash
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent --only PROD_MORT_LOC_001
```

Expected before fix: FAIL reproducing the internal sex-label error, or PASS if current branch already has incidental fix. If PASS, add another failing variant from `PROD_MORT_LOC_002` to `PROD_MORT_LOC_010`.

- [ ] **Step 2: Capturar debug**

Record in `chart_agent_prod_acceptance.md`:

- selected tables;
- semantic plan dimensions;
- semantic plan constraints;
- generated SQL;
- repaired SQL;
- validator error;
- chart plan.

- [ ] **Step 3: Escrever teste unitario da causa raiz**

If the semantic planner inferred sexo incorrectly for municipality mortality, add:

```python
def test_semantic_plan_mortality_rate_by_municipality_does_not_require_sex_labels():
    plan = build_semantic_plan(
        "Quais sao os municipios com maior taxa de mortalidade? Mostre em grafico."
    )

    dimension_names = {dimension.name for dimension in plan.dimensions}
    constraint_names = set(plan.constraints)
    metric_names = {metric.name for metric in plan.metrics}

    assert "taxa_mortalidade" in metric_names
    assert "municipio" in dimension_names or "municipios" in dimension_names
    assert "sexo" not in dimension_names
    assert "sex_label_output_required" not in constraint_names
```

- [ ] **Step 4: Corrigir regra geral**

Allowed fixes:

- Improve semantic dimension extraction so "municipios", "cidade", "localidade", "UF", "estado" win over accidental sex constraints.
- Add negative guard: only apply `sex_label_output_required` when user query or required dimensions explicitly reference sexo/homens/mulheres/masculino/feminino.
- If repair inserted sexo due to chart defaults, fix repair macro selection by answer shape.
- If table selection/schema context leaked sex lookup as dominant context, restrict schema context to validated tables.

Disallowed fixes:

- Special-case exact full sentence.
- Disable the sex label validator.
- Remove the chart request.
- Convert the answer to text-only to avoid the graph.

- [ ] **Step 5: Add neighboring tests**

Add tests for:

```text
Gere um grafico de barras com os 10 municipios de maior mortalidade hospitalar.
Mostre em colunas a taxa de mortalidade por UF de residencia.
Mostre taxa de mortalidade por sexo em grafico.
Compare mortes de homens e mulheres ao longo dos anos.
```

Expected:

- municipality/UF questions do not require sex labels;
- sex questions always return human labels.

- [ ] **Step 6: Run focused checks**

```bash
./.venv/bin/python -m pytest tests/test_semantic_layer.py tests/test_semantic_validators.py tests/test_visualization_chart_plan.py -q
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --only PROD_MORT_LOC
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent --only PROD_MORT_LOC
```

Expected: PASS.

## Task 5: User-Facing Error Boundary

**Files:**
- Modify: `src/interfaces/api/main.py`
- Modify: `frontend/public/app.js`
- Test: `tests/test_api_chart_contract.py`

- [ ] **Step 1: Add API test**

Add a test asserting that internal planning errors are not returned verbatim to the UI for valid chart requests. The API may include structured debug metadata only when debug mode is active.

- [ ] **Step 2: Implement safe message**

If a planning validator raises an internal error after repair attempts:

- API returns `success=false`;
- response text says the agent could not validate the chart safely;
- response suggests a narrower chart request;
- debug payload includes the internal class when debug is enabled;
- UI never prefixes raw `SEMANTIC PLAN ERROR` to the user message.

- [ ] **Step 3: Run**

```bash
./.venv/bin/python -m pytest tests/test_api_chart_contract.py tests/test_frontend_chart_layout.py -q
```

Expected: PASS.

## Task 6: Exhaustive Evaluation Protocol

**Files:**
- Modify: `evaluation/visualization/chart_agent_prod_acceptance.md`

- [ ] **Step 1: Offline curated**

```bash
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py
```

Expected:

- `success_rate == 1.0`
- `no_raw_internal_error == 1.0`
- `sql_invariant_validity == 1.0`

- [ ] **Step 2: Online smoke**

```bash
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent --limit 20
```

Expected: 100% success for smoke.

- [ ] **Step 3: Online by family**

```bash
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent --only PROD_MORT_LOC
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent --only PROD_TIME
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent --only PROD_DEMO
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent --only PROD_CID
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent --only PROD_PROC
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent --only PROD_FIN
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent --only PROD_SOCIO
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent --only PROD_AUTO
```

Expected: 100% per family, or every failure documented with root cause and fixed before continuing.

- [ ] **Step 4: Online shuffled repeat**

```bash
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent --shuffle --seed 20260521
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent --shuffle --seed 20260522
```

Expected: no order-sensitive failures.

- [ ] **Step 5: Existing chart eval compatibility**

```bash
./.venv/bin/python evaluation/runners/run_chart_evaluation.py
./.venv/bin/python evaluation/runners/run_chart_evaluation.py --run-agent
```

Expected: previous chart eval remains at target metrics.

- [ ] **Step 6: Frontend smoke**

Run the existing Chrome/headless smoke or agent-browser if available. Required visual families:

- bar;
- line;
- area;
- pie;
- donut;
- scatter;
- KPI;
- fallback table;
- error boundary safe message.

Expected:

- no blank chart;
- no horizontal overflow;
- titles/subtitles fit;
- warnings visible;
- error boundary does not leak internal strings.

## Task 7: Continuous Regression Workflow

**Files:**
- Modify as needed: `.github/workflows/ci.yml`
- Modify: `evaluation/visualization/chart_agent_prod_acceptance.md`

- [ ] **Step 1: Add lightweight CI gate**

Add offline production canary to CI:

```bash
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py
```

- [ ] **Step 2: Keep online eval manual/nightly**

Online eval should not block every PR unless API budget is explicitly accepted. Add a documented manual command:

```bash
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent --shuffle --seed "$(date +%Y%m%d)"
```

- [ ] **Step 3: Production feedback loop**

Every raw failure, user complaint, or suspicious correction from production must become:

1. a JSONL case;
2. an acceptance log row;
3. a unit test for the root layer;
4. a neighboring paraphrase group.

## Anti-Overfitting Checklist

Before accepting any fix, answer yes to all:

- Does the fix apply to a class of questions, not just one sentence?
- Did we add at least 5 neighboring questions?
- Did we test both positive and negative cases?
- Did the fix preserve previous online/offline chart metrics?
- Did we keep semantic correctness over visual convenience?
- Did we avoid weakening validators that catch real mistakes?
- Did we prevent raw internal errors from reaching the UI?

## Manual Prompt Pack For Human Review

Use these in the UI after implementation:

```text
Quais sao os municipios com maior taxa de mortalidade? Mostre em grafico.
Gere um grafico de barras com os 10 municipios de maior mortalidade hospitalar.
Mostre em colunas a taxa de mortalidade por UF de residencia.
Mostre taxa de mortalidade por sexo em grafico.
Compare mortes de homens e mulheres ao longo dos anos.
Gere um grafico de linhas com internacoes por ano.
Mostre o valor total das internacoes por ano em grafico de area.
Gere um grafico de pizza das internacoes por raca/cor.
Quais capitulos CID tiveram mais internacoes? Gere um grafico de barras.
Mostre as 10 principais causas de morte em grafico.
Gere um donut chart dos procedimentos mais frequentes.
Mostre taxa de mortalidade por especialidade em barras.
Gere um grafico de barras do custo medio por municipio.
Scatter entre permanencia media e custo medio por municipio.
Mostre mortalidade infantil media por ano em grafico.
Compare PIB per capita e mortalidade infantil em scatter.
Visualize a evolucao das internacoes.
Gere um grafico disso.
Transforme o resultado anterior em barras.
Quero um grafico com mortalidade.
```

Pass criteria for manual review:

- no raw internal error;
- chart or safe clarification appears;
- SQL debug, when enabled, uses correct tables;
- labels are human-readable;
- chart is readable.

## Commit Sequence Esperada

1. `docs(visualization): track production chart agent failures`
2. `test(visualization): add production chart agent cases`
3. `test(visualization): add production chart agent eval runner`
4. `fix(semantic): keep mortality locality charts on requested dimension`
5. `fix(api): hide internal chart planning errors from users`
6. `test(visualization): pass production chart agent canary`

## Final Gate

The work is production-ready only when:

```bash
./.venv/bin/python -m pytest tests/test_semantic_layer.py tests/test_semantic_validators.py tests/test_visualization_chart_plan.py tests/test_api_chart_contract.py tests/test_chart_agent_prod_eval.py -q
./.venv/bin/python evaluation/runners/run_chart_evaluation.py
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent --shuffle --seed 20260521
./.venv/bin/python evaluation/runners/run_chart_agent_prod_eval.py --run-agent --shuffle --seed 20260522
```

all pass, and `chart_agent_prod_acceptance.md` has no open P0/P1 item.
