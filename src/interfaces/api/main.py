"""
FastAPI REST API for Text-to-SQL Agent

Uses LangGraphOrchestrator directly — no subprocess overhead.
"""

from contextlib import asynccontextmanager
from pathlib import Path
import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional

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
    session_id: Optional[str] = None


class QueryResponse(BaseModel):
    success: bool
    status: str
    answer: str
    response: str
    sql: Optional[str] = None
    sql_query: Optional[str] = None
    execution_time: float
    timestamp: str
    session_id: Optional[str] = None
    chart: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SchemaResponse(BaseModel):
    schema_text: str = Field(serialization_alias="schema")
    tables: list[str]
    selected_table: Optional[str] = None
    timestamp: str


class ModelsResponse(BaseModel):
    available_models: Dict[str, list[str]]
    current_model: Dict[str, Any]
    timestamp: str


def _build_query_response(result: Dict[str, Any], started_at: float, session_id: Optional[str]) -> QueryResponse:
    success = bool(result.get("success"))
    answer = result.get("response") or result.get("error_message") or "Resposta não disponível"
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
    )


def _format_table_schema(table_name: str, info: Dict[str, Any]) -> str:
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


def _build_schema_response(table: Optional[str]) -> SchemaResponse:
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
        result = _orchestrator.process_query(
            request.query,
            session_id=request.session_id,
        )
        if not request.include_sql:
            result["sql_query"] = None
        return _build_query_response(result, start_time, request.session_id)
    except Exception as e:
        return QueryResponse(
            success=False,
            status="error",
            answer=f"Erro: {str(e)}",
            response=f"Erro: {str(e)}",
            sql=None,
            sql_query=None,
            execution_time=round(time.time() - start_time, 2),
            timestamp=datetime.now().isoformat(),
            session_id=request.session_id,
            chart=None,
            metadata={},
        )


@app.get("/api/v1/schema", response_model=SchemaResponse)
@app.get("/schema", response_model=SchemaResponse)
async def schema(table: Optional[str] = None):
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
