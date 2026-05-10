# DataVisSUS Text-to-SQL Agent

[![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue.svg)](https://www.python.org/)
[![OpenAI](https://img.shields.io/badge/OpenAI-gpt--4o--mini-412991.svg)](https://openai.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-%3E%3D1.1.10-purple.svg)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-%3E%3D0.115.13-009688.svg)](https://fastapi.tiangolo.com/)
[![Pydantic](https://img.shields.io/badge/Pydantic-%3E%3D2.11.7-e92063.svg)](https://docs.pydantic.dev/)
[![Apache ECharts](https://img.shields.io/badge/Apache%20ECharts-5.6.0-aa344d.svg)](https://echarts.apache.org/)

DataVisSUS is a research-oriented Text-to-SQL agent for Brazilian public healthcare analytics. It translates natural-language questions into executable SQL, validates the query against semantic and database constraints, executes it, and returns a natural-language answer with optional chart output.

The project is designed as an AI Engineering and AI Research artifact: the focus is not only generating SQL, but studying semantic robustness, tool-grounded execution, structured LLM outputs, evaluation methodology, ablations, and failure modes in hard analytical questions.

## Contents

- [What This Project Is](#what-this-project-is)
- [Architecture](#architecture)
- [Agent Workflow](#agent-workflow)
- [AI Engineering Design](#ai-engineering-design)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Evaluation and Research](#evaluation-and-research)
- [Observability](#observability)
- [License](#license)

## What This Project Is

This repository implements a LangGraph-based agent that answers analytical questions over DATASUS-style health data. The core workload is semantically difficult Text-to-SQL: mortality counts and rates, temporal comparisons, top-N rankings, denominator-sensitive metrics, anti-conditions, business rules, and domain-specific table/column selection.

The system is intentionally built to improve generalization rather than overfit a benchmark. It separates:

- **Intent routing** from SQL generation.
- **Table discovery** from schema retrieval.
- **Semantic planning** from SQL synthesis.
- **SQL generation** from validation and execution.
- **Chart intent** from default text answers.
- **Evaluation** from component ablation.

Supported interfaces:

- Interactive CLI.
- FastAPI API.
- Node/Express web chat frontend.
- Evaluation runners for DAG evaluation, regression, ablation, table selection, and chart generation.

## Architecture

![DataVisSUS Text-to-SQL Agent Architecture](assets/animated/flow_v09_research_clean_github_dark.svg)


The architecture is composed of:

- **Web frontend**: chat UI, optional SQL visibility, table rendering, and Apache ECharts rendering.
- **Agent Backend**: FastAPI plus the production LangGraph orchestrator.
- **LangGraph Orchestrator**: explicit state-machine workflow for routing, planning, SQL generation, validation, execution, repair, and response synthesis.
- **Semantic Layer**: reusable domain catalog, data profile, metric rules, join paths, macros, and SQL contract checks.
- **SQL tools and database runtime**: SQLDatabaseToolkit tools for schema, validation, and execution over the configured database.
- **Observability**: logs and optional MLflow tracking.

## Agent Workflow

The production graph is defined in [`src/agent/workflow.py`](src/agent/workflow.py). The main path is:

1. **Classify**
   - Determines whether the user message is `database`, `conversational`, `schema`, `clarification`, or `error`.
   - Database questions continue to table discovery.
   - Conversational questions go directly to response generation.

2. **Discover and Select Tables**
   - Implemented in [`src/agent/table_selection.py`](src/agent/table_selection.py).
   - Uses table metadata, heuristics, embeddings, and configurable LLM selection presets.
   - Current default preset is `llm_best`.

3. **Schema Context**
   - Implemented in [`src/agent/schema_node.py`](src/agent/schema_node.py).
   - Uses `sql_db_schema` and local SUS metadata to provide table/column context.

4. **Plan Gate and Semantic Plan**
   - `plan_gate` decides whether the query needs semantic planning or multi-query handling.
   - [`src/semantic/plan_schema.py`](src/semantic/plan_schema.py) defines the Pydantic `SemanticPlan` contract.
   - [`src/agent/semantic_planner.py`](src/agent/semantic_planner.py) reconciles heuristic and structured LLM semantic plans.

5. **SQL Reasoning and Generation**
   - [`src/agent/sql_generation.py`](src/agent/sql_generation.py) generates SQL using schema context, semantic plan guidance, chart plan guidance, and prompt rules.
   - SQL generation returns a Pydantic `SQLOutput` with `sql`, `reasoning`, and `confidence`.

6. **Validation**
   - [`src/agent/validation.py`](src/agent/validation.py) validates SQL using SQLDatabaseToolkit query checking plus semantic and contract validators.
   - Validation targets common semantic failures: wrong denominators, wrong output shape, invalid top-N grouping, wrong filters, and unsafe SQL.

7. **Execution**
   - [`src/agent/execution.py`](src/agent/execution.py) executes validated SQL through `sql_db_query`.
   - Non-`SELECT` SQL is blocked by safety checks.

8. **Repair Loop**
   - If validation or execution fails, repair can route back to SQL generation or validation.
   - Semantic repair guidance is stored in [`src/semantic/repair_guidance.yml`](src/semantic/repair_guidance.yml).

9. **Compose Answer**
   - Generates the final answer in natural language.
   - If the user explicitly requested a chart, the response may also include a structured chart payload.

## AI Engineering Design

### Pydantic Structured Outputs

Pydantic is used as a typed contract layer between LLM reasoning and deterministic code. This reduces ambiguous parsing and makes downstream validation explicit.

Important contracts:

| Contract | File | Purpose |
|---|---|---|
| `SemanticPlan` | [`src/semantic/plan_schema.py`](src/semantic/plan_schema.py) | Semantic intent, metrics, dimensions, filters, answer shape, constraints |
| `SemanticPlannerOutput` | [`src/agent/semantic_planner.py`](src/agent/semantic_planner.py) | LLM-reconciled semantic plan with confidence and reasoning |
| `SQLOutput` | [`src/agent/sql_generation.py`](src/agent/sql_generation.py) | Structured SQL generation result |
| `VisualizationIntent`, `ChartPlan`, `ChartSpec` | [`src/visualization/schema.py`](src/visualization/schema.py) | Explicit chart generation contracts |
| API request/response models | [`src/interfaces/api/main.py`](src/interfaces/api/main.py) | FastAPI data contracts |

The central structured-output adapter is:

```python
structured_llm = self._llm.with_structured_output(output_schema)
```

in [`src/agent/llm_manager.py`](src/agent/llm_manager.py).

### Tool Calling and Tool-Grounded Execution

The agent uses LangChain `SQLDatabaseToolkit` tools and binds them to the OpenAI model through `bind_tools`. The workflow also invokes tools directly inside deterministic graph nodes, which keeps the critical path inspectable.

Tools used in the pipeline:

| Tool | Main Step | Purpose |
|---|---|---|
| `sql_db_list_tables` / enhanced list tool | Discover and select tables | Database table inventory with curated descriptions |
| `sql_db_schema` | Schema context | Table schema retrieval for selected tables |
| `sql_db_query_checker` | Validate | LLM-assisted SQL query checking |
| `sql_db_query` | Execute | Query execution against the configured database |

The tool setup is implemented in [`src/agent/llm_manager.py`](src/agent/llm_manager.py). Tool execution records are persisted in the graph state through `ToolCallResult`, making tool usage observable and evaluable.

### Semantic Layer

The semantic layer is the main generalization mechanism. It is not intended to memorize benchmark questions. It encodes reusable domain abstractions:

- Metrics and denominator rules.
- Domain filters and code mappings.
- Join paths.
- SQL macro expectations.
- Data profiles.
- Answer-shape constraints.
- Semantic repair guidance.
- AST-level SQL contract checks.

Key files:

- [`src/semantic/catalog.yml`](src/semantic/catalog.yml)
- [`src/semantic/catalog.py`](src/semantic/catalog.py)
- [`src/semantic/planner.py`](src/semantic/planner.py)
- [`src/semantic/plan_reconciler.py`](src/semantic/plan_reconciler.py)
- [`src/semantic/contract_validator.py`](src/semantic/contract_validator.py)
- [`src/semantic/sql_ast.py`](src/semantic/sql_ast.py)
- [`src/semantic/profiles/generated_profile.json`](src/semantic/profiles/generated_profile.json)

### Explicit Chart Generation

Charts are opt-in. The agent should only generate a chart when the user explicitly asks for one.

The chart pipeline is:

1. Detect visualization intent.
2. Build a structured `ChartPlan`.
3. Generate SQL shaped for the visual contract.
4. Validate chart compatibility.
5. Return `ChartSpec`.
6. Convert `ChartSpec` to Apache ECharts options for the frontend.

Relevant files:

- [`src/visualization/intent.py`](src/visualization/intent.py)
- [`src/visualization/planner.py`](src/visualization/planner.py)
- [`src/visualization/schema.py`](src/visualization/schema.py)
- [`src/visualization/echarts.py`](src/visualization/echarts.py)
- [`frontend/public/app.js`](frontend/public/app.js)

## Technology Stack

Version constraints are defined in [`pyproject.toml`](pyproject.toml) and [`frontend/package.json`](frontend/package.json).

| Layer | Technology | Version / Constraint | Role |
|---|---|---:|---|
| Language | Python | `>=3.11` | Backend, agent, evaluation |
| Model provider | OpenAI | SDK `>=1.55.0` | LLM runtime |
| Default model | `gpt-4o-mini` | Config default | SQL, semantic planning, response synthesis |
| Orchestration | LangGraph | `>=1.1.10` | Explicit graph workflow |
| LLM/tool framework | LangChain Core | `>=0.3.74` | Messages, tools, structured calls |
| SQL tools | LangChain Community | `>=0.3.25` | SQLDatabaseToolkit |
| OpenAI integration | LangChain OpenAI | `>=0.3.32` | Chat model and structured output |
| API | FastAPI | `>=0.115.13` | REST API |
| ASGI runtime | Uvicorn | `>=0.34.3` | API serving |
| Data contracts | Pydantic | `>=2.11.7` | API models, semantic plans, chart specs |
| Experiment tracking | MLflow | `>=2.15.0` | Optional run and ablation tracking |
| Database access | SQLAlchemy | `2.0.41` | DB engine abstraction |
| PostgreSQL driver | psycopg2-binary | `>=2.9.10` | PostgreSQL execution |
| Local analytical DB | DuckDB | `1.4.4` | Local/analytical database runtime |
| DuckDB SQLAlchemy | duckdb-engine | `0.17.0` | DuckDB URL support |
| Embeddings | sentence-transformers | `>=2.6.1` | Table-selection embedding stage |
| Frontend runtime | Node.js | `>=16` | Web interface server |
| Web server | Express | `^4.18.2` | Frontend proxy/server |
| Charts | Apache ECharts | `5.6.0` via CDN | SVG chart rendering in UI |
| Quality | Ruff | `>=0.11.0` | Lint and formatting |
| Tests | pytest | `>=8.4.2` | Unit and regression tests |

## Project Structure

```bash
txt2sql_refactor_openai_v2/
├── src/
│   ├── agent/
│   │   ├── workflow.py              # LangGraph state graph
│   │   ├── orchestrator.py          # Production orchestrator and session handling
│   │   ├── classification.py        # Query routing
│   │   ├── table_selection.py       # Table discovery and selection
│   │   ├── schema_node.py           # Schema retrieval and enrichment
│   │   ├── semantic_planner.py      # Structured semantic plan reconciliation
│   │   ├── sql_generation.py        # Reasoning and structured SQL output
│   │   ├── validation.py            # SQL and semantic validation
│   │   ├── execution.py             # Tool-grounded SQL execution
│   │   ├── query_planner.py         # Single vs multi-query planning
│   │   ├── multi_executor.py        # Multi-query execution path
│   │   ├── result_synthesizer.py    # Multi-result answer synthesis
│   │   └── tools/                   # Custom LangChain tools
│   ├── application/
│   │   ├── config/                  # Runtime config and table metadata
│   │   └── prompts/                 # Versioned prompt catalogs
│   ├── interfaces/
│   │   ├── api/main.py              # FastAPI app
│   │   └── cli/agent.py             # CLI interface
│   ├── semantic/                    # Semantic catalog, plans, validators, profiles
│   ├── visualization/               # Chart intent, planning, validation, ECharts adapter
│   └── utils/                       # Logging, SQL safety, helper utilities
├── evaluation/
│   ├── runners/                     # DAG, ablation, regression, chart, table-selection runners
│   ├── dag/                         # Evaluation DAG tasks
│   ├── metrics/                     # EX, CM, EM and SQL comparison metrics
│   ├── ablation/results/            # Ablation outputs
│   ├── table_selection/             # Table-selection benchmark
│   └── visualization/               # Chart evaluation artifacts
├── frontend/                        # Node/Express + vanilla JS web UI
├── assets/animated/                 # README architecture diagrams
├── data/                            # SQLite checkpoint DB
├── logs/                            # Runtime logs
├── tests/                           # Unit tests
├── pyproject.toml
├── uv.lock
└── README.md
```

## Quick Start

### Prerequisites

- Python 3.11 or higher.
- Node.js 16 or higher for the web UI.
- OpenAI API key.
- PostgreSQL or DuckDB-compatible database URL.

### Installation

Clone the repository:

```bash
git clone <repository-url>
cd txt2sql_refactor_openai_v2
```

Install Python dependencies:

```bash
uv sync --extra dev
source .venv/bin/activate
```

Fallback without `uv`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

### Configuration

Create the environment file:

```bash
cp .env.example .env
```

Typical variables:

```env
OPENAI_API_KEY=sk-your_openai_key_here

# Preferred
DATABASE_URL=postgresql+psycopg2://postgres:your_password@localhost:5432/sihrd5

# Optional fallback if DATABASE_URL is not set
DATABASE_PATH=duckdb:///path/to/local.duckdb

# Optional observability
MLFLOW_TRACKING_URI=sqlite:///mlflow.db
MLFLOW_EXPERIMENT=txt2sql-agent
```

The app resolves the database in this order:

1. `DATABASE_URL`
2. `DATABASE_PATH`

### Run the CLI

Interactive mode:

```bash
python src/interfaces/cli/agent.py
```

Single query:

```bash
python src/interfaces/cli/agent.py --query "Quantas mortes ocorreram em 2022?"
```

Debug mode:

```bash
python src/interfaces/cli/agent.py \
  --query "Quais foram os 5 municípios com mais mortes?" \
  --debug-steps
```

Health check:

```bash
python src/interfaces/cli/agent.py --health-check
```

### Run the API

```bash
python src/interfaces/api/main.py
```

API:

- `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`

### Run the Web UI

```bash
cd frontend
npm start
```

Frontend:

- `http://localhost:3000`

## Usage

### Example Questions

```text
Quantas mortes ocorreram em 2022?
Qual é a idade média das mulheres que morreram?
Quais foram os 5 municípios com mais mortes?
Gere um gráfico de pizza mostrando as mortes entre homens e mulheres.
Compare mortes por sexo nos últimos 5 anos em um gráfico de barras.
```

### API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/query` or `/query` | Run an agent query |
| `GET` | `/api/v1/schema` or `/schema` | Inspect schema context |
| `GET` | `/api/v1/models` or `/models` | Inspect model configuration |
| `GET` | `/api/v1/health` or `/health` | Health check |

Example:

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query":"Quantas mortes ocorreram em 2022?","include_sql":true}'
```

### Local Quality Checks

The GitHub Actions `Lint + Unit Tests` job runs:

```bash
uv run ruff check src/
uv run ruff format --check src/
uv run pytest tests/ \
  --ignore=tests/test_agent_improvements.py \
  --ignore=tests/test_openai_api_isolated.py \
  -q
```

Useful focused checks for semantic work:

```bash
uv run pytest tests/test_semantic_layer.py \
  tests/test_semantic_plan_reconciliation.py \
  tests/test_sql_contract_validator.py \
  tests/test_sql_execution_block.py -q
```

## Evaluation and Research

The evaluation system is designed for scientific error analysis, not only leaderboard-style execution accuracy.

### Evaluation Modes

| Mode | Runner | Purpose |
|---|---|---|
| DAG evaluation | `evaluation.runners.run_dag_evaluation` | End-to-end agent quality |
| Ablation | `evaluation.runners.run_ablation` | Component-level impact analysis |
| Regression | `evaluation.runners.run_regression` | CI or targeted quality gates |
| Table selection | `evaluation.runners.run_table_selection_eval` | Isolated table-selection quality |
| Chart evaluation | `evaluation.runners.run_chart_evaluation` | Visualization intent and chart spec quality |
| Rich prompt baseline | `evaluation/run_rich_prompt_baseline.py` | Single-shot baseline comparison |

### Metrics

| Metric | Meaning |
|---|---|
| `EX` | Execution Accuracy: result-level correctness |
| `CM` | Component Matching: SQL structure similarity |
| `EM` | Exact Match: SQL string-level equivalence |

The project also produces failure lists, detailed outputs, ablation reports, chart evaluation artifacts, and logs. These are used to identify semantic error classes such as wrong output shape, wrong aggregation grain, missing anti-condition, wrong temporal comparison, and incorrect denominator.

### Run Evaluations

```bash
python -m evaluation.runners.run_dag_evaluation \
  --ground-truth evaluation/ground_truth_v2.json \
  --workers 2

python -m evaluation.runners.run_ablation \
  --dataset evaluation/ground_truth_v2.json \
  --workers 4

python -m evaluation.runners.run_regression --threshold 0.90
python -m evaluation.runners.run_table_selection_eval
python -m evaluation.runners.run_chart_evaluation
python evaluation/run_rich_prompt_baseline.py
python evaluation/generate_report.py
```

Compatibility note:

- `evaluation/run_dag_evaluation.py` is kept as a wrapper.
- The canonical runner is [`evaluation/runners/run_dag_evaluation.py`](evaluation/runners/run_dag_evaluation.py).

### Output Locations

```bash
evaluation/results/dag_evaluation_<id>/       # DAG evaluation run folders
evaluation/ablation/results/<run_id>/         # Ablation outputs and checkpoints
evaluation/table_selection/results/<run_id>/  # Table-selection benchmark outputs
evaluation/visualization/results/             # Chart evaluation outputs
baselines/rich_prompt_baseline/artifacts/     # Baseline artifacts
evaluation/logs/                              # Evaluation runner logs
```

Ground-truth and regression datasets:

- [`evaluation/ground_truth.json`](evaluation/ground_truth.json)
- [`evaluation/ground_truth_v2.json`](evaluation/ground_truth_v2.json)
- [`evaluation/regression_set.json`](evaluation/regression_set.json)
- [`evaluation/table_selection/table_selection_gold.json`](evaluation/table_selection/table_selection_gold.json)
- [`evaluation/visualization/chart_gold.json`](evaluation/visualization/chart_gold.json)

### Research Principles

Current development follows these constraints:

- Do not add benchmark-question-specific rules.
- Prefer reusable semantic contracts over ground-truth memorization.
- Use ablation before attributing gains or regressions to a component.
- Track easy, medium, and hard questions separately.
- Treat hard-query failures as semantic failures first, not just prompt failures.
- Validate new components on real agent runs, not only isolated unit tests.

## Observability

### Logging

Runtime logs are written under `logs/` and `evaluation/logs/`.

Common files:

- `logs/txt2sql_api.log`
- `logs/txt2sql_cli.log`
- `logs/txt2sql_nodes.log`
- `logs/orchestrator_v3.log`
- `evaluation/logs/txt2sql_orchestrator.log`

### MLflow

MLflow is optional. When `MLFLOW_TRACKING_URI` is configured, the agent can log query runs and ablation experiments through [`src/agent/mlflow_tracker.py`](src/agent/mlflow_tracker.py).

The project does not require LangSmith.

### Session Memory

LangGraph checkpoints are persisted with SQLite in:

```bash
data/chatbot_memory.db
```

This enables multi-turn session continuity across requests.

## License

This project is licensed under the MIT License.
