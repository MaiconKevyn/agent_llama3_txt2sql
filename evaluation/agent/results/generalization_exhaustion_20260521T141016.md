# Agent Generalization Exhaustion

- Run: `generalization_exhaustion_20260521T141016`
- Total: 10
- Dry run: `False`

## Status

| Status | Count |
| --- | ---:|
| `failed` | 7 |
| `passed` | 3 |

## Failures

| ID | Severity | Root cause | Question |
| --- | --- | --- | --- |
| GEN183 | `medium` | `response_grounding_error` | Quais UFs tiveram maior leitos SUS por 1000 habitantes em 2021? |
| GEN184 | `medium` | `response_grounding_error` | Quais UFs tiveram maior medicos por 1000 habitantes em 2021? |
| GEN185 | `high` | `sql_execution_error` | Quais UFs tiveram maior total de leitos SUS em 2021? |
| GEN186 | `high` | `sql_execution_error` | Quais UFs tiveram maior total de medicos em 2021? |
| GEN187 | `medium` | `response_grounding_error` | Quais municipios tiveram maior PIB per capita em 2019? |
| GEN188 | `medium` | `response_grounding_error` | Quais municipios tiveram maior PIB per capita em 2020? |
| GEN189 | `medium` | `response_grounding_error` | Quais municipios tiveram maior PIB per capita em 2021? |
