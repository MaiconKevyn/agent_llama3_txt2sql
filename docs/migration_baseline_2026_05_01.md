# Migration Baseline 2026-05-01

## Context

This baseline was captured before the LangGraph `1.1.10` migration work.

Environment snapshot:

- Timestamp: `2026-05-01T22:44:39-03:00`
- Python: `3.12.3`
- Worktree state: dirty, with ongoing local refactor changes unrelated to the migration baseline

## Commands Executed

### Repository state

```bash
git status --short
date -Iseconds
./.venv/bin/python --version
```

### Passing unit / compatibility tests

```bash
./.venv/bin/python -m pytest tests/test_state_module_split.py -q
./.venv/bin/python -m pytest tests/test_sql_generation_module_split.py -q
./.venv/bin/python -m pytest tests/test_routing.py -q
./.venv/bin/python -m pytest tests/test_sql_execution_block.py -q
./.venv/bin/python -m pytest tests/test_orchestrator_support.py -q
./.venv/bin/python -c "from src.interfaces.api.main import app; print(app.title)"
```

### Failing runtime smoke tests

```bash
./.venv/bin/python src/interfaces/cli/agent.py --health-check
./.venv/bin/python -c "from src.agent.orchestrator import create_production_orchestrator; create_production_orchestrator(); print('orchestrator_ok')"
./.venv/bin/python evaluation/runners/run_regression.py
```

## Results

### Passed

- `tests/test_state_module_split.py`
- `tests/test_sql_generation_module_split.py`
- `tests/test_routing.py`
- `tests/test_sql_execution_block.py`
- `tests/test_orchestrator_support.py`
- API module import smoke test

Interpretation:

- the typed state layer works
- the workflow-facing helper layer works
- SQL generation module imports and schemas work
- routing helpers work
- SQL blocking logic works
- API module import does not fail at import time

### Failed

- CLI health check
- direct production orchestrator creation
- regression runner startup

Shared failure:

```text
sqlalchemy.exc.NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:duckdb
```

## Baseline Diagnosis

The current runtime is already blocked before any LangGraph migration change by a database dialect issue.

Observed runtime configuration:

- resolved database scheme: `duckdb`

This means:

- the migration baseline is not "fully healthy"
- the orchestrator cannot currently initialize in this environment
- regression execution is blocked by infrastructure/dependency setup

The failure happens in:

- `src/agent/llm_manager.py`
- `src/agent/orchestrator_support.py`
- `langchain_community.utilities.SQLDatabase.from_uri(...)`
- SQLAlchemy dialect resolution for `duckdb`

## Implication for Migration

Before or during PR 1, the migration work must explicitly address environment/database dependency consistency.

Minimum requirement:

- ensure the configured database URL points to a supported installed dialect
- or install and pin the DuckDB SQLAlchemy dialect required by the current `.env` / config path

Without that, runtime migration validation will remain blocked regardless of LangGraph version.

## Baseline Status

Checkpoint 0 status: partially complete.

Completed:

- repository state captured
- essential compatibility tests captured
- runtime smoke failures captured
- primary blocker identified

Blocked:

- full runtime regression baseline
- orchestrator health baseline
- evaluation baseline metrics

## Next Action

Resolve the runtime database dialect dependency first, then rerun:

```bash
./.venv/bin/python src/interfaces/cli/agent.py --health-check
./.venv/bin/python -c "from src.agent.orchestrator import create_production_orchestrator; create_production_orchestrator(); print('orchestrator_ok')"
./.venv/bin/python evaluation/runners/run_regression.py
```
