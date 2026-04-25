# DataVisSUS TXT2SQL Agent

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o--mini-412991.svg)](https://openai.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.6.6-purple.svg)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.13-009688.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL%20%2F%20DuckDB-336791.svg)](https://www.postgresql.org/)

> An AI-powered text-to-SQL system for Brazilian public healthcare data (DATASUS/SUS), built with LangGraph, OpenAI, FastAPI, and a dedicated web interface for natural-language analytics over hospital datasets.

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
- [System Design](#system-design)
- [Observability](#observability)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## Overview
**DataVisSUS TXT2SQL Agent** translates natural-language questions into executable SQL for Brazilian healthcare datasets. The system is designed for DATASUS-style analytical workloads and combines query classification, schema selection, guarded SQL generation, validation, repair, execution, and response synthesis inside a LangGraph workflow.

### Key Capabilities
- **Natural Language to SQL**: Converts Portuguese or English analytical questions into SQL queries.
- **Workflow Routing**: Distinguishes between database, conversational, schema, and clarification flows.
- **Schema-Aware Generation**: Selects relevant tables, loads schema context, and constrains SQL generation accordingly.
- **Multi-Step Recovery**: Repairs invalid SQL through validation and execution feedback loops.
- **Multi-Query Planning**: Supports plan gating, query planning, multi-query execution, verification, and result synthesis for more complex requests.
- **Multiple Interfaces**: CLI, REST API, and web frontend are available in the same repository.
- **Safety Guardrails**: Blocks non-`SELECT` execution and sanitizes generated SQL before execution.
- **Evaluation Pipeline**: Includes an agent-vs-baseline benchmark setup with execution accuracy metrics.

## Features
- **LangGraph Pipeline**: Stateful graph-based orchestration with checkpointed conversation memory.
- **OpenAI Integration**: Uses `gpt-4o-mini` by default for SQL and conversational responses.
- **Enhanced Table Discovery**: Combines table metadata and selection heuristics to narrow schema context.
- **Validation and Repair Loop**: Static validation plus retry-driven SQL repair before re-execution.
- **Session Memory**: Persists interaction history in SQLite for multi-turn usage.
- **FastAPI Service**: Exposes query, schema, models, and health endpoints.
- **Web Chat Interface**: Separate Node/Express frontend that connects to the API.
- **Evaluation Artifacts**: Stores raw evaluation runs, reports, and baseline artifacts for comparison.

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
    D --> E[plan_gate]

    E -->|query_planner| F[query_planner]
    E -->|reasoning| G[reasoning]
    E -->|generate_sql| H[generate_sql]
    E -->|response| R

    F -->|single| H
    F -->|complex single| G
    F -->|multi| I[multi_sql_executor]

    I --> J[multi_verifier]
    J -->|approved| K[result_synthesizer]
    J -->|fallback single| H

    G --> H
    H --> L[vote_sql]
    L --> M[validate_sql]
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
| **Language Model** | OpenAI `gpt-4o-mini` | SQL generation and conversational responses |
| **LLM Framework** | LangChain | LLM orchestration and SQL toolkit integration |
| **Graph Orchestration** | LangGraph `0.6.6` | Stateful workflow execution |
| **API Layer** | FastAPI | REST service for queries, schema, health, and models |
| **Frontend** | Node.js, Express, vanilla JS | Web chat interface for the agent |
| **Database Access** | SQLAlchemy, psycopg2, LangChain SQLDatabase | SQL execution against PostgreSQL or DuckDB |
| **Checkpoint Memory** | SQLite | Multi-turn session persistence |
| **Evaluation** | Custom EX / CM / EM metrics | Benchmarking agent and baseline performance |
| **Observability** | LangSmith, rotating file logs | Tracing and operational visibility |

## Project Structure
```bash
txt2sql_refactor_openai_v2/
├── src/
│   ├── agent/
│   │   ├── workflow.py              # LangGraph graph definition and routing
│   │   ├── orchestrator.py          # Main production orchestrator
│   │   ├── nodes.py                 # Core workflow node implementations
│   │   ├── query_planner.py         # Single vs multi-query planning
│   │   ├── plan_gate.py             # Planner gate before SQL generation
│   │   ├── validation.py            # SQL validation helpers
│   │   ├── execution.py             # SQL execution logic
│   │   ├── result_synthesizer.py    # Multi-query result synthesis
│   │   └── tools/                   # Enhanced SQL-related tools
│   ├── application/config/
│   │   ├── simple_config.py         # App and orchestrator defaults
│   │   ├── table_descriptions.py    # Table metadata and descriptions
│   │   └── table_templates.py       # Prompt templates and examples
│   ├── interfaces/
│   │   ├── api/main.py              # FastAPI entrypoint
│   │   └── cli/agent.py             # CLI entrypoint
│   ├── infrastructure/database/
│   │   └── connection_service.py    # Database connection services
│   ├── memory/                      # Example memory/vector store artifacts
│   └── utils/                       # Logging, SQL safety, classification utils
├── evaluation/                      # Evaluation runners, metrics, results
├── baselines/rich_prompt_baseline/  # Single-shot baseline implementation
├── frontend/                        # Web interface served by Node/Express
├── docs/                            # Papers, diagrams, reports
├── tests/                           # Safety and execution tests
├── requirements.txt                 # Python dependencies
└── README.md                        # This file
```

## Getting Started
### Prerequisites
- **Python**: 3.11 or higher
- **Node.js**: 16 or higher for the web frontend
- **OpenAI API Key**: Required for `gpt-4o-mini`
- **Database**: PostgreSQL is the default setup; DuckDB URLs are also accepted by the LLM manager

### Installation
1. **Clone the repository**
```bash
git clone <repository-url>
cd txt2sql_refactor_openai_v2
```

2. **Create and activate a virtual environment**
```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate
```

3. **Install Python dependencies**
```bash
pip install -r requirements.txt
```

4. **Install frontend dependencies** (optional)
```bash
cd frontend
npm install
cd ..
```

### Configuration
Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Expected variables:

```env
# OpenAI Configuration
OPENAI_API_KEY=sk-your_openai_key_here

# LangSmith Configuration
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_langsmith_api_key_here
LANGCHAIN_PROJECT=txt2sql

# Database Configuration
DATABASE_PATH=postgresql+psycopg2://postgres:your_password@localhost:5432/sihrd5
```

The application reads `DATABASE_URL` first when available, and falls back to `DATABASE_PATH`.

### Running the Application
1. **Run the CLI**
```bash
python src/interfaces/cli/agent.py
```

Single-query mode and debugging examples:

```bash
python src/interfaces/cli/agent.py --query "Quantas mortes ocorreram em 2022?"
python src/interfaces/cli/agent.py --query "Quantos hospitais existem?" --debug-steps
python src/interfaces/cli/agent.py --health-check
python src/interfaces/cli/agent.py --db-url "postgresql://user:pass@localhost:5432/sihrd5" --query "..."
```

2. **Run the API**
```bash
python src/interfaces/api/main.py
```

The API will be available at `http://localhost:8000`, with docs at `http://localhost:8000/docs`.

3. **Run the web interface**
```bash
cd frontend
npm start
```

The frontend will be available at `http://localhost:3000`.

## Usage
### Example Queries
**1. Mortality counting**
```text
Quantas mortes ocorreram em 2022?
```

**2. Demographic filtering**
```text
Qual é a idade média das mulheres que morreram?
```

**3. Infrastructure analysis**
```text
Quantos leitos de UTI existem em Minas Gerais?
```

**4. Ranking query**
```text
Quais foram as 5 cidades com mais mortes?
```

### API Endpoints
- `POST /api/v1/query` or `POST /query`: process a natural-language query
- `GET /api/v1/schema` or `GET /schema`: inspect table descriptions and schema summary
- `GET /api/v1/models` or `GET /models`: inspect configured models
- `GET /api/v1/health` or `GET /health`: check service health

Example request:

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query":"Quantas mortes ocorreram em 2022?","include_sql":true}'
```

### Tests
```bash
python -m pytest tests/ -v
python -m pytest tests/ --cov=src --cov-report=html
```

The current test suite covers SQL safety and execution blocking scenarios.

## Evaluation
The repository includes two evaluation paths:
- **LangGraph agent evaluation**: end-to-end workflow benchmark using the orchestrated agent.
- **Rich prompt baseline**: single-shot baseline for measuring the gain from graph orchestration.

### Metrics
| Metric | Description |
|---|---|
| **EX** | Execution Accuracy, based on result correctness |
| **CM** | Component Matching, based on SQL structure similarity |
| **EM** | Exact Match, based on SQL string-level equivalence |

### Running Evaluation
```bash
python evaluation/run_dag_evaluation.py
python evaluation/run_rich_prompt_baseline.py
python evaluation/generate_report.py
```

### Output Locations
```bash
evaluation/results/                       # Agent evaluation outputs and reports
baselines/rich_prompt_baseline/artifacts/ # Baseline execution artifacts
```

Ground truth files are stored in `evaluation/ground_truth.json` and `evaluation/ground_truth_v2.json`.

## System Design
### Query Routing
The workflow starts with query classification and routes requests into database, schema, conversational, or clarification paths. Database queries continue through schema selection and SQL generation, while conversational or clarification requests bypass SQL execution entirely.

### Plan Gate and Query Planner
Before generating SQL, the graph decides whether the request should proceed directly, use additional reasoning, or be decomposed into multiple SQL sub-queries. This is the main architectural difference from a simpler single-pass text-to-SQL agent.

### SQL Validation and Repair
Generated SQL is sanitized and checked before execution. Failures are routed through validation retries, repair nodes, and controlled re-execution to improve robustness without allowing unsafe statements.

### Memory and Sessions
The orchestrator stores checkpoint data in `data/chatbot_memory.db`, enabling conversation continuity and stateful LangGraph execution across requests.

## Observability
### Logging
Main logs are written under `logs/` and `evaluation/logs/`. Useful files include:
- `logs/orchestrator_v3.log`
- `evaluation/logs/txt2sql_api.log`
- `evaluation/logs/txt2sql_cli.log`
- `evaluation/logs/txt2sql_nodes.log`

### LangSmith
If `LANGSMITH_TRACING=true` is configured, the application emits traces for workflow execution, which is useful for debugging prompt behavior, retries, and performance bottlenecks.

## Contributing
Contributions should preserve the current architecture boundaries:
- Keep orchestration logic inside `src/agent/`.
- Keep app configuration centralized in `src/application/config/`.
- Keep interface-specific concerns inside `src/interfaces/`.
- Update evaluation artifacts or documentation when changing workflow behavior.

For larger behavior changes, validate both the agent path and the baseline path to avoid regressions in benchmark comparability.

## License
This project is licensed under the **MIT License**.

See [LICENSE](LICENSE) for the full text.

Copyright (c) 2026 Maicon Kevyn
