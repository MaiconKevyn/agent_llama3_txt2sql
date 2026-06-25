"""Table discovery and selection nodes + helpers."""

import re
import time
from typing import Any

from ..utils.logging_config import get_nodes_logger
from .llamaindex_context import (
    normalize_llamaindex_mode,
    retrieve_llamaindex_schema_context,
)
from .llm_manager import get_llm_manager
from .state_helpers import add_ai_message, add_error, add_tool_call_result, update_phase
from .state_models import TX, ExecutionPhase, MessagesStateTXT2SQL, ToolCallResult

logger = get_nodes_logger()


_NON_APPLICATION_TABLE_NAMES = {"Tabela"}
_NON_APPLICATION_TABLE_PREFIXES = (
    "accepted_values_",
    "relationships_",
    "source_not_null_",
    "source_unique_",
    "source_accepted_values_",
)


def _filter_active_tables(tables: list[str]) -> list[str]:
    """Keep user-queryable schema tables and drop dbt audit/test relations."""
    active_tables: list[str] = []
    seen: set[str] = set()
    for table in tables:
        if not table or table in seen:
            continue
        if table in _NON_APPLICATION_TABLE_NAMES:
            continue
        if table.startswith(_NON_APPLICATION_TABLE_PREFIXES):
            continue
        if "dbt_test__audit" in table:
            continue
        active_tables.append(table)
        seen.add(table)
    return active_tables


def _mentions_supported_socioeconomic_indicator(query_lower: str) -> bool:
    return bool(
        re.search(
            r"popula[cç][aã]o|habitantes|pib\s+per\s+capita|mortalidade\s+infantil|"
            r"leitos?\s+sus|m[eé]dicos?",
            query_lower,
        )
    )


def _validate_table_selection(
    user_query: str,
    selected_tables: list[str],
    available_tables: list[str],
) -> list[str]:
    """Validate and enhance table selection using business rules."""
    query_lower = user_query.lower()
    active_available = set(_filter_active_tables(available_tables))
    validated_tables = [
        table
        for table in selected_tables
        if table in active_available and not table.startswith(_NON_APPLICATION_TABLE_PREFIXES)
    ]

    logger.info(f"Starting table validation - Query: '{user_query}' - Initial: {selected_tables}")

    if _mentions_supported_socioeconomic_indicator(query_lower):
        validated_tables = []
        for table in ("socioeconomico", "municipios"):
            if table not in validated_tables and table in active_available:
                validated_tables.append(table)
                logger.info(
                    "Added table for supported socioeconomic indicator",
                    extra={"table": table},
                )
    elif "socioeconomico" in validated_tables and any(
        table in validated_tables
        for table in ("internacoes", "cid", "hospital", "procedimentos", "internacao_procedimento")
    ):
        validated_tables.remove("socioeconomico")
        logger.info(
            "Removed 'socioeconomico': query does not mention a supported socioeconomic indicator"
        )

    diagnosis_context = bool(
        re.search(r"diagn[oó]stic|cid|doen[cç]a|c[aâ]ncer|cancer|covid|neoplas", query_lower)
    )
    procedure_context = bool(re.search(r"procediment|proc_rea|cirurg", query_lower))
    if diagnosis_context and not procedure_context:
        for table in ("procedimentos", "internacao_procedimento"):
            if table in validated_tables:
                validated_tables.remove(table)
                logger.info(
                    "Removed procedure table from diagnosis-only query",
                    extra={"table": table},
                )

    # Rule 1: Death queries — MORTE is a boolean in internacoes
    if any(keyword in query_lower for keyword in ["morte", "óbito", "falecimento", "mortalidade"]):
        is_infant_mortality = "infantil" in query_lower and any(
            k in query_lower for k in ["mortalidade", "taxa"]
        )
        if is_infant_mortality:
            logger.info(
                "Infant mortality query detected — keeping socioeconomico, NOT adding internacoes"
            )
        else:
            if "internacoes" not in validated_tables and "internacoes" in available_tables:
                validated_tables.append("internacoes")
                logger.info("Added 'internacoes' for death query (MORTE boolean column)")

    # Rule 2: Procedure frequency queries need internacoes + internacao_procedimento + procedimentos
    if any(
        phrase in query_lower
        for phrase in [
            "procedimentos mais comuns",
            "procedimentos mais realizados",
            "frequência de procedimento",
            "procedimento",
        ]
    ):
        added_tables = []
        for tbl in ("internacoes", "internacao_procedimento", "procedimentos"):
            if tbl not in validated_tables and tbl in available_tables:
                validated_tables.append(tbl)
                added_tables.append(tbl)
        if added_tables:
            logger.debug("Ensured tables for procedure frequency", extra={"added": added_tables})

    # Rule 3: Financial queries about internacoes
    if (
        any(keyword in query_lower for keyword in ["valor", "custo", "gasto", "financeiro"])
        and "óbito" in query_lower
    ):
        if "internacoes" not in validated_tables and "internacoes" in available_tables:
            validated_tables.append("internacoes")
            logger.debug("Added 'internacoes' for financial data")

    # Rule 4: Hospital mortality rate → internacoes only
    if any(
        kw in query_lower for kw in ["taxa de mortalidade", "taxa mortalidade", "mortalidade"]
    ) and any(
        kw in query_lower
        for kw in ["taxa", "percentual", "proporção", "maior taxa", "municípios com"]
    ):
        if "infantil" not in query_lower:
            if "socioeconomico" in validated_tables:
                validated_tables.remove("socioeconomico")
                logger.info("Removed 'socioeconomico': hospital mortality rate uses internacoes")
            if "internacoes" not in validated_tables and "internacoes" in available_tables:
                validated_tables.append("internacoes")
                logger.info("Added 'internacoes' for hospital mortality rate calculation")

    # Rule 4b: Obstetric queries
    if any(
        keyword in query_lower
        for keyword in ["obstétric", "obstétrica", "obstétricas", "obstétrico"]
    ):
        if "internacoes" in validated_tables:
            validated_tables = ["internacoes"]
            logger.info("Reduced to internacoes only for obstetric query — use ESPEC = 2")
        elif "cid" in validated_tables:
            validated_tables.remove("cid")
            logger.info("Removed 'cid' for obstetric query — use ESPEC = 2 instead")

    # Rule 4c: Infant mortality queries
    if "infantil" in query_lower and any(k in query_lower for k in ["mortalidade", "taxa"]):
        if "socioeconomico" in validated_tables:
            validated_tables = ["socioeconomico"]
            logger.info("Simplified to socioeconomico only for infant mortality rate query")

    if re.search(
        r"n[ií]vel\s+de\s+instru[cç][aã]o|grau\s+de\s+instru[cç][aã]o|escolaridade", query_lower
    ):
        for tbl in ("internacoes", "instrucao"):
            if tbl not in validated_tables and tbl in available_tables:
                validated_tables.append(tbl)
                logger.info("Added table for education-level analysis", extra={"table": tbl})

    if re.search(r"hospitais?|cnes", query_lower) and re.search(
        r"\bestados?\b|\buf\b|munic[ií]pios?|cidades?|localiza[cç][aã]o|atend\w+|receb\w+",
        query_lower,
    ):
        for tbl in ("internacoes", "hospital", "municipios"):
            if tbl not in validated_tables and tbl in available_tables:
                validated_tables.append(tbl)
                logger.info("Added table for hospital-location join path", extra={"table": tbl})

    # Rule 5: Remove unnecessary over-selections for simple counting
    if len(validated_tables) > 1:
        simple_counting_patterns = [
            r"quantos? \w+ foram registrad[ao]s?",
            r"quantos? \w+ exist[em]?",
            r"total de \w+",
        ]
        is_simple_count = any(
            re.search(pattern, query_lower) for pattern in simple_counting_patterns
        )

        if is_simple_count and not any(
            join_keyword in query_lower for join_keyword in ["por", "com", "em", "de"]
        ):
            priority_tables = [
                "internacao_procedimento",
                "procedimentos",
                "cid",
                "hospital",
                "socioeconomico",
                "vincprev",
                "instrucao",
                "especialidade",
            ]
            for priority_table in priority_tables:
                if priority_table in validated_tables:
                    validated_tables = [priority_table]
                    logger.debug(
                        "Simplified to single table for counting", extra={"table": priority_table}
                    )
                    break

    # Rule 6: internacao_procedimento requires internacoes and procedimentos
    if "internacao_procedimento" in validated_tables:
        if "internacoes" not in validated_tables and "internacoes" in available_tables:
            validated_tables.append("internacoes")
            logger.info("Added 'internacoes' - required for internacao_procedimento junction")
        if "procedimentos" not in validated_tables and "procedimentos" in available_tables:
            validated_tables.append("procedimentos")
            logger.info("Added 'procedimentos' - required for internacao_procedimento junction")

    # Rule 7: sex filters/grouping usually come directly from internacoes.
    # Keep `sexo` only when the query explicitly asks for the label/description itself.
    if "sexo" in validated_tables and "internacoes" in validated_tables:
        needs_sex_label = any(
            phrase in query_lower
            for phrase in [
                "descrição do sexo",
                "descricao do sexo",
                "nome do sexo",
                "rótulo do sexo",
                "rotulo do sexo",
                "label do sexo",
            ]
        )
        if not needs_sex_label:
            validated_tables.remove("sexo")
            logger.info("Removed 'sexo' - internacoes already supports sex filter/grouping")

    # Rule 8: municipality-of-care questions require hospital geography, not residence geography.
    is_care_municipality_query = re.search(r"munic[ií]p", query_lower) is not None and (
        re.search(r"atend\w+", query_lower) is not None
        or "localização do hospital" in query_lower
        or "localizacao do hospital" in query_lower
        or "hospital" in query_lower
    )
    if is_care_municipality_query:
        if "hospital" not in validated_tables and "hospital" in available_tables:
            validated_tables.append("hospital")
            logger.info("Added 'hospital' for municipality-of-care query")
        if "municipios" not in validated_tables and "municipios" in available_tables:
            validated_tables.append("municipios")
            logger.info("Added 'municipios' for municipality-of-care query")

    if validated_tables != selected_tables:
        logger.debug(
            "Table validation completed",
            extra={
                "original": selected_tables,
                "validated": validated_tables,
            },
        )

    return validated_tables


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


def select_tables_with_llamaindex(
    user_query: str,
    available_tables: list[str],
    ablation_flags: dict[str, Any] | None = None,
) -> tuple[list[str], list[str], Any]:
    """Select runtime tables exclusively through LlamaIndex schema retrieval."""
    flags = ablation_flags or {}
    tables = _filter_active_tables(available_tables)
    llama_context = retrieve_llamaindex_schema_context(
        user_query=user_query,
        available_tables=tables,
        top_k_tables=int(flags.get("llamaindex_top_k_tables", 6) or 6),
        index_dir=str(flags.get("llamaindex_index_dir", ".llamaindex_schema")),
        rebuild_index=bool(flags.get("llamaindex_rebuild_index", False)),
    )
    raw_selected_tables = [table for table in llama_context.selected_tables if table in tables]
    selected_tables = (
        _validate_table_selection(user_query, raw_selected_tables, tables)
        if raw_selected_tables
        else []
    )
    return selected_tables, raw_selected_tables, llama_context


def list_tables_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """
    List Tables Node - Using SQLDatabaseToolkit

    Uses the sql_db_list_tables tool from SQLDatabaseToolkit
    Following official LangGraph SQL agent patterns
    """
    start_time = time.time()

    logger.info("Table discovery node started")

    try:
        llm_manager = get_llm_manager()

        tools = llm_manager.get_sql_tools()
        list_tables_tool = next((tool for tool in tools if tool.name == "sql_db_list_tables"), None)

        if not list_tables_tool:
            raise ValueError("sql_db_list_tables tool not found")

        tool_result = list_tables_tool.invoke("")

        if isinstance(tool_result, str):
            table_pattern = r"^(\w+):"
            table_names = []
            for line in tool_result.split("\n"):
                line = line.strip()
                match = re.match(table_pattern, line)
                if match:
                    table_names.append(match.group(1))

            if not table_names:
                db = llm_manager.get_database()
                table_names = db.get_usable_table_names()

            tables = _filter_active_tables(table_names)
        else:
            tables = []

        state["available_tables"] = tables

        ablation_flags = state.get("ablation_flags") or {}
        selected_tables: list[str] = []
        llamaindex_mode = normalize_llamaindex_mode(
            ablation_flags.get("llamaindex_mode") or "context"
        )

        selected_tables, raw_selected_tables, llama_context = select_tables_with_llamaindex(
            user_query=state["user_query"],
            available_tables=tables,
            ablation_flags=ablation_flags,
        )
        state["llamaindex_context"] = {
            "selected_tables": llama_context.selected_tables,
            "table_context": llama_context.table_context,
            "schema_context": llama_context.schema_context,
            "retrieval_mode": llama_context.retrieval_mode,
            "confidence": llama_context.confidence,
            "error": llama_context.error,
        }

        selection_mode = "llamaindex_context" if selected_tables else "llamaindex_unavailable"

        state["selected_tables"] = selected_tables
        meta = state.get("response_metadata", {}) or {}
        meta.update(
            {
                "llamaindex_enabled": True,
                "llamaindex_mode": llamaindex_mode,
                "llamaindex_retrieval_mode": llama_context.retrieval_mode,
                "llamaindex_selected_tables": llama_context.selected_tables,
                "llamaindex_confidence": llama_context.confidence,
                "llamaindex_error": llama_context.error,
                "raw_selected_tables": raw_selected_tables,
                "validated_selected_tables": selected_tables,
                "table_selection_mode": selection_mode,
            }
        )
        state["response_metadata"] = meta

        if not selected_tables:
            reason = llama_context.error or "LlamaIndex did not return valid runtime tables"
            state = add_error(
                state,
                f"LlamaIndex table selection failed: {reason}",
                "table_discovery_error",
                ExecutionPhase.TABLE_DISCOVERY,
                taxonomy=TX.WRONG_TABLE_SELECTION,
            )

        tool_call_result = ToolCallResult(
            tool_name="sql_db_list_tables",
            tool_input={},
            tool_output=tool_result,
            success=True,
            execution_time=time.time() - start_time,
        )

        state = add_tool_call_result(state, tool_call_result)

        ai_response = (
            f"Found {len(tables)} tables: {', '.join(tables[:3])}{'...' if len(tables) > 3 else ''}"
        )
        state = add_ai_message(state, ai_response)

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.TABLE_DISCOVERY, execution_time)

        logger.info(
            "Tables discovered",
            extra={
                "total_tables": len(tables),
                "table_list": ", ".join(tables),
                "selected_tables": ", ".join(state["selected_tables"]),
                "raw_selected_tables": ", ".join(raw_selected_tables),
                "execution_time": execution_time,
            },
        )

        return state

    except Exception as e:
        error_message = f"Table listing failed: {str(e)}"
        state = add_error(
            state,
            error_message,
            "table_discovery_error",
            ExecutionPhase.TABLE_DISCOVERY,
            taxonomy=TX.WRONG_TABLE_SELECTION,
        )

        state["available_tables"] = []
        state["selected_tables"] = []

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.TABLE_DISCOVERY, execution_time)

        return state
