"""Schema retrieval node, schema cache, and SUS schema enhancement helpers."""

import hashlib
import re
import time
from datetime import datetime

from ..application.config.table_descriptions import TABLE_DESCRIPTIONS
from ..utils.logging_config import get_nodes_logger
from .llm_manager import OpenAILLMManager, get_llm_manager
from .state_helpers import add_ai_message, add_error, add_tool_call_result, update_phase
from .state_models import ExecutionPhase, MessagesStateTXT2SQL, ToolCallResult

logger = get_nodes_logger()

# Module-level schema cache — schema is static; no need to re-fetch per query
_schema_cache: dict[str, str] = {}


def _merge_llamaindex_schema_context(
    schema_text: str,
    state: MessagesStateTXT2SQL,
) -> str:
    llama_context = state.get("llamaindex_context") or {}
    extra_context = str(llama_context.get("schema_context") or "").strip()
    if not extra_context:
        return schema_text
    meta = state.get("response_metadata", {}) or {}
    meta["llamaindex_schema_context_length"] = len(extra_context)
    state["response_metadata"] = meta
    return f"{schema_text}\n\n[LLAMAINDEX RETRIEVED CONTEXT]\n{extra_context}"


def _should_verify_llamaindex_schema_with_db(state: MessagesStateTXT2SQL) -> bool:
    flags = state.get("ablation_flags") or {}
    return bool(flags.get("verify_llamaindex_schema_with_db", False))


def _record_schema_context_metadata(
    state: MessagesStateTXT2SQL,
    *,
    source: str,
    verified_with_db: bool,
    selected_tables: list[str],
    schema_text: str,
) -> None:
    meta = state.get("response_metadata", {}) or {}
    meta.update(
        {
            "schema_context_source": source,
            "schema_context_verified_with_db": verified_with_db,
            "schema_context_tables": list(selected_tables),
            "schema_context_length": len(schema_text),
        }
    )
    state["response_metadata"] = meta


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
        verify_with_db = _should_verify_llamaindex_schema_with_db(state)

        if not list_tables_tool:
            raise ValueError("Required SQL tools not available for schema refresh")
        if verify_with_db and not schema_tool:
            raise ValueError("sql_db_schema tool not available for schema refresh verification")

        list_tables_start = time.time()
        table_output = list_tables_tool.invoke("")
        list_tables_duration = time.time() - list_tables_start
        table_names: list[str] = []
        if isinstance(table_output, str):
            table_pattern = r"^(\w+):"
            for line in table_output.split("\n"):
                match = re.match(table_pattern, line.strip())
                if match:
                    table_names.append(match.group(1))

        if not table_names:
            db = llm_manager.get_database()
            table_names = db.get_usable_table_names()

        from .table_selection import _filter_active_tables, select_tables_with_llamaindex

        table_names = _filter_active_tables(table_names)
        state["available_tables"] = table_names

        contextual_query = (
            f"{state.get('user_query', '')}\nContexto do erro detectado: {error_message}"
        )
        selected_tables, raw_selected_tables, llama_context = select_tables_with_llamaindex(
            user_query=contextual_query,
            available_tables=table_names,
            ablation_flags=state.get("ablation_flags") or {},
        )

        if not selected_tables:
            raise ValueError(
                llama_context.error
                or "LlamaIndex did not return valid tables during schema refresh"
            )

        state["selected_tables"] = selected_tables
        state["llamaindex_context"] = {
            "selected_tables": llama_context.selected_tables,
            "table_context": llama_context.table_context,
            "schema_context": llama_context.schema_context,
            "retrieval_mode": llama_context.retrieval_mode,
            "confidence": llama_context.confidence,
            "error": llama_context.error,
        }

        metadata = state.get("response_metadata", {}) or {}
        metadata.setdefault("repair_schema_refreshes", []).append(
            {
                "error": error_message,
                "selected_tables": selected_tables,
                "selection_mode": "llamaindex_context",
                "timestamp": datetime.now().isoformat(),
            }
        )
        metadata["raw_selected_tables_after_error"] = raw_selected_tables
        metadata["table_selection_mode_after_error"] = "llamaindex_context"
        state["response_metadata"] = metadata

        list_tables_call = ToolCallResult(
            tool_name="sql_db_list_tables",
            tool_input={},
            tool_output=table_output,
            success=True,
            execution_time=list_tables_duration,
        )
        state = add_tool_call_result(state, list_tables_call)

        llama_schema_text = str(llama_context.schema_context or "").strip()
        if llama_schema_text and not verify_with_db:
            state["schema_context"] = llama_schema_text
            _record_schema_context_metadata(
                state,
                source="llamaindex",
                verified_with_db=False,
                selected_tables=selected_tables,
                schema_text=llama_schema_text,
            )
            total_duration = time.time() - refresh_start
            logger.info(
                "Schema context refreshed from LlamaIndex",
                extra={
                    "selected_tables": selected_tables,
                    "duration": total_duration,
                },
            )
            return True

        if not schema_tool:
            raise ValueError("sql_db_schema tool not available for schema refresh fallback")

        tables_input = ", ".join(selected_tables)
        schema_start = time.time()
        schema_output = schema_tool.invoke(tables_input)
        schema_duration = time.time() - schema_start
        schema_text = _merge_llamaindex_schema_context(str(schema_output), state)
        state["schema_context"] = schema_text
        _record_schema_context_metadata(
            state,
            source="sql_db_schema",
            verified_with_db=bool(llama_schema_text),
            selected_tables=selected_tables,
            schema_text=schema_text,
        )

        schema_call = ToolCallResult(
            tool_name="sql_db_schema",
            tool_input={"tables": tables_input},
            tool_output=schema_output,
            success=True,
            execution_time=schema_duration,
        )
        state = add_tool_call_result(state, schema_call)

        total_duration = time.time() - refresh_start
        logger.info(
            "Schema context refreshed",
            extra={
                "selected_tables": selected_tables,
                "duration": total_duration,
            },
        )
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
  "MUNIC_RES" FK→municipios."CO_MUNICIPIO_6D": município de RESIDÊNCIA do paciente (onde o paciente mora)
  ⚠️  MUNIC_MOV não existe em internacoes — está APENAS em hospital.MUNIC_MOV
  MUNIC_RES vs MUNIC_MOV — REGRA DEFAULT + EXCEÇÕES:
    DEFAULT (sem contexto de localização hospitalar): → MUNIC_RES (residência do paciente)
    ✅ "municípios com mais internações" → MUNIC_RES (JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D")
    ✅ "5 municípios com mais internações obstétricas" → MUNIC_RES
    ✅ "municípios com mais internações por especialidade/raça/diagnóstico" → MUNIC_RES
    EXCEÇÃO — usar MUNIC_MOV quando a pergunta menciona localização dos hospitais ou cidades onde ocorrem os procedimentos:
    ✅ "municípios que mais ATENDEM / recebem / onde estão os hospitais" → MUNIC_MOV
    ✅ "procedimentos/internacao_procedimento NAS CIDADES de X / em hospitais de X" → MUNIC_MOV
        JOIN hospital h ON i."CNES" = h."CNES"
        JOIN municipios mu ON h."MUNIC_MOV" = mu."CO_MUNICIPIO_6D"
    ❌ NUNCA usar JOIN hospital para "municípios com mais internações" sem contexto hospitalar
  "DIAG_PRINC" FK→cid."CID": diagnóstico principal de entrada
  "CID_MORTE"  FK→cid."CID": causa da morte (somente quando MORTE=true)

socioeconomico (wide-format por município/ano):
  "QT_POPULACAO" população | "VL_PIB_PERCAPITA" PIB per capita
  "VL_MORT_INFANTIL" mortalidade infantil | "QT_LEITOS_SUS" leitos SUS
  "VL_LEITOS_SUS_1000" leitos SUS por 1000 | "QT_MEDICOS" médicos
  "VL_MEDICOS_1000" médicos por 1000
  ⚠️ NÃO use metrica/valor; essas colunas não existem no schema atual.

raca_cor:
  lookup raca_cor descreve categorias identificadas 1..5; internacoes pode conter 99=Sem informação
  1=Branca, 2=Preta, 3=Parda, 4=Amarela, 5=Indígena, 99=Sem informação
  Filtrar inline: WHERE "RACA_COR" = 5 (sem JOIN)
  Descrição: JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR" → SELECT r."DESCRICAO"
  DISTRIBUIÇÃO/COMPOSIÇÃO incluindo SEM INFORMACAO → LEFT JOIN + COALESCE/CASE para preservar código 99
  ANÁLISE por raça (taxa, média) → excluir unknowns: WHERE "RACA_COR" NOT IN (0, 99)
  raça/cor identificada/informada/registrada → WHERE "RACA_COR" IN (1, 2, 3, 4, 5)

JOIN RULES:
  municipio do paciente (residência) — DEFAULT → JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
  municipio do hospital  (atendimento) — SOMENTE quando há contexto de hospital/localização:
                                          JOIN hospital h ON i."CNES" = h."CNES"
                                          JOIN municipios mu ON h."MUNIC_MOV" = mu."CO_MUNICIPIO_6D"
  CRÍTICO: "municípios com mais internações" (sem contexto hospitalar) → MUNIC_RES (DEFAULT)
  CRÍTICO: "municípios que atendem / recebem / onde ficam hospitais" → MUNIC_MOV via hospital JOIN
  CRÍTICO: "procedimentos/internacao_procedimento NAS CIDADES de X" → MUNIC_MOV (hospital location)
  especialidade         → JOIN especialidade e ON i."ESPEC" = e."ESPEC" → SELECT e."DESCRICAO"
  diagnóstico           → JOIN cid c ON i."DIAG_PRINC" = c."CID" → SELECT c."DESCRICAO"
  causa de morte        → JOIN cid c ON i."CID_MORTE" = c."CID" WHERE i."MORTE" = true
"""
    return base_schema + sus_mappings


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


def get_schema_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """
    Get Schema Node.

    Uses LlamaIndex schema context as the default prompt schema source. The
    live sql_db_schema tool is only called when LlamaIndex context is missing
    or when explicit DB verification is enabled.
    """
    start_time = time.time()

    logger.info("Schema node started")

    try:
        selected_tables = state.get("selected_tables", [])
        if not selected_tables:
            state = add_error(
                state,
                "Schema retrieval skipped: no tables were selected by LlamaIndex",
                "schema_error",
                ExecutionPhase.SCHEMA_ANALYSIS,
            )
            state["schema_context"] = ""
            execution_time = time.time() - start_time
            state = update_phase(state, ExecutionPhase.SCHEMA_ANALYSIS, execution_time)
            return state

        tables_input = ", ".join(selected_tables)
        llama_context = state.get("llamaindex_context") or {}
        llama_extra = str(llama_context.get("schema_context") or "").strip()
        llama_hash = (
            hashlib.sha256(llama_extra.encode("utf-8")).hexdigest()[:12] if llama_extra else "none"
        )
        verify_with_db = _should_verify_llamaindex_schema_with_db(state)
        cache_prefix = "llamaindex" if llama_extra and not verify_with_db else "sql_db_schema"
        cache_key = f"{cache_prefix}|" + "|".join(sorted(selected_tables)) + f"|li:{llama_hash}"

        if cache_key in _schema_cache:
            schema_text = _schema_cache[cache_key]
            state["schema_context"] = schema_text
            _record_schema_context_metadata(
                state,
                source=cache_prefix,
                verified_with_db=cache_prefix == "sql_db_schema" and bool(llama_extra),
                selected_tables=selected_tables,
                schema_text=schema_text,
            )
            logger.info(
                "Schema served from cache",
                extra={
                    "tables": tables_input,
                    "cache_key": cache_key,
                    "context_size": len(schema_text),
                },
            )
            execution_time = time.time() - start_time
            state = update_phase(state, ExecutionPhase.SCHEMA_ANALYSIS, execution_time)
            return state

        if llama_extra and not verify_with_db:
            schema_text = llama_extra
            state["schema_context"] = schema_text
            _schema_cache[cache_key] = schema_text
            _record_schema_context_metadata(
                state,
                source="llamaindex",
                verified_with_db=False,
                selected_tables=selected_tables,
                schema_text=schema_text,
            )
            state = add_ai_message(
                state, f"Retrieved LlamaIndex schema context for {len(selected_tables)} tables"
            )
            execution_time = time.time() - start_time
            state = update_phase(state, ExecutionPhase.SCHEMA_ANALYSIS, execution_time)
            logger.info(
                "Schema context loaded from LlamaIndex",
                extra={
                    "tables": tables_input,
                    "context_size": len(schema_text),
                    "execution_time": execution_time,
                },
            )
            return state

        llm_manager = get_llm_manager()
        tools = llm_manager.get_sql_tools()
        schema_tool = next((tool for tool in tools if tool.name == "sql_db_schema"), None)

        if not schema_tool:
            raise ValueError("sql_db_schema tool not found")

        tool_result = schema_tool.invoke(tables_input)
        schema_text = _merge_llamaindex_schema_context(str(tool_result), state)

        state["schema_context"] = schema_text
        _schema_cache[cache_key] = schema_text
        _record_schema_context_metadata(
            state,
            source="sql_db_schema",
            verified_with_db=bool(llama_extra),
            selected_tables=selected_tables,
            schema_text=schema_text,
        )

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

        logger.info(
            "Schema retrieved",
            extra={
                "tables": tables_input,
                "context_size": len(schema_text),
                "execution_time": execution_time,
            },
        )

        return state

    except Exception as e:
        error_message = f"Schema retrieval failed: {str(e)}"
        selected_tables = state.get("selected_tables", [])
        if selected_tables:
            schema_text = _merge_llamaindex_schema_context(
                _build_fallback_schema_context(selected_tables, error_message),
                state,
            )
            cache_key = "fallback|" + "|".join(sorted(selected_tables))
            state["schema_context"] = schema_text
            _schema_cache[cache_key] = schema_text
            _record_schema_context_metadata(
                state,
                source="curated_fallback",
                verified_with_db=False,
                selected_tables=selected_tables,
                schema_text=schema_text,
            )
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
            state = add_ai_message(
                state, f"Retrieved fallback schema for {len(selected_tables)} tables"
            )
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
        state["schema_context"] = ""

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SCHEMA_ANALYSIS, execution_time)

        return state
