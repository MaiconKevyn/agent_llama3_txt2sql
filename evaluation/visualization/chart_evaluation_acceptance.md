# Chart Evaluation Acceptance Log

## Baseline

Data: 2026-05-21

Visualizacao unit/API/frontend smoke baseline:

```bash
./.venv/bin/python -m pytest tests/test_visualization_schema.py tests/test_visualization_planner.py tests/test_visualization_validator.py tests/test_echarts_adapter.py tests/test_api_chart_contract.py tests/test_frontend_chart_layout.py tests/test_visualization_orchestrator.py tests/test_chart_evaluation.py -q
```

Resultado: PASS, 43 tests.

Deterministic chart evaluation baseline:

```bash
./.venv/bin/python evaluation/runners/run_chart_evaluation.py
```

Report: `evaluation/visualization/results/chart_evaluation_20260521T011828Z.json`

Metricas:

```json
{
  "intent_precision": 1.0,
  "intent_recall": 1.0,
  "intent_accuracy": 1.0,
  "spec_validity": 1.0,
  "column_fidelity": 1.0,
  "chart_type_accuracy": 1.0,
  "x_accuracy": 1.0,
  "y_accuracy": 1.0,
  "series_accuracy": 1.0,
  "echarts_validity": 1.0
}
```

## Gates Da Versao Final

- Deterministic chart evaluation: pass
- Agent chart evaluation: pass
- Frontend visual smoke: pass
- Known limitations: reviewed

## Offline Deep Evaluation

Data: 2026-05-21

Suite focada:

```bash
./.venv/bin/python -m pytest tests/test_visualization_schema.py tests/test_visualization_presentation.py tests/test_visualization_planner.py tests/test_visualization_validator.py tests/test_echarts_adapter.py tests/test_api_chart_contract.py tests/test_frontend_chart_layout.py tests/test_visualization_orchestrator.py tests/test_chart_evaluation.py -q
```

Resultado: PASS, 56 tests.

Familias avaliadas:

```bash
./.venv/bin/python evaluation/runners/run_chart_evaluation.py --only CHART_BAR
./.venv/bin/python evaluation/runners/run_chart_evaluation.py --only CHART_LINE
./.venv/bin/python evaluation/runners/run_chart_evaluation.py --only CHART_AREA
./.venv/bin/python evaluation/runners/run_chart_evaluation.py --only CHART_PIE
./.venv/bin/python evaluation/runners/run_chart_evaluation.py --only CHART_KPI
./.venv/bin/python evaluation/runners/run_chart_evaluation.py --only CHART_SCATTER
```

Resultado: todas as familias retornaram `spec_validity`, `column_fidelity`, `echarts_validity` e `presentation_validity` iguais a `1.0`.

Deterministic chart evaluation completa:

```bash
./.venv/bin/python evaluation/runners/run_chart_evaluation.py
```

Report: `evaluation/visualization/results/chart_evaluation_20260521T012756Z.json`

Metricas:

```json
{
  "intent_precision": 1.0,
  "intent_recall": 1.0,
  "intent_accuracy": 1.0,
  "spec_validity": 1.0,
  "column_fidelity": 1.0,
  "chart_type_accuracy": 1.0,
  "x_accuracy": 1.0,
  "y_accuracy": 1.0,
  "series_accuracy": 1.0,
  "echarts_validity": 1.0,
  "presentation_validity": 1.0
}
```

## Online Agent Evaluation

Data: 2026-05-21

Ambiente:

```text
OPENAI_API_KEY set
DATABASE_URL missing
DATABASE_PATH duckdb://///home/maiconkevyn/PycharmProjects/health-system-chatbot/sihrd5.duckdb?access_mode=read_only
```

Falha inicial investigada:

```bash
./.venv/bin/python evaluation/runners/run_chart_evaluation.py --run-agent --only CHART_AREA
```

Report: `evaluation/visualization/results/chart_evaluation_20260521T013650Z.json`

Resultado: `CHART_AREA_002` falhou porque o agente gerou SQL de receita a partir de `socioeconomico` usando `VAL_TOT`, coluna que pertence a `internacoes`.

Apos a correcao:

```bash
./.venv/bin/python evaluation/runners/run_chart_evaluation.py --run-agent --only CHART_AREA
./.venv/bin/python evaluation/runners/run_chart_evaluation.py --run-agent --only CHART_PIE
./.venv/bin/python evaluation/runners/run_chart_evaluation.py --run-agent --only CHART_KPI
./.venv/bin/python evaluation/runners/run_chart_evaluation.py --run-agent --only CHART_SCATTER
```

Reports:

- `evaluation/visualization/results/chart_evaluation_20260521T014609Z.json`
- `evaluation/visualization/results/chart_evaluation_20260521T014811Z.json`
- `evaluation/visualization/results/chart_evaluation_20260521T015126Z.json`
- `evaluation/visualization/results/chart_evaluation_20260521T015316Z.json`

Resultado: todas as familias testadas atingiram `agent_success_rate == 1.0` e `agent_echarts_validity == 1.0`.

Duas execucoes online completas:

```bash
./.venv/bin/python evaluation/runners/run_chart_evaluation.py --run-agent
./.venv/bin/python evaluation/runners/run_chart_evaluation.py --run-agent
```

Reports:

- `evaluation/visualization/results/chart_evaluation_20260521T022820Z.json`
- `evaluation/visualization/results/chart_evaluation_20260521T024308Z.json`

Metricas estaveis nas duas execucoes:

```json
{
  "intent_precision": 1.0,
  "intent_recall": 1.0,
  "intent_accuracy": 1.0,
  "spec_validity": 1.0,
  "column_fidelity": 1.0,
  "chart_type_accuracy": 1.0,
  "x_accuracy": 1.0,
  "y_accuracy": 1.0,
  "series_accuracy": 1.0,
  "echarts_validity": 1.0,
  "presentation_validity": 1.0,
  "agent_success_rate": 1.0,
  "agent_chart_type_accuracy": 1.0,
  "agent_x_accuracy": 1.0,
  "agent_y_accuracy": 1.0,
  "agent_series_accuracy": 1.0,
  "agent_echarts_validity": 1.0
}
```

## Frontend Smoke

Data: 2026-05-21

Servidor usado:

```bash
PORT=3002 HOST=127.0.0.1 API_BASE_URL=http://127.0.0.1:8000/api/v1 npm start
```

Smoke automatizado via Chrome headless DevTools Protocol com payloads representativos para barra, linha, area, donut, scatter, KPI, fallback de tabela e alta cardinalidade.

| Prompt/caso visual | Desktop 1440px | Mobile 390px | Observacao | Status |
| --- | --- | --- | --- | --- |
| barras municipios | ok | ok | 8 paineis, warnings visiveis, sem overflow | pass |
| linha mortes ano | ok | ok | SVG renderizado, titulo/subtitulo sem estouro | pass |
| area receita ano | ok | ok | moeda BRL e footnote visiveis | pass |
| donut mortes sexo | ok | ok | legenda detalhada sem sobrepor grafico | pass |
| KPI valor total | ok | ok | indicador monetario e nota visiveis | pass |
| scatter idade/mortes | ok | ok | SVG renderizado, eixos preservados | pass |
| tabela fallback | ok | ok | tabela renderizada quando nao ha ECharts | pass |

Medicoes do smoke:

```json
{
  "desktop": {
    "panels": 8,
    "echartsTargets": 7,
    "svgs": 7,
    "tables": 1,
    "summaries": 8,
    "footnotes": 8,
    "warnings": 2,
    "bodyOverflow": 0,
    "textOverflow": [],
    "panelOverflow": [],
    "blankCharts": 0,
    "shortCharts": [],
    "headerOverlap": 0
  },
  "mobile": {
    "panels": 8,
    "echartsTargets": 7,
    "svgs": 7,
    "tables": 1,
    "summaries": 8,
    "footnotes": 8,
    "warnings": 2,
    "bodyOverflow": 0,
    "textOverflow": [],
    "panelOverflow": [],
    "blankCharts": 0,
    "shortCharts": [],
    "headerOverlap": 0
  }
}
```

Screenshots:

- `evaluation/visualization/results/20260521T_frontend_smoke_rerun_desktop.png`
- `evaluation/visualization/results/20260521T_frontend_smoke_rerun_mobile.png`

## Final Acceptance

| Gate | Resultado | Evidencia |
| --- | --- | --- |
| Unit tests | pass | `./.venv/bin/python -m pytest tests/test_visualization_schema.py tests/test_visualization_presentation.py tests/test_visualization_planner.py tests/test_visualization_validator.py tests/test_echarts_adapter.py tests/test_api_chart_contract.py tests/test_frontend_chart_layout.py tests/test_visualization_orchestrator.py tests/test_chart_evaluation.py -q` -> 56 passed |
| Regression visual ampla | pass | `./.venv/bin/python -m pytest tests/test_visualization*.py tests/test_echarts_adapter.py tests/test_api_chart_contract.py tests/test_frontend_chart_layout.py tests/test_chart_evaluation.py -q` -> 94 passed |
| Offline chart eval | pass | `evaluation/visualization/results/chart_evaluation_20260521T024434Z.json` |
| Online agent eval | pass | `evaluation/visualization/results/chart_evaluation_20260521T022820Z.json` e `evaluation/visualization/results/chart_evaluation_20260521T024308Z.json` |
| Frontend smoke | pass | Chrome headless desktop/mobile com 8 casos visuais, zero overflow e zero grafico em branco |
| Limites conhecidos | reviewed | Reparos ainda podem ser acionados para SQL temporal ou categorias clinicas incompletas, mas os validadores impedem payload invalido e as duas rodadas online completas nao revelaram nova classe de falha. |

## Decisao

A versao atende os gates criticos do plano: contrato de apresentacao presente em todos os specs, ECharts valido, frontend sem quebra visual nos tipos principais, duas execucoes online completas estaveis e offline deterministico com todas as metricas em `1.0`.

## Falhas Encontradas E Decisao

| Data | Caso | Sintoma | Causa raiz | Decisao | Status |
| --- | --- | --- | --- | --- | --- |
| 2026-05-21 | CHART_AREA_002 | `agent_success_rate` caiu para 0.5 na familia area; SQL usou `SUM(VAL_TOT)` em `socioeconomico` | contexto LlamaIndex mantinha tabela removida pela validacao e o planner semantico nao inferia receita total para `valor total por ano` | rebuild do schema validado, regra semantica para `receita_total`, validacao de ChartPlan para receita em `internacoes` | fixed |
| 2026-05-21 | CHART_KPI_003 | KPI financeiro passava, mas dependia de reparo de alias `valor_total_internacoes` -> `receita_total` | macro escalar e plano semantico usavam alias divergente do contrato de visualizacao | alinhar metric name e SQL deterministico para `receita_total` | fixed |
| 2026-05-21 | Frontend smoke harness | mobile duplicou os 8 graficos do desktop | historico salvo em `localStorage` foi recarregado antes da injecao do segundo viewport | limpar DOM e historico antes de cada viewport; sem alteracao de produto | fixed |
