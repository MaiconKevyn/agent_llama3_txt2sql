# DataVisSUS TXT2SQL Agent

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o--mini-412991.svg)](https://openai.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.1.10%2B-purple.svg)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.13-009688.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL%20%2F%20DuckDB-336791.svg)](https://www.postgresql.org/)

Text-to-SQL for Brazilian public healthcare analytics, built around a LangGraph workflow with OpenAI models, a semantic layer, FastAPI, a CLI, and a lightweight web frontend.

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Running the Application](#running-the-application)
- [Usage](#usage)
- [Evaluation](#evaluation)
- [Observability](#observability)
- [License](#license)

## Overview
The agent translates natural-language questions into SQL for DATASUS-style analytical workloads. The current pipeline combines query classification, table discovery, schema enrichment, semantic planning, SQL generation, SQL/semantic validation, repair, execution, and response synthesis inside a stateful LangGraph workflow.

The implementation is intentionally oriented toward semantic robustness rather than benchmark-specific tuning. The semantic layer stores reusable metric definitions, domain filters, join expectations, SQL macros, and validation rules that can be applied to new questions without hardcoding individual ground-truth examples.

## Features
- Natural language to SQL in Portuguese or English.
- Query routing for database, conversational, schema, and clarification paths.
- Three-stage table selection with heuristics, multilingual embeddings, and optional LLM fallback.
- Schema-aware SQL generation with SUS-specific table metadata and semantic catalog guidance.
- Semantic planning before SQL generation for metrics, filters, grouping, ordering, limits, joins, and expected output shape.
- Domain-aware validation for mortality denominators, top-N/grouping patterns, socioeconomic metric filters, catalog-count questions, and date/age filters.
- Multi-step recovery through validation and execution feedback loops.
- Multi-query planning and synthesis for more complex analytical requests.
- Multiple interfaces in one repository: CLI, REST API, and web frontend.
- Execution safety guardrails that block non-`SELECT` SQL.
- Built-in evaluation, regression, and ablation runners.
- Optional MLflow tracking for query runs and ablation experiments.

## Architecture
```mermaid
flowchart TD
    START([User Query]) --> A[classify_query]

    A -->|database| B[list_tables]
    A -->|schema| B
    A -->|conversational| R[generate_response]
    A -->|clarification| C[clarification]
    A -->|error| R

    B --> D[get_schema]
    D -->|database query| E[plan_gate]
    D -->|schema response or error| R
    E --> S[semantic_planner]

    S -->|query_planner| F[query_planner]
    S -->|reasoning| G[reasoning]
    S -->|generate_sql| H[generate_sql]

    F -->|single| H
    F -->|complex single| G
    F -->|multi| I[multi_sql_executor]

    I --> J[multi_verifier]
    J -->|approved| K[result_synthesizer]
    J -->|fallback single| H

    G --> H
    H --> M[validate_sql]
    M -->|valid| N[execute_sql]
    M -->|retry generation| O[repair_sql]
    M -->|retry validation| M
    M -->|error| R

    N -->|success| R
    N -->|retry generation| O
    N -->|retry validation| M
    N -->|retry execution| N
    N -->|error| R

    O -->|replan| G
    O -->|revalidate| M

    K --> END([Final Response])
    R --> END
    C --> END
```

## Technology Stack
| Component | Technology | Purpose |
|---|---|---|
| Language model | OpenAI `gpt-4o-mini` by default | SQL generation and conversational responses |
| LLM framework | LangChain | Model/tool integration and SQL toolkit support |
| Graph orchestration | LangGraph `>=1.1.10` | Stateful workflow execution |
| API layer | FastAPI | REST endpoints for query, schema, models, and health |
| Frontend | Node.js, Express, vanilla JS | Web chat interface |
| Database access | SQLAlchemy, psycopg2, LangChain SQLDatabase | SQL execution against PostgreSQL; DuckDB URLs are also accepted |
| Semantic layer | YAML catalog + Pydantic models + SQL AST inspection | Domain metrics, join rules, macros, semantic plan validation, and SQL contract checks |
| Session memory | `langgraph-checkpoint-sqlite` + SQLite | Session checkpoint persistence in `data/chatbot_memory.db` |
| Evaluation | Custom EX / CM / EM metrics | Benchmarking, regression, and ablation analysis |
| Observability | Rotating file logs, optional MLflow | Operational visibility and experiment tracking |

## Project Structure
```bash
txt2sql_refactor_openai_v2/
├── src/
│   ├── agent/
│   │   ├── workflow.py              # LangGraph workflow definition
│   │   ├── orchestrator.py          # Main production orchestrator
│   │   ├── sql_generation.py        # SQL generation and reasoning helpers
│   │   ├── validation.py            # SQL validation and repair helpers
│   │   ├── execution.py             # SQL execution logic
│   │   ├── query_planner.py         # Single vs multi-query planning
│   │   ├── result_synthesizer.py    # Multi-query result synthesis
│   │   └── mlflow_tracker.py        # Optional MLflow integration
│   ├── application/config/          # App config and SUS table metadata
│   ├── application/prompts/         # Versioned table-selection prompt catalog
│   ├── interfaces/
│   │   ├── api/main.py              # FastAPI entrypoint
│   │   └── cli/agent.py             # CLI entrypoint
│   ├── infrastructure/database/     # Database connection services
│   ├── memory/                      # Example memory/vector store artifacts
│   ├── semantic/
│   │   ├── catalog.yml              # Reusable metrics, dimensions, macros, rules
│   │   ├── planner.py               # Heuristic semantic plan extraction
│   │   ├── plan_reconciler.py       # Reconcile heuristic and LLM semantic plans
│   │   ├── validators.py            # Semantic plan and SQL-shape validators
│   │   ├── contract_validator.py    # AST-level SQL contract checks
│   │   └── repair_guidance.yml      # Semantic repair hints by failure type
│   └── utils/                       # Logging, SQL safety, classification utils
├── baselines/rich_prompt_baseline/  # Single-shot baseline implementation
├── evaluation/
│   ├── dag/                         # DAG evaluation pipeline tasks
│   ├── metrics/                     # EX, CM, EM, and SQL parsing helpers
│   ├── runners/                     # DAG, regression, ablation, table-selection runners
│   ├── ablation/results/            # Ablation run folders and item checkpoints
│   ├── results/                     # DAG and legacy evaluation outputs
│   └── table_selection/             # Table-selection benchmark data
├── frontend/                        # Web interface served by Node/Express
├── data/                            # Runtime SQLite checkpoint database
├── logs/                            # Application logs
├── mlruns/                          # Local MLflow artifacts when enabled
├── tests/                           # Unit tests
├── pyproject.toml                   # Canonical Python dependency spec
├── uv.lock                          # Locked dependency graph for uv
└── README.md
```

## Getting Started
### Prerequisites
- Python 3.11 or higher
- Node.js 16 or higher for the frontend
- An OpenAI API key
- A PostgreSQL database URL for normal usage

DuckDB URLs are also accepted by the connection layer, but PostgreSQL is the primary deployment path used by the current CLI, API, and evaluation flows.

### Installation
1. Clone the repository.

```bash
git clone <repository-url>
cd txt2sql_refactor_openai_v2
```

2. Install Python dependencies.

Recommended:

```bash
uv sync --extra dev
source .venv/bin/activate
```

Fallback:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Install frontend dependencies if you want the web UI.

```bash
cd frontend
npm install
cd ..
```

### Configuration
Copy the example environment file:

```bash
cp .env.example .env
```

Typical variables:

```env
# Required
OPENAI_API_KEY=sk-your_openai_key_here

# Database
DATABASE_URL=postgresql+psycopg2://postgres:your_password@localhost:5432/sihrd5

# Optional fallback if DATABASE_URL is not set
DATABASE_PATH=postgresql+psycopg2://postgres:your_password@localhost:5432/sihrd5

# Optional MLflow tracking
MLFLOW_TRACKING_URI=sqlite:///mlflow.db
MLFLOW_EXPERIMENT=txt2sql-agent
```

The application prefers `DATABASE_URL` and falls back to `DATABASE_PATH`.

### Running the Application
Run the CLI:

```bash
python src/interfaces/cli/agent.py
```

Single-query and debug examples:

```bash
python src/interfaces/cli/agent.py --query "Quantas mortes ocorreram em 2022?"
python src/interfaces/cli/agent.py --query "Quantos hospitais existem?" --debug-steps
python src/interfaces/cli/agent.py --health-check
python src/interfaces/cli/agent.py --db-url "postgresql://user:pass@localhost:5432/sihrd5" --query "..."
python src/interfaces/cli/agent.py --table-selection-preset llm_best --query "..."
```

Run the API:

```bash
python src/interfaces/api/main.py
```

The API is exposed on `http://localhost:8000`, with docs at `http://localhost:8000/docs`.

Run the web interface:

```bash
cd frontend
npm start
```

The frontend is exposed on `http://localhost:3000`.

## Usage
### Example Queries
```text
Quantas mortes ocorreram em 2022?
Qual e a idade media das mulheres que morreram?
Quantos leitos de UTI existem em Minas Gerais?
Quais foram as 5 cidades com mais mortes?
```

### API Endpoints
- `POST /api/v1/query` or `POST /query`
- `GET /api/v1/schema` or `GET /schema`
- `GET /api/v1/models` or `GET /models`
- `GET /api/v1/health` or `GET /health`

Example request:

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query":"Quantas mortes ocorreram em 2022?","include_sql":true}'
```

### Tests and Local Quality Checks
The CI job `Lint + Unit Tests` currently runs:

```bash
uv run ruff check src/
uv run ruff format --check src/
uv run pytest tests/ \
  --ignore=tests/test_agent_improvements.py \
  --ignore=tests/test_openai_api_isolated.py \
  -q
```

The test suite covers routing, orchestration support, SQL safety, execution blocking, CLI session behavior, logging, and MLflow helpers.

Useful focused checks while changing the semantic layer:

```bash
uv run pytest tests/test_semantic_layer.py \
  tests/test_semantic_plan_reconciliation.py \
  tests/test_sql_contract_validator.py \
  tests/test_sql_execution_block.py -q
```

## Evaluation
The repository includes five complementary evaluation paths:
- End-to-end DAG evaluation of the LangGraph agent
- Rich prompt baseline evaluation
- Regression runs for CI or targeted benchmark slices
- Ablation runs to measure the impact of specific pipeline components
- Dedicated table-selection benchmark runs

### Metrics
| Metric | Description |
|---|---|
| EX | Execution Accuracy, based on result correctness |
| CM | Component Matching, based on SQL structure similarity |
| EM | Exact Match, based on SQL string-level equivalence |

### Running Evaluation
```bash
python -m evaluation.runners.run_dag_evaluation --ground-truth evaluation/ground_truth_v2.json --workers 2
python evaluation/run_rich_prompt_baseline.py
python -m evaluation.runners.run_regression --threshold 0.90
python -m evaluation.runners.run_ablation --dataset evaluation/ground_truth_v2.json --workers 4
python -m evaluation.runners.run_table_selection_eval
python evaluation/generate_report.py
```

`evaluation/run_dag_evaluation.py` is kept as a compatibility wrapper. The canonical DAG runner is `evaluation/runners/run_dag_evaluation.py`.

### Output Locations
```bash
evaluation/results/dag_evaluation_<id>/       # DAG evaluation run folders
evaluation/ablation/results/<run_id>/         # Ablation outputs and item checkpoints
evaluation/table_selection/results/<run_id>/  # Table-selection benchmark outputs
baselines/rich_prompt_baseline/artifacts/     # Baseline artifacts
evaluation/logs/                              # Evaluation runner logs
```

Ground-truth and slice datasets are stored in `evaluation/ground_truth.json`, `evaluation/ground_truth_v2.json`, `evaluation/regression_set.json`, and the targeted slice files under `evaluation/*slice*.json`.

## Observability
### Logging
Runtime logs are written under `logs/` and `evaluation/logs/`. Common files include:
- `logs/orchestrator_v3.log`
- `logs/txt2sql_api.log`
- `logs/txt2sql_cli.log`
- `logs/txt2sql_nodes.log`
- `evaluation/logs/txt2sql_orchestrator.log`

### MLflow
The project no longer uses LangSmith.

When `MLFLOW_TRACKING_URI` is configured, the agent can log query runs and ablation experiments through `src/agent/mlflow_tracker.py`. Tracking is optional and the application remains operational when MLflow is not configured.

### Session Memory
LangGraph checkpoints are persisted with SQLite in `data/chatbot_memory.db`, enabling multi-turn session continuity across requests.

## License
This project is licensed under the MIT License.
