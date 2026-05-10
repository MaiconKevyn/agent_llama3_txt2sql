"""Schema retrieval node, schema cache, and SUS schema enhancement helpers."""

import re
import time
from datetime import datetime
from typing import Dict, List

from ..application.config.table_descriptions import TABLE_DESCRIPTIONS
from ..utils.logging_config import get_nodes_logger
from .llm_manager import OpenAILLMManager, get_llm_manager
from .state_helpers import add_ai_message, add_error, add_tool_call_result, update_phase
from .state_models import ExecutionPhase, MessagesStateTXT2SQL, ToolCallResult

logger = get_nodes_logger()

# Module-level schema cache — schema is static; no need to re-fetch per query
_schema_cache: Dict[str, str] = {}


def _build_fallback_schema_context(selected_tables: list[str], error_message: str) -> str:
    sections = [
        "Schema context fallback generated from curated table metadata.",
        f"Original schema-tool error: {error_message}",
    ]
    for table in selected_tables:
        description = TABLE_DESCRIPTIONS.get(table)
        if not description:
            sections.append(f"\nTABLE {table}: metadata not available.")
            continue
        sections.append(f"\nTABLE {table}: {description.get('title', table)}")
        sections.append(str(description.get("description", "")))
        key_columns = description.get("key_columns") or []
        if key_columns:
            sections.append("Key columns: " + ", ".join(str(column) for column in key_columns))
        mappings = description.get("value_mappings") or {}
        if mappings:
            sections.append("Value mappings:")
            sections.extend(f"- {column}: {meaning}" for column, meaning in mappings.items())
        notes = description.get("critical_notes") or []
        if notes:
            sections.append("Critical notes:")
            sections.extend(f"- {note}" for note in notes)
        relationships = description.get("relationships") or []
        if relationships:
            sections.append("Relationships:")
            sections.extend(f"- {relationship}" for relationship in relationships)
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Schema refresh helpers (used by repair_sql_node in execution.py)
# ---------------------------------------------------------------------------

def _should_refresh_schema(error_message: str) -> bool:
    """Detect whether the error suggests missing columns/tables."""
    if not error_message:
        return False

    lower_error = error_message.lower()

    if "undefined column" in lower_error or "psycopg2.errors.undefinedcolumn" in lower_error:
        return True

    missing_markers = ["does not exist", "não existe"]
    schema_terms = ["column", "coluna", "relation", "tabela", "table"]

    if any(marker in lower_error for marker in missing_markers):
        if any(term in lower_error for term in schema_terms):
            return True

    return False


def _refresh_schema_context(
    state: MessagesStateTXT2SQL,
    error_message: str,
    llm_manager: OpenAILLMManager,
) -> bool:
    """Re-run table discovery and schema retrieval with error context."""
    try:
        logger.info("Refreshing schema context after execution error")

        refresh_start = time.time()

        tools = llm_manager.get_sql_tools()
        list_tables_tool = next((tool for tool in tools if tool.name == "sql_db_list_tables"), None)
        schema_tool = next((tool for tool in tools if tool.name == "sql_db_schema"), None)

        if not list_tables_tool or not schema_tool:
            raise ValueError("Required SQL tools not available for schema refresh")

        list_tables_start = time.time()
        table_output = list_tables_tool.invoke("")
        list_tables_duration = time.time() - list_tables_start
        table_names: List[str] = []
        if isinstance(table_output, str):
            table_pattern = r'^(\w+):'
            for line in table_output.split('\n'):
                match = re.match(table_pattern, line.strip())
                if match:
                    table_names.append(match.group(1))

        if not table_names:
            db = llm_manager.get_database()
            table_names = db.get_usable_table_names()

        state["available_tables"] = table_names

        # Lazy import to avoid circular dependency
        from .table_selection import _select_relevant_tables

        contextual_query = f"{state.get('user_query', '')}\nContexto do erro detectado: {error_message}"
        selected_tables, raw_selected_tables = _select_relevant_tables(
            user_query=contextual_query,
            tool_result=table_output,
            available_tables=table_names,
            llm_manager=llm_manager,
        )

        if not selected_tables:
            selected_tables = table_names[:3]

        state["selected_tables"] = selected_tables

        metadata = state.get("response_metadata", {}) or {}
        metadata.setdefault("repair_schema_refreshes", []).append({
            "error": error_message,
            "selected_tables": selected_tables,
            "timestamp": datetime.now().isoformat(),
        })
        metadata["raw_selected_tables_after_error"] = raw_selected_tables
        state["response_metadata"] = metadata

        list_tables_call = ToolCallResult(
            tool_name="sql_db_list_tables",
            tool_input={},
            tool_output=table_output,
            success=True,
            execution_time=list_tables_duration,
        )
        state = add_tool_call_result(state, list_tables_call)

        tables_input = ", ".join(selected_tables)
        schema_start = time.time()
        schema_output = schema_tool.invoke(tables_input)
        schema_duration = time.time() - schema_start
        state["schema_context"] = str(schema_output)

        schema_call = ToolCallResult(
            tool_name="sql_db_schema",
            tool_input={"tables": tables_input},
            tool_output=schema_output,
            success=True,
            execution_time=schema_duration,
        )
        state = add_tool_call_result(state, schema_call)

        total_duration = time.time() - refresh_start
        logger.info("Schema context refreshed", extra={
            "selected_tables": selected_tables,
            "duration": total_duration,
        })
        return True

    except Exception as e:
        logger.error("Schema refresh failed", extra={"error": str(e)})
        return False


# ---------------------------------------------------------------------------
# SUS schema enhancement
# ---------------------------------------------------------------------------

def _enhance_sus_schema_context(base_schema: str) -> str:
    """
    Enhance schema context with Brazilian SUS data value mappings.

    Adds critical value mappings and join rules not obvious from raw DDL.
    This is the single source of truth for column semantics — overrides DDL if conflicting.
    """
    sus_mappings = """

CRITICAL COLUMN VALUE MAPPINGS (sihrd5 — override DDL if conflicting):
=======================================================================
internacoes:
  "SEXO"    INTEGER: 1=Masculino, 3=Feminino (NUNCA usar 2)
  "MORTE"   BOOLEAN: true=óbito, false=alta
  "IND_VDRL" BOOLEAN: true=positivo (filtrar sem JOIN cid)
  "IDADE"   INTEGER (0-130): idade pré-calculada — USAR para todos filtros de idade
  "NASC"    DATE: data de nascimento — usar SOMENTE para "nascidos antes/após ano X"
            ❌ EXTRACT(YEAR FROM AGE("NASC")) — ERRADO, usar "IDADE" diretamente
            ❌ (CURRENT_DATE - "NASC") / 365 > 60 — ERRADO, usar "IDADE" diretamente
  "VAL_TOT" NUMERIC: custo total   | "VAL_SH": serviço hospitalar | "VAL_UTI": UTI
            "valor do serviço hospitalar" → VAL_SH  (NÃO VAL_TOT!)
  "ESPEC"   INTEGER: 1=Cirúrgico, 2=Obstétrico, 3=Clínico, 4=Crônico, 5=Psiquiatria, 7=Pediátrico
  "MUNIC_RES" FK→municipios.codigo_6d: município de RESIDÊNCIA do paciente (onde o paciente mora)
  ⚠️  MUNIC_MOV não existe em internacoes — está APENAS em hospital.MUNIC_MOV
  MUNIC_RES vs MUNIC_MOV — REGRA DEFAULT + EXCEÇÕES:
    DEFAULT (sem contexto de localização hospitalar): → MUNIC_RES (residência do paciente)
    ✅ "municípios com mais internações" → MUNIC_RES (JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d)
    ✅ "5 municípios com mais internações obstétricas" → MUNIC_RES
    ✅ "municípios com mais internações por especialidade/raça/diagnóstico" → MUNIC_RES
    EXCEÇÃO — usar MUNIC_MOV quando a pergunta menciona localização dos hospitais ou cidades onde ocorrem os procedimentos:
    ✅ "municípios que mais ATENDEM / recebem / onde estão os hospitais" → MUNIC_MOV
    ✅ "procedimentos/atendimentos NAS CIDADES de X / em hospitais de X" → MUNIC_MOV
        JOIN hospital h ON i."CNES" = h."CNES"
        JOIN municipios mu ON h."MUNIC_MOV" = mu.codigo_6d
    ❌ NUNCA usar JOIN hospital para "municípios com mais internações" sem contexto hospitalar
  "DIAG_PRINC" FK→cid."CID": diagnóstico principal de entrada
  "CID_MORTE"  FK→cid."CID": causa da morte (somente quando MORTE=true)

socioeconomico (long-format — SEMPRE filtrar por metrica):
  metrica='populacao_total'             | metrica='idhm'
  metrica='mortalidade_infantil_1ano'   | metrica='bolsa_familia_total'
  metrica='esgotamento_sanitario_domicilio' | metrica='taxa_envelhecimento'
  ⚠️ SEM WHERE metrica=? → SUM soma TODAS as métricas → resultado sem sentido!

raca_cor:
  0=Sem informação, 1=Branca, 2=Preta, 3=Parda, 4=Amarela, 5=Indígena, 99=Sem informação
  Filtrar inline: WHERE "RACA_COR" = 5 (sem JOIN)
  Descrição: JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR" → SELECT r."DESCRICAO"
  DISTRIBUIÇÃO/COMPOSIÇÃO (inclui SEM INFORMACAO) → JOIN sem filtro; codes 0 e 99 → 'SEM INFORMACAO'
  ANÁLISE por raça (taxa, média) → excluir unknowns: WHERE "RACA_COR" NOT IN (0, 99)

JOIN RULES:
  municipio do paciente (residência) — DEFAULT → JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
  municipio do hospital  (atendimento) — SOMENTE quando há contexto de hospital/localização:
                                          JOIN hospital h ON i."CNES" = h."CNES"
                                          JOIN municipios mu ON h."MUNIC_MOV" = mu.codigo_6d
  CRÍTICO: "municípios com mais internações" (sem contexto hospitalar) → MUNIC_RES (DEFAULT)
  CRÍTICO: "municípios que atendem / recebem / onde ficam hospitais" → MUNIC_MOV via hospital JOIN
  CRÍTICO: "procedimentos/atendimentos NAS CIDADES de X" → MUNIC_MOV (hospital location)
  especialidade         → JOIN especialidade e ON i."ESPEC" = e."ESPEC" → SELECT e."DESCRICAO"
  diagnóstico           → JOIN cid c ON i."DIAG_PRINC" = c."CID" → SELECT c."CD_DESCRICAO"
  causa de morte        → JOIN cid c ON i."CID_MORTE" = c."CID" WHERE i."MORTE" = true
"""
    return base_schema + sus_mappings


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def get_schema_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """
    Get Schema Node - Using SQLDatabaseToolkit

    Uses the sql_db_schema tool from SQLDatabaseToolkit
    Following official LangGraph SQL agent patterns
    """
    start_time = time.time()

    logger.info("Schema node started")

    try:
        llm_manager = get_llm_manager()

        tools = llm_manager.get_sql_tools()
        schema_tool = next((tool for tool in tools if tool.name == "sql_db_schema"), None)

        if not schema_tool:
            raise ValueError("sql_db_schema tool not found")

        selected_tables = state.get("selected_tables", [])
        if not selected_tables:
            selected_tables = state.get("available_tables", ["sus_data"])[:3]

        tables_input = ", ".join(selected_tables)
        cache_key = "|".join(sorted(selected_tables))

        if cache_key in _schema_cache:
            schema_text = _schema_cache[cache_key]
            state["schema_context"] = schema_text
            logger.info("Schema served from cache", extra={
                "tables": tables_input,
                "cache_key": cache_key,
                "context_size": len(schema_text),
            })
            execution_time = time.time() - start_time
            state = update_phase(state, ExecutionPhase.SCHEMA_ANALYSIS, execution_time)
            return state

        tool_result = schema_tool.invoke(tables_input)
        schema_text = str(tool_result)

        state["schema_context"] = schema_text
        _schema_cache[cache_key] = schema_text

        tool_call_result = ToolCallResult(
            tool_name="sql_db_schema",
            tool_input={"tables": tables_input},
            tool_output=tool_result,
            success=True,
            execution_time=time.time() - start_time,
        )

        state = add_tool_call_result(state, tool_call_result)

        schema_summary = f"Retrieved schema for {len(selected_tables)} tables"
        state = add_ai_message(state, schema_summary)

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SCHEMA_ANALYSIS, execution_time)

        logger.info("Schema retrieved", extra={
            "tables": tables_input,
            "context_size": len(schema_text),
            "execution_time": execution_time,
        })

        return state

    except Exception as e:
        error_message = f"Schema retrieval failed: {str(e)}"
        selected_tables = state.get("selected_tables", []) or state.get("available_tables", [])[:3]
        if selected_tables:
            schema_text = _build_fallback_schema_context(selected_tables, error_message)
            cache_key = "|".join(sorted(selected_tables))
            state["schema_context"] = schema_text
            _schema_cache[cache_key] = schema_text
            state = add_tool_call_result(
                state,
                ToolCallResult(
                    tool_name="sql_db_schema",
                    tool_input={"tables": ", ".join(selected_tables)},
                    tool_output=schema_text,
                    success=False,
                    error_message=error_message,
                    execution_time=time.time() - start_time,
                ),
            )
            state = add_ai_message(state, f"Retrieved fallback schema for {len(selected_tables)} tables")
            execution_time = time.time() - start_time
            state = update_phase(state, ExecutionPhase.SCHEMA_ANALYSIS, execution_time)
            logger.warning(
                "Schema tool failed; using curated fallback schema",
                extra={
                    "tables": selected_tables,
                    "error": error_message,
                    "context_size": len(schema_text),
                },
            )
            return state

        state = add_error(state, error_message, "schema_error", ExecutionPhase.SCHEMA_ANALYSIS)
        state["schema_context"] = (
            "Tables: internacoes (patient healthcare data), cid (diagnoses), "
            "municipios (cities), atendimentos (procedures junction)"
        )

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SCHEMA_ANALYSIS, execution_time)

        return state
