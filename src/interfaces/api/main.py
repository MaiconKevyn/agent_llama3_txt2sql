"""
FastAPI REST API for Text-to-SQL Agent

Uses LangGraphOrchestrator directly — no subprocess overhead.
"""

import sys
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Allow running both as `python -m ...` and `python src/interfaces/api/main.py`
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Lifespan: initialise the orchestrator once at startup
# ---------------------------------------------------------------------------
_orchestrator = None


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


SAFE_INTERNAL_AGENT_ERROR = (
    "Não foi possível processar sua consulta com segurança. "
    "Tente refinar o recorte ou peça o gráfico de outra forma."
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
    return text or "Resposta não disponível"


def _build_query_response(
    result: dict[str, Any], started_at: float, session_id: str | None
) -> QueryResponse:
    success = bool(result.get("success"))
    raw_answer = result.get("response") or result.get("error_message") or "Resposta não disponível"
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
    from src.agent.state_helpers import state_to_legacy_format

    final_state = _last_workflow_state(updates)
    debug_payload = _build_debug_payload_from_updates(updates)
    if final_state is not None:
        result = state_to_legacy_format(final_state)
        result["debug"] = debug_payload
        return result

    error_message = _latest_stream_error(updates) or "Debug execution did not return workflow state"
    return {
        "success": False,
        "question": user_query,
        "sql_query": None,
        "results": [],
        "row_count": 0,
        "execution_time": 0.0,
        "error_message": error_message,
        "response": f"Não foi possível processar sua consulta: {error_message}",
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
    """Run the normal chart attachment step for debug/streaming responses."""

    metadata = result.get("metadata") or {}
    from src.visualization import build_chart_plan, detect_visualization_intent
    from src.visualization.schema import ChartPlan, VisualizationIntent

    try:
        visualization_intent = VisualizationIntent.model_validate(
            metadata.get("visualization_intent") or {}
        )
    except Exception:
        visualization_intent = detect_visualization_intent(user_query)

    try:
        chart_plan = ChartPlan.model_validate(metadata.get("chart_plan") or {})
    except Exception:
        chart_plan = build_chart_plan(user_query, visualization_intent)

    if not visualization_intent.requested:
        return result

    attach_visualization = getattr(orchestrator, "_attach_visualization_if_requested", None)
    if attach_visualization is None:
        return result

    return attach_visualization(
        result=result,
        user_query=user_query,
        visualization_intent=visualization_intent,
        chart_plan=chart_plan,
    )


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
        if request.debug:
            updates = _orchestrator.process_query(
                request.query,
                session_id=request.session_id,
                streaming=True,
            )
            result = _build_debug_result_from_updates(request.query, updates)
            result = _attach_visualization_to_debug_result(
                _orchestrator,
                result=result,
                user_query=request.query,
            )
        else:
            result = _orchestrator.process_query(
                request.query,
                session_id=request.session_id,
            )
        if not request.include_sql:
            result["sql_query"] = None
        return _build_query_response(result, start_time, request.session_id)
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


@app.get("/api/v1/health")
@app.get("/health")
async def health():
    if _orchestrator is None:
        return {"status": "starting"}
    return _orchestrator.health_check()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
