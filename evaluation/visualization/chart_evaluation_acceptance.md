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

- Deterministic chart evaluation: not_run
- Agent chart evaluation: not_run
- Frontend visual smoke: not_run
- Known limitations: not_reviewed

## Falhas Encontradas E Decisao

| Data | Caso | Sintoma | Causa raiz | Decisao | Status |
| --- | --- | --- | --- | --- | --- |
