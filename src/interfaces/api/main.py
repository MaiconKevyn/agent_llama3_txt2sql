"""
FastAPI REST API for Text-to-SQL Agent

Uses the simple SQL orchestrator directly, with no subprocess overhead.
"""

import sys
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

# Allow running both as `python -m ...` and `python src/interfaces/api/main.py`
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")


# ---------------------------------------------------------------------------
# Lifespan: initialise the orchestrator once at startup
# ---------------------------------------------------------------------------
_orchestrator = None
_database_engine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _orchestrator
    from src.agent.orchestrator import create_production_orchestrator

    _orchestrator = create_production_orchestrator()
    yield
    # No teardown needed (DB connections are pooled by SQLAlchemy)


app = FastAPI(
    title="DATASUS Text-to-SQL API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    query: str
    include_sql: bool = True
    session_id: str | None = None
    debug: bool = False
    chart_from_last_result: bool = False
    table_context: "TableContext | None" = None


class TableContext(BaseModel):
    table_schema: str
    table_name: str


class QueryResponse(BaseModel):
    success: bool
    status: str
    answer: str
    response: str
    sql: str | None = None
    sql_query: str | None = None
    execution_time: float
    timestamp: str
    session_id: str | None = None
    chart: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    debug: dict[str, Any] | None = None


class SchemaResponse(BaseModel):
    schema_text: str = Field(serialization_alias="schema")
    tables: list[str]
    selected_table: str | None = None
    timestamp: str


class ModelsResponse(BaseModel):
    available_models: dict[str, list[str]]
    current_model: dict[str, Any]
    timestamp: str


class DatabaseTableSummary(BaseModel):
    table_schema: str
    table_name: str
    table_type: str
    row_count: int | None = None
    classification: str | None = None


class DatabaseOverviewResponse(BaseModel):
    database_url: str
    tables: list[DatabaseTableSummary]
    generated_docs: list[str]
    timestamp: str


class DatabaseColumn(BaseModel):
    ordinal_position: int
    column_name: str
    data_type: str
    is_nullable: str | None = None


class DatabaseTableDetailResponse(BaseModel):
    table_schema: str
    table_name: str
    columns: list[DatabaseColumn]
    sample_columns: list[str]
    sample_rows: list[dict[str, Any]]
    sample_limit: int
    timestamp: str


class DatabaseQueryRequest(BaseModel):
    sql: str
    limit: int = Field(default=100, ge=1, le=500)


class DatabaseQueryResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    limit: int
    sql: str
    execution_time: float
    timestamp: str


SAFE_INTERNAL_AGENT_ERROR = (
    "Nao foi possivel processar sua consulta com seguranca. "
    "Tente refinar o recorte ou peca a resposta de outra forma."
)

INTERNAL_ERROR_MARKERS = (
    "SEMANTIC PLAN ERROR",
    "CHART PLAN ERROR",
    "Binder Error",
    "Catalog Error",
    "Parser Error",
    "Traceback",
    "sqlalchemy",
    "duckdb",
    "KeyError",
    "ValueError",
    "Internal Server Error",
)


def _contains_internal_error(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in INTERNAL_ERROR_MARKERS)


def _sanitize_user_response(text: str | None) -> str:
    if _contains_internal_error(text):
        return SAFE_INTERNAL_AGENT_ERROR
    return text or "Resposta nao disponivel"


def _build_query_response(
    result: dict[str, Any], started_at: float, session_id: str | None
) -> QueryResponse:
    success = bool(result.get("success"))
    raw_answer = result.get("response") or result.get("error_message") or "Resposta nao disponivel"
    answer = _sanitize_user_response(raw_answer)
    sql_query = result.get("sql_query")
    metadata = result.get("metadata", {}) or {}

    return QueryResponse(
        success=success,
        status="success" if success else "error",
        answer=answer,
        response=answer,
        sql=sql_query,
        sql_query=sql_query,
        execution_time=round(time.time() - started_at, 2),
        timestamp=datetime.now().isoformat(),
        session_id=session_id or metadata.get("session_id"),
        chart=result.get("chart"),
        metadata=metadata,
        debug=result.get("debug"),
    )


_DEBUG_NODE_TITLES = {
    "classify_query": "Classification",
    "list_tables": "Table Discovery",
    "get_schema": "Schema",
    "plan_gate": "Plan Gate",
    "query_planner": "Query Planner",
    "reasoning": "Reasoning",
    "semantic_planner": "Semantic Planner",
    "generate_sql": "SQL Generation",
    "validate_sql": "SQL Validation",
    "repair_sql": "SQL Repair",
    "execute_sql": "SQL Execution",
    "multi_executor": "Multi Query Execution",
    "multi_verifier": "Multi Query Verification",
    "result_synthesizer": "Result Synthesis",
    "generate_response": "Response",
    "clarification": "Clarification",
    "error": "Error",
}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="json", exclude_none=True))
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _node_state_value(node_state: dict[str, Any], key: str) -> Any:
    value = node_state.get(key)
    return _json_safe(value) if value is not None else None


def _execution_debug_data(node_state: dict[str, Any]) -> dict[str, Any]:
    execution = _json_safe(node_state.get("sql_execution_result")) or {}
    if not isinstance(execution, dict):
        return {"execution": execution}
    results = execution.get("results") or []
    return {
        "success": execution.get("success"),
        "row_count": execution.get("row_count", len(results) if isinstance(results, list) else 0),
        "execution_time": execution.get("execution_time"),
        "error_message": execution.get("error_message"),
        "preview": results[:3] if isinstance(results, list) else results,
    }


def _debug_step_data(node_name: str, node_state: dict[str, Any]) -> dict[str, Any]:
    metadata = _json_safe(node_state.get("response_metadata")) or {}
    data: dict[str, Any] = {}

    if node_name == "error":
        data["current_error"] = (
            _node_state_value(node_state, "current_error")
            or _node_state_value(node_state, "error")
            or _node_state_value(node_state, "value")
        )
    elif node_name == "classify_query":
        data["route"] = _node_state_value(node_state, "query_route")
        data["classification"] = _node_state_value(node_state, "classification")
    elif node_name == "list_tables":
        data["available_tables"] = _node_state_value(node_state, "available_tables") or []
        data["selected_tables"] = _node_state_value(node_state, "selected_tables") or []
    elif node_name == "get_schema":
        schema_context = node_state.get("schema_context") or ""
        data["schema_context_length"] = len(schema_context)
        data["selected_tables"] = _node_state_value(node_state, "selected_tables") or []
    elif node_name in {"plan_gate", "semantic_planner"}:
        data["plan_type"] = _node_state_value(node_state, "plan_type")
        data["semantic_plan"] = _node_state_value(node_state, "semantic_plan")
        if metadata.get("semantic_planner"):
            data["semantic_planner"] = metadata["semantic_planner"]
    elif node_name in {"generate_sql", "repair_sql"}:
        data["generated_sql"] = _node_state_value(node_state, "generated_sql")
        data["selected_tables"] = _node_state_value(node_state, "selected_tables") or []
        if metadata.get("semantic_repair"):
            data["semantic_repair"] = metadata["semantic_repair"]
        if metadata.get("repair_attempts"):
            data["repair_attempts"] = metadata["repair_attempts"]
    elif node_name == "validate_sql":
        data["validated_sql"] = _node_state_value(node_state, "validated_sql")
        data["validation_errors"] = _node_state_value(node_state, "validation_errors") or []
        if metadata.get("semantic_validation"):
            data["semantic_validation"] = metadata["semantic_validation"]
    elif node_name == "execute_sql":
        data.update(_execution_debug_data(node_state))
    elif node_name == "generate_response":
        data["final_response"] = _node_state_value(
            node_state, "final_response"
        ) or _node_state_value(node_state, "response")
        data["success"] = _node_state_value(node_state, "success")
    else:
        for key in (
            "current_phase",
            "completed_phases",
            "current_error",
            "generated_sql",
            "validated_sql",
            "final_sql_query",
            "final_response",
        ):
            value = _node_state_value(node_state, key)
            if value not in (None, [], {}):
                data[key] = value

    current_error = _node_state_value(node_state, "current_error")
    if current_error:
        data["current_error"] = current_error
    return data


def _build_debug_payload_from_updates(updates: list[dict[str, Any]]) -> dict[str, Any]:
    steps = []
    for update in updates:
        for node_name, node_state in update.items():
            if not isinstance(node_state, dict):
                node_state = {"value": node_state}
            current_error = node_state.get("current_error")
            node_failed = node_name == "error"
            steps.append(
                {
                    "index": len(steps) + 1,
                    "node": node_name,
                    "title": _DEBUG_NODE_TITLES.get(node_name, node_name.replace("_", " ").title()),
                    "status": "error" if current_error or node_failed else "completed",
                    "data": _debug_step_data(node_name, node_state),
                }
            )

    return {
        "enabled": True,
        "steps": steps,
        "summary": {
            "nodes_executed": len(steps),
            "nodes": [step["node"] for step in steps],
        },
    }


def _last_workflow_state(updates: list[dict[str, Any]]) -> dict[str, Any] | None:
    for update in reversed(updates):
        for _node_name, node_state in update.items():
            if isinstance(node_state, dict) and "user_query" in node_state:
                return node_state
    return None


def _latest_stream_error(updates: list[dict[str, Any]]) -> str | None:
    for update in reversed(updates):
        for node_name, node_state in update.items():
            if node_name == "error":
                if isinstance(node_state, dict):
                    return str(
                        node_state.get("current_error")
                        or node_state.get("error")
                        or node_state.get("message")
                        or node_state
                    )
                return str(node_state)
            if isinstance(node_state, dict) and node_state.get("current_error"):
                return str(node_state["current_error"])
    return None


def _build_debug_result_from_updates(
    user_query: str, updates: list[dict[str, Any]]
) -> dict[str, Any]:
    for update in reversed(updates):
        simple_state = update.get("simple_agent") if isinstance(update, dict) else None
        if isinstance(simple_state, dict) and isinstance(simple_state.get("simple_result"), dict):
            result = dict(simple_state["simple_result"])
            result["debug"] = _build_debug_payload_from_updates(updates)
            return result

    debug_payload = _build_debug_payload_from_updates(updates)
    error_message = _latest_stream_error(updates) or "Debug execution did not return workflow state"
    return {
        "success": False,
        "question": user_query,
        "sql_query": None,
        "results": [],
        "row_count": 0,
        "execution_time": 0.0,
        "error_message": error_message,
        "response": f"Nao foi possivel processar sua consulta: {error_message}",
        "timestamp": datetime.now().isoformat(),
        "metadata": {},
        "debug": debug_payload,
    }


def _attach_visualization_to_debug_result(
    orchestrator: Any,
    *,
    result: dict[str, Any],
    user_query: str,
) -> dict[str, Any]:
    """Visualization was intentionally removed from the simple runtime."""
    return result


def _format_table_schema(table_name: str, info: dict[str, Any]) -> str:
    lines = [
        f"TABELA: {table_name}",
        f"TITULO: {info.get('title', table_name)}",
        f"DESCRICAO: {info.get('description', '-')}",
        f"PROPOSITO: {info.get('purpose', '-')}",
    ]

    key_columns = info.get("key_columns") or []
    if key_columns:
        lines.append("COLUNAS_CHAVE:")
        lines.extend(f"- {column}" for column in key_columns)

    value_mappings = info.get("value_mappings") or {}
    if value_mappings:
        lines.append("MAPEAMENTOS:")
        lines.extend(f"- {column}: {description}" for column, description in value_mappings.items())

    critical_notes = info.get("critical_notes") or []
    if critical_notes:
        lines.append("NOTAS_CRITICAS:")
        lines.extend(f"- {note}" for note in critical_notes)

    relationships = info.get("relationships") or []
    if relationships:
        lines.append("RELACIONAMENTOS:")
        lines.extend(f"- {relation}" for relation in relationships)

    use_cases = info.get("use_cases") or []
    if use_cases:
        lines.append("CASOS_DE_USO:")
        lines.extend(f"- {use_case}" for use_case in use_cases)

    return "\n".join(lines)


def _build_schema_response(table: str | None) -> SchemaResponse:
    from src.application.config.table_descriptions import TABLE_DESCRIPTIONS

    tables = sorted(TABLE_DESCRIPTIONS.keys())
    if table:
        if table not in TABLE_DESCRIPTIONS:
            raise HTTPException(status_code=404, detail=f"Tabela não encontrada: {table}")
        schema = _format_table_schema(table, TABLE_DESCRIPTIONS[table])
    else:
        schema = "\n\n".join(
            _format_table_schema(table_name, TABLE_DESCRIPTIONS[table_name])
            for table_name in tables
        )

    return SchemaResponse(
        schema_text=schema,
        tables=tables,
        selected_table=table,
        timestamp=datetime.now().isoformat(),
    )


def _build_models_response() -> ModelsResponse:
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not ready")

    return ModelsResponse(
        available_models=_orchestrator.get_available_models(),
        current_model=_orchestrator.get_current_model(),
        timestamp=datetime.now().isoformat(),
    )


def _redact_database_url(database_url: str) -> str:
    if "://" not in database_url or "@" not in database_url:
        return database_url
    scheme, rest = database_url.split("://", 1)
    return f"{scheme}://****@{rest.split('@', 1)[1]}"


def _get_database_engine():
    global _database_engine
    if _database_engine is None:
        from src.agent.orchestrator_support import resolve_database_url

        _database_engine = create_engine(resolve_database_url(None))
    return _database_engine


def _docs_generated_files() -> list[str]:
    docs_dir = PROJECT_ROOT / "docs" / "generated"
    if not docs_dir.exists():
        return []
    return sorted(path.name for path in docs_dir.iterdir() if path.is_file())


def _read_table_inventory() -> dict[tuple[str, str], dict[str, Any]]:
    import csv

    inventory_path = PROJECT_ROOT / "docs" / "generated" / "table_inventory.csv"
    if not inventory_path.exists():
        return {}

    inventory: dict[tuple[str, str], dict[str, Any]] = {}
    with inventory_path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            key = (row.get("table_schema") or "main", row.get("table_name") or "")
            if not key[1]:
                continue
            row_count = row.get("row_count")
            inventory[key] = {
                "row_count": int(row_count) if row_count and row_count.isdigit() else None,
                "classification": row.get("classificacao") or None,
            }
    return inventory


def _json_result_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return _json_safe(value)


def _quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier:
        raise HTTPException(status_code=400, detail="Identificador de banco invalido")
    return '"' + identifier.replace('"', '""') + '"'


def _table_exists(connection: Any, schema_name: str, table_name: str) -> bool:
    result = connection.execute(
        text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = :schema_name
              AND table_name = :table_name
            LIMIT 1
            """
        ),
        {"schema_name": schema_name, "table_name": table_name},
    )
    return result.first() is not None


def _is_explorable_database_table(table_schema: str, table_name: str) -> bool:
    """Return whether a table is part of the user-facing database explorer."""

    if table_schema != "main":
        return False
    lowered = (table_name or "").lower()
    blocked_patterns = (
        "dbt",
        "_dbt_",
        "test",
        "_test_",
        "tmp",
        "temp",
        "staging",
        "fixture",
    )
    return not any(pattern in lowered for pattern in blocked_patterns)


def _ensure_explorable_database_table(table_schema: str, table_name: str) -> None:
    if not _is_explorable_database_table(table_schema, table_name):
        raise HTTPException(
            status_code=404,
            detail=f"Tabela nao disponivel no explorador: {table_schema}.{table_name}",
        )


def _normalize_query_limit(limit: int) -> int:
    return max(1, min(int(limit or 100), 500))


def _prepare_database_query(sql: str, limit: int) -> str:
    from src.utils.sql_safety import is_select_only, sanitize_sql_for_execution

    ok, reason = is_select_only(sql)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    cleaned = sanitize_sql_for_execution(sql).rstrip(";").strip()
    normalized_limit = _normalize_query_limit(limit)
    return f"SELECT * FROM ({cleaned}) AS ui_query LIMIT {normalized_limit}"


def _build_database_overview() -> DatabaseOverviewResponse:
    from src.agent.orchestrator_support import resolve_database_url

    engine = _get_database_engine()
    inventory = _read_table_inventory()
    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                SELECT table_schema, table_name, table_type
                FROM information_schema.tables
                WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
                ORDER BY table_schema, table_name
                """
            )
        )
        tables = []
        for row in result.mappings().all():
            if not _is_explorable_database_table(row["table_schema"], row["table_name"]):
                continue
            key = (row["table_schema"], row["table_name"])
            metadata = inventory.get(key, {})
            tables.append(
                DatabaseTableSummary(
                    table_schema=row["table_schema"],
                    table_name=row["table_name"],
                    table_type=row["table_type"],
                    row_count=metadata.get("row_count"),
                    classification=metadata.get("classification"),
                )
            )

    return DatabaseOverviewResponse(
        database_url=_redact_database_url(resolve_database_url(None)),
        tables=tables,
        generated_docs=_docs_generated_files(),
        timestamp=datetime.now().isoformat(),
    )


def _build_database_table_detail(
    schema_name: str, table_name: str, sample_limit: int = 25
) -> DatabaseTableDetailResponse:
    _ensure_explorable_database_table(schema_name, table_name)
    engine = _get_database_engine()
    normalized_limit = _normalize_query_limit(sample_limit)
    with engine.connect() as connection:
        if not _table_exists(connection, schema_name, table_name):
            raise HTTPException(
                status_code=404, detail=f"Tabela nao encontrada: {schema_name}.{table_name}"
            )

        column_result = connection.execute(
            text(
                """
                SELECT ordinal_position, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = :schema_name
                  AND table_name = :table_name
                ORDER BY ordinal_position
                """
            ),
            {"schema_name": schema_name, "table_name": table_name},
        )
        columns = [DatabaseColumn(**dict(row)) for row in column_result.mappings().all()]

        qualified_table = f"{_quote_identifier(schema_name)}.{_quote_identifier(table_name)}"
        sample_result = connection.execute(
            text(f"SELECT * FROM {qualified_table} LIMIT {normalized_limit}")
        )
        sample_columns = list(sample_result.keys())
        sample_rows = [
            {key: _json_result_value(value) for key, value in row.items()}
            for row in sample_result.mappings().all()
        ]

    return DatabaseTableDetailResponse(
        table_schema=schema_name,
        table_name=table_name,
        columns=columns,
        sample_columns=sample_columns,
        sample_rows=sample_rows,
        sample_limit=normalized_limit,
        timestamp=datetime.now().isoformat(),
    )


def _run_database_query(request: DatabaseQueryRequest) -> DatabaseQueryResponse:
    started_at = time.time()
    prepared_sql = _prepare_database_query(request.sql, request.limit)
    engine = _get_database_engine()
    with engine.connect() as connection:
        result = connection.execute(text(prepared_sql))
        columns = list(result.keys())
        rows = [
            {key: _json_result_value(value) for key, value in row.items()}
            for row in result.mappings().all()
        ]

    return DatabaseQueryResponse(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        limit=_normalize_query_limit(request.limit),
        sql=prepared_sql,
        execution_time=round(time.time() - started_at, 3),
        timestamp=datetime.now().isoformat(),
    )


def _load_table_context_detail(table_context: TableContext) -> DatabaseTableDetailResponse:
    return _build_database_table_detail(
        table_context.table_schema,
        table_context.table_name,
        sample_limit=0,
    )


def _apply_table_context_to_query(
    query: str,
    table_context: TableContext,
    detail: DatabaseTableDetailResponse,
) -> tuple[str, dict[str, Any]]:
    selected_columns = detail.columns[:12]
    column_summary = ", ".join(
        f"{column.column_name} {column.data_type}" for column in selected_columns
    )
    table_ref = f"{detail.table_schema}.{detail.table_name}"
    context_block = (
        f"Contexto ativo de tabela: {table_ref}\n"
        f"Colunas conhecidas: {column_summary or 'sem catalogo de colunas disponivel'}\n"
        "Use esta tabela como foco principal da resposta. "
        "Se a pergunta exigir outras tabelas, explique a necessidade antes de ampliar o escopo.\n\n"
        f"Pergunta do usuario: {query}"
    )
    return context_block, {
        "table_context_applied": True,
        "table_context": {
            "table_schema": detail.table_schema,
            "table_name": detail.table_name,
            "columns": [column.column_name for column in selected_columns],
        },
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.post("/api/v1/query", response_model=QueryResponse)
@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not ready")

    start_time = time.time()
    try:
        effective_query = request.query
        table_context_metadata: dict[str, Any] = {}
        if request.table_context is not None:
            table_detail = _load_table_context_detail(request.table_context)
            effective_query, table_context_metadata = _apply_table_context_to_query(
                request.query,
                request.table_context,
                table_detail,
            )

        if request.debug:
            updates = _orchestrator.process_query(
                effective_query,
                session_id=request.session_id,
                streaming=True,
            )
            result = _build_debug_result_from_updates(effective_query, updates)
            result = _attach_visualization_to_debug_result(
                _orchestrator,
                result=result,
                user_query=effective_query,
            )
        else:
            orchestrator_kwargs: dict[str, Any] = {"session_id": request.session_id}
            if request.chart_from_last_result:
                orchestrator_kwargs["chart_from_last_result"] = True
            result = _orchestrator.process_query(effective_query, **orchestrator_kwargs)
        if table_context_metadata:
            metadata = result.get("metadata", {}) or {}
            metadata.update(table_context_metadata)
            result["metadata"] = metadata
        if not request.include_sql:
            result["sql_query"] = None
        return _build_query_response(result, start_time, request.session_id)
    except HTTPException:
        raise
    except Exception as e:
        answer = SAFE_INTERNAL_AGENT_ERROR
        return QueryResponse(
            success=False,
            status="error",
            answer=answer,
            response=answer,
            sql=None,
            sql_query=None,
            execution_time=round(time.time() - start_time, 2),
            timestamp=datetime.now().isoformat(),
            session_id=request.session_id,
            chart=None,
            metadata={"error_type": type(e).__name__},
        )


@app.get("/api/v1/schema", response_model=SchemaResponse)
@app.get("/schema", response_model=SchemaResponse)
async def schema(table: str | None = None):
    return _build_schema_response(table)


@app.get("/api/v1/models", response_model=ModelsResponse)
@app.get("/models", response_model=ModelsResponse)
async def models():
    return _build_models_response()


@app.get("/api/v1/database/overview", response_model=DatabaseOverviewResponse)
@app.get("/database/overview", response_model=DatabaseOverviewResponse)
async def database_overview():
    try:
        return _build_database_overview()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao inspecionar banco: {exc}") from exc


@app.get(
    "/api/v1/database/table/{schema_name}/{table_name}",
    response_model=DatabaseTableDetailResponse,
)
@app.get("/database/table/{schema_name}/{table_name}", response_model=DatabaseTableDetailResponse)
async def database_table(schema_name: str, table_name: str, limit: int = 25):
    try:
        return _build_database_table_detail(schema_name, table_name, limit)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar tabela: {exc}") from exc


@app.post("/api/v1/database/query", response_model=DatabaseQueryResponse)
@app.post("/database/query", response_model=DatabaseQueryResponse)
async def database_query(request: DatabaseQueryRequest):
    try:
        return _run_database_query(request)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao executar SQL: {exc}") from exc


@app.get("/api/v1/health")
@app.get("/health")
async def health():
    if _orchestrator is None:
        return {"status": "starting"}
    return _orchestrator.health_check()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
