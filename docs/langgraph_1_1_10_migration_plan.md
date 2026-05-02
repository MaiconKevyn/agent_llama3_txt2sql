# LangGraph 1.1.10 Migration Plan

## Objective

Refactor the project to run intentionally on `langgraph==1.1.10` and align the surrounding LLM stack without breaking existing behavior in:

- CLI execution
- FastAPI endpoints
- SQL generation and execution
- multi-query planning
- checkpoint persistence
- evaluation runners

This plan treats the migration as a controlled compatibility upgrade, not as a feature redesign.

## Current State

The repository currently has inconsistent dependency declarations:

- `pyproject.toml` allows `langgraph>=0.6.6`
- `requirements.txt` pins `langgraph==0.6.6`
- `uv.lock` already resolves `langgraph==1.1.10`

The same inconsistency exists for the broader LangChain/OpenAI stack.

Resolved versions currently present in `uv.lock`:

- `langgraph==1.1.10`
- `langgraph-checkpoint-sqlite==3.0.3`
- `langchain-core==1.3.2`
- `langchain-community==0.4.1`
- `langchain-openai==1.2.1`
- `openai==2.33.0`
- `fastapi==0.136.1`
- `uvicorn==0.46.0`
- `pydantic==2.13.3`
- `sqlalchemy==2.0.49`
- `psycopg2-binary==2.9.12`
- `python-dotenv==1.2.2`
- `requests==2.33.1`
- `sentence-transformers==5.4.1`
- `mlflow==3.11.1`

## Scope

In scope:

- dependency normalization
- compatibility fixes for LangGraph/LangChain/OpenAI APIs
- checkpointing validation
- runner and test stabilization
- regression validation

Out of scope for this migration:

- architecture redesign
- prompt redesign
- planner strategy changes
- replacing SQLite checkpoint storage
- changing public API shapes unless required for compatibility

## Compatibility Surface

### Direct LangGraph usage

Primary files:

- `src/agent/workflow.py`
- `src/agent/orchestrator_support.py`
- `src/agent/state_models.py`
- `src/agent/state_helpers.py`

Observed features in use:

- `StateGraph`
- `START`
- `END`
- `workflow.compile(checkpointer=...)`
- `workflow.invoke(...)`
- `workflow.stream(...)`
- `add_messages`
- `SqliteSaver`

Risk level: low to medium.

Reason: the project uses the stable graph construction path, not advanced or deprecated orchestration features.

### LangChain / OpenAI integration

Primary files:

- `src/agent/llm_manager.py`
- `src/agent/sql_generation.py`
- `src/agent/query_planner.py`
- `src/agent/multi_executor.py`
- `src/agent/result_synthesizer.py`
- `src/agent/classification.py`
- `src/agent/execution.py`

Observed features in use:

- `ChatOpenAI`
- `bind_tools(...)`
- `with_structured_output(...)`
- `AIMessage`, `HumanMessage`, `ToolMessage`, `SystemMessage`
- `SQLDatabase`
- `SQLDatabaseToolkit`
- tool `invoke(...)`

Risk level: medium to high.

Reason: these libraries evolve more often in payload shape and tool integration behavior than `StateGraph` itself.

### Application interfaces

Primary files:

- `src/interfaces/api/main.py`
- `src/interfaces/cli/agent.py`
- `src/agent/orchestrator.py`
- `evaluation/runners/run_regression.py`
- `evaluation/runners/run_ablation.py`

Risk level: medium.

Reason: interface behavior depends on orchestrator result shape remaining stable.

## Migration Principles

1. Upgrade dependencies before redesigning logic.
2. Change one layer at a time.
3. Prove compatibility with tests before touching prompts or routing.
4. Keep result payload contracts stable.
5. Maintain a clean rollback point after each checkpoint.

## Target Dependency Policy

The project should stop relying on broad `>=` declarations for critical LLM packages.

Recommended target policy:

- pin exact versions for the LangGraph/LangChain/OpenAI stack
- treat `pyproject.toml` plus `uv.lock` as canonical
- generate `requirements.txt` from the lock, not manually

Recommended initial pinned target set:

```toml
langgraph==1.1.10
langgraph-checkpoint-sqlite==3.0.3
langchain-core==1.3.2
langchain-community==0.4.1
langchain-openai==1.2.1
openai==2.33.0
fastapi==0.136.1
uvicorn==0.46.0
pydantic==2.13.3
sqlalchemy==2.0.49
psycopg2-binary==2.9.12
python-dotenv==1.2.2
requests==2.33.1
sentence-transformers==5.4.1
mlflow==3.11.1
```

This is the safest starting point because it matches what the repository already resolves under `uv.lock`.

## Implementation Checkpoints

### Checkpoint 0: Baseline Freeze

Goal:

Capture the current behavior before any dependency alignment.

Tasks:

- record `git status`
- record current `uv.lock`
- run targeted unit tests
- run API smoke test
- run CLI smoke test
- run a short regression slice
- save outputs under a dated artifact folder

Suggested commands:

```bash
pytest tests/test_state_module_split.py -q
pytest tests/test_sql_generation_module_split.py -q
pytest tests/test_routing.py -q
pytest tests/test_sql_execution_block.py -q
python -m src.interfaces.cli.agent --health-check
python evaluation/runners/run_regression.py
```

Acceptance criteria:

- baseline artifacts saved
- known failures documented
- no migration changes yet

Rollback:

- none needed

### Checkpoint 1: Canonical Dependency Strategy

Goal:

Make one installation path authoritative.

Tasks:

- declare `uv` as the canonical installer
- update `pyproject.toml` to explicit versions
- regenerate `requirements.txt` from the lock or mark it as exported compatibility output
- verify local environment can be recreated from scratch

Files likely touched:

- `pyproject.toml`
- `requirements.txt`
- `README.md`
- `uv.lock`

Acceptance criteria:

- `uv sync` produces the expected environment
- `requirements.txt` no longer contradicts the lock

Rollback:

- revert manifest files only

### Checkpoint 2: Add Compatibility Smoke Tests

Goal:

Add tests that fail fast if the new stack breaks the agent’s runtime contract.

Tasks:

- add orchestrator construction smoke test
- add workflow compile smoke test
- add checkpoint/thread_id smoke test
- add `workflow.invoke(...)` smoke test
- add `workflow.stream(...)` smoke test
- add `ChatOpenAI.bind_tools(...)` smoke test
- add `with_structured_output(...)` smoke test

Recommended new tests:

- `tests/test_langgraph_runtime_compat.py`
- `tests/test_llm_manager_stack_compat.py`
- `tests/test_api_smoke.py`

Acceptance criteria:

- smoke tests pass on the pinned target stack
- failures point to specific integration surfaces

Rollback:

- tests can stay even if later checkpoints fail

### Checkpoint 3: Pure Dependency Upgrade

Goal:

Run the existing code against the target stack without changing logic.

Tasks:

- apply version pins
- refresh lockfile
- recreate environment
- run the compatibility smoke tests

Non-goals:

- no prompt changes
- no routing changes
- no planner changes
- no API redesign

Acceptance criteria:

- workflow compiles
- orchestrator starts
- imports resolve
- smoke tests identify only real compatibility defects

Rollback:

- revert manifest and lockfile changes

### Checkpoint 4: LangGraph Runtime Fixes

Goal:

Fix compatibility issues in the graph runtime layer only.

Areas to inspect:

- `StateGraph(...)` initialization
- `compile(checkpointer=...)`
- config format for `configurable.thread_id`
- `stream(...)` output shape
- `add_messages` interaction with typed state

Files likely touched:

- `src/agent/workflow.py`
- `src/agent/orchestrator_support.py`
- `src/agent/state_models.py`
- `src/agent/state_helpers.py`

Acceptance criteria:

- graph compiles cleanly
- checkpoint-backed sessions work
- streaming and non-streaming paths both execute

Rollback:

- revert runtime-layer changes only

### Checkpoint 5: LangChain / OpenAI Integration Fixes

Goal:

Fix compatibility issues in model invocation, tools, and structured output.

Areas to inspect:

- `ChatOpenAI(...)` initialization fields
- `bind_tools(...)`
- tool call extraction from `AIMessage`
- `with_structured_output(...)`
- `SQLDatabaseToolkit` behavior
- tool `.invoke(...)` payload expectations

Files likely touched:

- `src/agent/llm_manager.py`
- `src/agent/sql_generation.py`
- `src/agent/query_planner.py`
- `src/agent/multi_executor.py`
- `src/agent/result_synthesizer.py`
- `src/agent/execution.py`
- `src/agent/classification.py`

Acceptance criteria:

- SQL generation still returns SQL
- structured planner outputs still parse
- tool execution remains functional
- no response-shape regression at orchestrator level

Rollback:

- revert only integration-layer changes

### Checkpoint 6: Interface Contract Validation

Goal:

Ensure CLI, API, and evaluation runners still work with the upgraded stack.

Tasks:

- validate API startup
- validate `/health`
- validate `/query`
- validate CLI `--health-check`
- validate evaluation runner imports and startup

Files likely touched:

- `src/interfaces/api/main.py`
- `src/interfaces/cli/agent.py`
- `src/agent/orchestrator.py`
- `evaluation/runners/run_regression.py`
- `evaluation/runners/run_ablation.py`

Acceptance criteria:

- API response model unchanged
- CLI usable
- evaluation runners executable

Rollback:

- revert interface-layer changes only

### Checkpoint 7: Short Regression Suite

Goal:

Validate core behavior on a small but representative query set.

Required slices:

- 5 simple single-table queries
- 5 join queries
- 5 ranking/aggregation queries
- 5 multi-query planner cases
- 3 clarification/conversational cases
- 3 expected-error cases

Validate per case:

- `success`
- `sql_query`
- `response`
- `row_count`
- retry behavior
- no exception escapes

Acceptance criteria:

- zero new crashes
- zero checkpoint corruption
- no catastrophic quality drop

Rollback:

- revert to the previous passing checkpoint

### Checkpoint 8: Full Regression and Evaluation

Goal:

Prove that the migration did not materially degrade the agent.

Tasks:

- run the full regression suite
- run ablation runner if still used
- run evaluation pipeline
- compare outputs against baseline artifacts

Metrics to compare:

- execution success rate
- EX / CM / EM where available
- average execution time
- error taxonomy distribution
- multi-query fallback rate

Acceptance criteria:

- zero systemic failures
- no material metric degradation without explicit approval

Rollback:

- revert to the last passing checkpoint

### Checkpoint 9: Cleanup and Hardening

Goal:

Leave the repository internally consistent after the migration.

Tasks:

- remove stale compatibility notes
- document the supported install flow
- update version mentions in README
- add migration notes for future upgrades
- ensure no dead code or old version comments remain

Acceptance criteria:

- repo documentation matches actual install/runtime behavior
- no contradictory dependency declarations remain

## Test Matrix

### Layer 1: Static and import checks

- package import
- graph import
- orchestrator import
- API module import
- runner import

### Layer 2: Unit compatibility checks

- typed state creation
- message helpers
- routing helpers
- planner structured output
- SQL validation blocking

### Layer 3: Runtime smoke tests

- workflow compile
- workflow invoke
- workflow stream
- SqliteSaver session checkpoint
- OpenAI model binding

### Layer 4: Interface smoke tests

- API `/health`
- API `/query`
- CLI health check
- CLI single query

### Layer 5: Behavioral regression

- regression slice
- full regression run
- evaluation metrics comparison

## Known High-Risk Areas

1. `SQLDatabaseToolkit`
2. tool-call payload shape on `AIMessage`
3. `with_structured_output(...)` schema parsing
4. SQLite checkpoint persistence across sessions
5. differences between exported `requirements.txt` and lock-driven installs

## Recommended PR Sequence

### PR 1

Dependency normalization only.

Contents:

- pin versions in `pyproject.toml`
- regenerate lock
- regenerate `requirements.txt`
- update README install notes

### PR 2

Compatibility smoke tests only.

Contents:

- add LangGraph runtime tests
- add LLM integration smoke tests
- add minimal API smoke tests

### PR 3

Upgrade fixes for runtime and integration layers.

Contents:

- code changes required to make the stack pass
- no behavior redesign

### PR 4

Regression validation and cleanup.

Contents:

- regression artifacts
- final docs cleanup
- migration summary

## Exit Criteria

The migration is complete only when all of the following are true:

- dependencies are internally consistent
- the project intentionally runs on `langgraph==1.1.10`
- orchestrator startup is stable
- API and CLI contracts are preserved
- regression suite shows no material breakage
- documentation reflects the real supported workflow

## Immediate Next Step

Implement PR 1 and PR 2 together only if you want faster feedback.

If minimizing risk is more important than speed, keep them separate:

1. normalize dependencies
2. add compatibility tests
3. upgrade and fix
4. run regression
