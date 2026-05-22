# Agent Generalization Exhaustion

- Run: `generalization_exhaustion_20260521T143527`
- Total: 10
- Dry run: `False`

## Status

| Status | Count |
| --- | ---:|
| `failed` | 8 |
| `passed` | 2 |

## Failures

| ID | Severity | Root cause | Question |
| --- | --- | --- | --- |
| GEN193 | `medium` | `response_grounding_error` | Qual foi a taxa de internacoes por 100 mil habitantes por UF em 2019? |
| GEN194 | `medium` | `response_grounding_error` | Qual foi a taxa de internacoes por 100 mil habitantes por UF em 2020? |
| GEN195 | `medium` | `response_grounding_error` | Qual foi a taxa de internacoes por 100 mil habitantes por UF em 2021? |
| GEN196 | `medium` | `response_grounding_error` | Quantas internacoes tiveram diagnostico principal ausente ou em branco em 2020? |
| GEN197 | `medium` | `response_grounding_error` | Quantas internacoes tiveram diagnostico principal ausente ou em branco em 2021? |
| GEN198 | `medium` | `response_grounding_error` | Quantas internacoes tiveram diagnostico principal ausente ou em branco em 2022? |
| GEN199 | `medium` | `response_grounding_error` | Quantos diagnosticos principais de 2020 nao existem no catalogo CID? |
| GEN200 | `high` | `sql_execution_error` | Quantos diagnosticos principais de 2021 nao existem no catalogo CID? |
