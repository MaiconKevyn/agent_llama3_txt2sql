"""Table discovery and selection nodes + helpers."""

import re
import time
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage

from .llm_manager import OpenAILLMManager, get_llm_manager
from .state_models import MessagesStateTXT2SQL, ExecutionPhase, ToolCallResult, TX
from .state_helpers import add_ai_message, add_tool_call_result, update_phase, add_error
from ..utils.logging_config import get_nodes_logger

logger = get_nodes_logger()


# ---------------------------------------------------------------------------
# Stage 1: keyword/regex heuristic
# ---------------------------------------------------------------------------

def _heuristic_table_selection(
    user_query: str, available_tables: List[str]
) -> Tuple[List[str], float]:
    """
    Stage 1: keyword-based fast table selection.
    Returns (tables, confidence). If confidence >= 0.85, skips LLM call.
    """
    q = user_query.lower()

    if re.search(r'mortalidade infantil|taxa de mortalidade infantil', q):
        return (['socioeconomico'], 0.95)

    if re.search(r'taxa de mortalidade|mortalidade hospitalar|maior taxa de mortalidade', q) \
            and 'infantil' not in q:
        return (['internacoes', 'municipios'], 0.93)

    if re.search(r'(mortes?|[óo]bitos?|falecimentos?)', q) and (
        re.search(r'\bestado\b', q)
        or re.search(r'\b(rs|ma|sp|rj|mg|pr|sc|go|mt|ms|ba|pe|ce|pa|am|es|df|pb|rn|al|pi|se|ro|ac|ap|rr|to)\b', q)
        or 'rio grande do sul' in q
    ):
        return (['internacoes', 'municipios'], 0.92)

    # "procedimentos/atendimentos nas cidades de X" → needs hospital for MUNIC_MOV
    # Check BEFORE the generic "procedimentos mais realizados" pattern
    if re.search(r'nas\s+cidades?', q) and re.search(r'procedimentos?|atendimentos?', q):
        return (['atendimentos', 'procedimentos', 'internacoes', 'hospital', 'municipios'], 0.92)

    if re.search(r'procedimentos?\s+(mais\s+)?(comuns?|realizados?|frequentes?)', q):
        return (['internacoes', 'atendimentos', 'procedimentos'], 0.92)

    if re.search(r'idhm|bolsa\s*familia|saneamento|pop.*econom', q):
        return (['socioeconomico', 'municipios'], 0.92)

    if re.search(r'especialidade.*interna[cç][oõ]es|interna[cç][oõ]es.*especialidade', q):
        return (['internacoes', 'especialidade'], 0.90)

    if re.search(r'n[ií]vel\s+de\s+instru[cç][aã]o|escolaridade.*interna[cç][oõ]es', q):
        return (['internacoes', 'instrucao'], 0.90)

    if re.search(r'ra[cç]a.*mortes|mortes.*ra[cç]a|ra[cç]a.*interna[cç][oõ]es', q):
        return (['internacoes', 'raca_cor'], 0.90)

    if re.search(r'hospital.*munic[ií]pio|munic[ií]pio.*hospital', q):
        return (['internacoes', 'hospital', 'municipios'], 0.88)

    return ([], 0.0)


# ---------------------------------------------------------------------------
# Stage 2 is in table_selector.py (EmbeddingTableSelector)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Stage 3: LLM selection
# ---------------------------------------------------------------------------

def _select_relevant_tables(
    user_query: str,
    tool_result: str,
    available_tables: List[str],
    llm_manager: OpenAILLMManager,
    disable_llm_stage: bool = False,
) -> Tuple[List[str], List[str]]:
    """
    3-stage table selection cascade:
      Stage 1: heuristic (instant)
      Stage 2: embedding similarity (< 10 ms)
      Stage 3: LLM (fallback for ambiguous queries — skipped when disable_llm_stage=True)

    Returns (validated_tables, raw_tables).
    """
    try:
        logger.info("Intelligent table selection started")

        # Stage 1: heuristic fast-path
        heur_tables, heur_confidence = _heuristic_table_selection(user_query, available_tables)
        if heur_confidence >= 0.85 and heur_tables:
            logger.info(
                f"Heuristic table selection: {heur_tables} (conf={heur_confidence})"
            )
            validated = _validate_table_selection(user_query, heur_tables, available_tables)
            return validated, heur_tables

        # Stage 2: embedding similarity fast-path (skips LLM when confident)
        try:
            from .table_selector import get_embedding_selector
            emb_tables, emb_confidence = get_embedding_selector().select(
                user_query, available_tables=available_tables, threshold=0.50, top_k=3
            )
            if emb_confidence >= 0.50 and emb_tables:
                logger.info(
                    "Embedding table selection",
                    extra={"tables": emb_tables, "conf": round(emb_confidence, 3)},
                )
                validated = _validate_table_selection(user_query, emb_tables, available_tables)
                return validated, emb_tables
        except Exception as _emb_exc:
            logger.warning("Embedding stage failed, proceeding to LLM", extra={"error": str(_emb_exc)})

        # Stage 3: LLM selection (skipped in ablation variant no_table_selection_llm)
        if disable_llm_stage:
            logger.info("table_selection: LLM stage disabled by ablation flag — using first available tables")
            fallback = _get_intelligent_fallback(user_query, available_tables)
            validated = _validate_table_selection(user_query, fallback, available_tables)
            return validated, fallback

        logger.info("Heuristic + embedding inconclusive — falling back to LLM table selection")

        from ..application.config.table_descriptions import TABLE_DESCRIPTIONS

        table_desc_lines = []
        for table_name in available_tables:
            if table_name in TABLE_DESCRIPTIONS:
                desc = TABLE_DESCRIPTIONS[table_name]
                title = desc.get("title", table_name)
                purpose = desc.get("purpose", "")
                use_cases = desc.get("use_cases", [])
                critical_notes = desc.get("critical_notes", [])

                line = f"- {table_name}: {title}"
                if purpose:
                    line += f" | {purpose}"
                if use_cases:
                    line += f" | Use for: {', '.join(use_cases[:2])}"
                if critical_notes:
                    line += f" | {'; '.join(critical_notes[:2])}"

                table_desc_lines.append(line)
            else:
                table_desc_lines.append(f"- {table_name}: Database table")

        selection_prompt = f"""POSTGRESQL TABLE SELECTION - Brazilian SUS Healthcare System

AVAILABLE TABLES:
{chr(10).join(table_desc_lines)}

CRITICAL SELECTION RULES FOR sihrd5 DATABASE:
====================================================

 CORE QUERIES - Primary Table Selection:
• internacoes: ALWAYS use for patient counts, hospitalization queries, deaths (MORTE boolean), VDRL (IND_VDRL boolean)
• atendimentos: Use when asking about procedures performed per hospitalization (junction table)

 LOOKUP TABLES - Always join when names/descriptions needed:
• cid: Join when need disease/diagnosis NAMES (table renamed from cid10 — use cid, NOT cid10!)
• procedimentos: Join when need procedure NAMES (always via atendimentos junction table)
• hospital: Join when need hospital/facility information
• municipios: Join when need city/municipality NAMES or geographic data

 SPECIALIZED ANALYSIS — socioeconomico is the ONLY source for these metrics:
• socioeconomico: Use for "população", "mortalidade infantil", "IDHM", "bolsa família", "envelhecimento",
  "saneamento", "dados do IBGE", "dados socioeconômicos" — ALWAYS filter by metrica column.
  NEVER use internacoes for "taxa de mortalidade infantil" — that comes from socioeconomico!
  Example: WHERE metrica = 'mortalidade_infantil_1ano' OR metrica = 'populacao_total' OR metrica = 'idhm'
• instrucao: Lookup for education level descriptions (JOIN with internacoes.INSTRU)
• vincprev: Lookup for social security type descriptions (JOIN with internacoes.VINCPREV)
• especialidade: Lookup for medical specialty descriptions (JOIN with internacoes.ESPEC)
• raca_cor: Lookup for race/color descriptions (JOIN with internacoes.RACA_COR)

 DISAMBIGUATION RULES:
• "taxa de mortalidade" / "mortalidade hospitalar" / "percentual de óbitos" in hospitalization context →
  calculate from internacoes: COUNT(MORTE=true)/COUNT(*). DO NOT use socioeconomico.
• "mortalidade infantil" / "taxa de mortalidade infantil" → socioeconomico with metrica='mortalidade_infantil_1ano'
• "municípios de residência" / "onde os pacientes moram" → internacoes.MUNIC_RES → municipios
• "municípios que atendem" / "por localização do hospital" / "média por município (hospital)" →
  hospital.MUNIC_MOV → municipios (requires BOTH hospital AND municipios tables)

 TABLES THAT NO LONGER EXIST (DO NOT SELECT):
• mortes: REMOVED — use internacoes WHERE "MORTE" = true
• cid10: RENAMED to cid — use cid
• dado_ibge: REPLACED by socioeconomico
• uti_detalhes: REMOVED — use internacoes."VAL_UTI" > 0 to identify ICU admissions
• condicoes_especificas: REMOVED — use internacoes WHERE "IND_VDRL" = true
• obstetricos: REMOVED — use internacoes.INSC_PN, GESTRICO, CONTRACEP1, CONTRACEP2
• cbor, infehosp, diagnosticos_secundarios: REMOVED from sihrd5

 SELECTION LOGIC:
1. Start with internacoes for most patient/hospitalization queries
2. For deaths/mortality: use internacoes with WHERE "MORTE" = true (no separate mortes table)
3. For procedures: add atendimentos + procedimentos (junction pattern)
4. Add lookup tables (cid, hospital, municipios) when descriptions are needed
5. For socioeconomic data: use socioeconomico (not dado_ibge)

USER QUERY: "{user_query}"

IMPORTANT: Respond with ONLY the table names separated by commas. No explanation or reasoning.

TABLES:"""

        response = llm_manager.invoke_chat([HumanMessage(content=selection_prompt)])

        selected_tables_str = response.content.strip() if hasattr(response, 'content') else str(response)

        logger.info(f"LLM table selection response: {selected_tables_str}")

        selected_tables = _parse_llm_table_selection(selected_tables_str, available_tables)
        raw_selected_tables = list(selected_tables)

        logger.info(f"Tables after parsing: {selected_tables}")

        selected_tables = _validate_table_selection(user_query, selected_tables, available_tables)

        logger.info(f"Tables after validation: {selected_tables}")

        if not selected_tables:
            logger.warning("No valid tables selected, using fallback")
            selected_tables = _get_intelligent_fallback(user_query, available_tables)

        logger.info("Table selection completed", extra={
            "query": user_query[:100],
            "available": available_tables,
            "selected": selected_tables,
            "raw_selected": raw_selected_tables,
            "type": "Single table" if len(selected_tables) == 1 else "Multi-table",
        })

        return selected_tables, raw_selected_tables

    except Exception as e:
        logger.error("Table selection failed", extra={"error": str(e)})
        return available_tables, available_tables


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_llm_table_selection(response: str, available_tables: List[str]) -> List[str]:
    """Simplified parsing of LLM table selection response."""
    import json

    selected_tables = []

    logger.info("Starting LLM response parsing", extra={"raw_response": response[:200]})

    # Method 1: JSON format
    try:
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(1))
            if 'tables' in data:
                tables = data['tables']
                selected_tables = [t for t in tables if t in available_tables]
                if selected_tables:
                    return selected_tables
    except (json.JSONDecodeError, KeyError):
        pass

    # Method 2: "TABLES:" section
    tables_match = re.search(r'TABLES:\s*(.+?)(?:\n|$)', response, re.IGNORECASE)
    if tables_match:
        tables_line = tables_match.group(1).strip()
        candidate_tables = [t.strip() for t in tables_line.split(',')]
        selected_tables = [t for t in candidate_tables if t in available_tables]
        if selected_tables:
            return selected_tables

    # Method 3: Direct comma-separated parsing
    lines = response.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line or line.startswith(('(Note:', 'Note:', 'Based on', 'Therefore', 'For this', 'The selection', 'I selected')):
            continue

        if ',' in line:
            candidate_tables = [t.strip() for t in line.split(',')]
        else:
            candidate_tables = [line.strip()]

        valid_candidates = []
        for candidate in candidate_tables:
            clean_candidate = re.sub(r'[^a-zA-Z0-9_]', '', candidate.strip())
            if clean_candidate in available_tables:
                valid_candidates.append(clean_candidate)

        if valid_candidates:
            logger.info(f"Direct parsing successful from line: '{line}' -> {valid_candidates}")
            return valid_candidates

    # Method 4: Any table name in response
    for table_name in available_tables:
        if re.search(r'\b' + re.escape(table_name) + r'\b', response, re.IGNORECASE):
            if table_name not in selected_tables:
                selected_tables.append(table_name)

    if not selected_tables:
        logger.warning("No tables found in LLM response")

    return selected_tables


def _validate_table_selection(
    user_query: str,
    selected_tables: List[str],
    available_tables: List[str],
) -> List[str]:
    """Validate and enhance table selection using business rules."""
    query_lower = user_query.lower()
    validated_tables = selected_tables.copy()

    logger.info(f"Starting table validation - Query: '{user_query}' - Initial: {selected_tables}")

    # Rule 1: Death queries — MORTE is a boolean in internacoes
    if any(keyword in query_lower for keyword in ['morte', 'óbito', 'falecimento', 'mortalidade']):
        is_infant_mortality = 'infantil' in query_lower and any(k in query_lower for k in ['mortalidade', 'taxa'])
        if is_infant_mortality:
            logger.info("Infant mortality query detected — keeping socioeconomico, NOT adding internacoes")
        else:
            if 'internacoes' not in validated_tables and 'internacoes' in available_tables:
                validated_tables.append('internacoes')
                logger.info("Added 'internacoes' for death query (MORTE boolean column)")

    # Rule 2: Procedure frequency queries need internacoes + atendimentos + procedimentos
    if any(phrase in query_lower for phrase in ['procedimentos mais comuns', 'procedimentos mais realizados', 'frequência de procedimento', 'procedimento']):
        added_tables = []
        for tbl in ('internacoes', 'atendimentos', 'procedimentos'):
            if tbl not in validated_tables and tbl in available_tables:
                validated_tables.append(tbl)
                added_tables.append(tbl)
        if added_tables:
            logger.debug("Ensured tables for procedure frequency", extra={"added": added_tables})

    # Rule 3: Financial queries about internacoes
    if any(keyword in query_lower for keyword in ['valor', 'custo', 'gasto', 'financeiro']) and 'óbito' in query_lower:
        if 'internacoes' not in validated_tables and 'internacoes' in available_tables:
            validated_tables.append('internacoes')
            logger.debug("Added 'internacoes' for financial data")

    # Rule 4: Hospital mortality rate → internacoes only
    if any(kw in query_lower for kw in ['taxa de mortalidade', 'taxa mortalidade', 'mortalidade']) and \
       any(kw in query_lower for kw in ['taxa', 'percentual', 'proporção', 'maior taxa', 'municípios com']):
        if 'infantil' not in query_lower:
            if 'socioeconomico' in validated_tables:
                validated_tables.remove('socioeconomico')
                logger.info("Removed 'socioeconomico': hospital mortality rate uses internacoes")
            if 'internacoes' not in validated_tables and 'internacoes' in available_tables:
                validated_tables.append('internacoes')
                logger.info("Added 'internacoes' for hospital mortality rate calculation")

    # Rule 4b: Obstetric queries
    if any(keyword in query_lower for keyword in ['obstétric', 'obstétrica', 'obstétricas', 'obstétrico']):
        if 'internacoes' in validated_tables:
            validated_tables = ['internacoes']
            logger.info("Reduced to internacoes only for obstetric query — use ESPEC = 2")
        elif 'cid' in validated_tables:
            validated_tables.remove('cid')
            logger.info("Removed 'cid' for obstetric query — use ESPEC = 2 instead")

    # Rule 4c: Infant mortality queries
    if 'infantil' in query_lower and any(k in query_lower for k in ['mortalidade', 'taxa']):
        if 'socioeconomico' in validated_tables:
            validated_tables = ['socioeconomico']
            logger.info("Simplified to socioeconomico only for infant mortality rate query")

    # Rule 5: Remove unnecessary over-selections for simple counting
    if len(validated_tables) > 1:
        simple_counting_patterns = [
            r'quantos? \w+ foram registrad[ao]s?',
            r'quantos? \w+ exist[em]?',
            r'total de \w+',
        ]
        is_simple_count = any(re.search(pattern, query_lower) for pattern in simple_counting_patterns)

        if is_simple_count and not any(join_keyword in query_lower for join_keyword in ['por', 'com', 'em', 'de']):
            priority_tables = ['atendimentos', 'procedimentos', 'cid',
                               'hospital', 'socioeconomico', 'vincprev', 'instrucao', 'especialidade']
            for priority_table in priority_tables:
                if priority_table in validated_tables:
                    validated_tables = [priority_table]
                    logger.debug("Simplified to single table for counting", extra={"table": priority_table})
                    break

    # Rule 6: atendimentos requires internacoes and procedimentos
    if 'atendimentos' in validated_tables:
        if 'internacoes' not in validated_tables and 'internacoes' in available_tables:
            validated_tables.append('internacoes')
            logger.info("Added 'internacoes' - required for atendimentos junction")
        if 'procedimentos' not in validated_tables and 'procedimentos' in available_tables:
            validated_tables.append('procedimentos')
            logger.info("Added 'procedimentos' - required for atendimentos junction")

    if validated_tables != selected_tables:
        logger.debug("Table validation completed", extra={
            "original": selected_tables,
            "validated": validated_tables,
        })

    return validated_tables


def _get_intelligent_fallback(user_query: str, available_tables: List[str]) -> List[str]:
    """Intelligent fallback when no tables are selected."""
    query_lower = user_query.lower()

    if any(keyword in query_lower for keyword in ['morte', 'óbito', 'falecimento', 'mortalidade']):
        return ['internacoes']
    if any(keyword in query_lower for keyword in ['uti', 'terapia intensiva', 'cuidados intensivos']):
        return ['internacoes']
    if any(keyword in query_lower for keyword in ['obstétric', 'gestante', 'pré-natal', 'parto']):
        return ['internacoes']
    if any(keyword in query_lower for keyword in ['procedimento', 'cirurgia', 'tratamento']):
        return ['atendimentos', 'internacoes', 'procedimentos'] if 'atendimentos' in available_tables else ['internacoes']
    if any(keyword in query_lower for keyword in ['cid', 'código', 'doença', 'diagnóstico']):
        return ['cid'] if 'cid' in available_tables else ['internacoes']

    return ['internacoes'] if 'internacoes' in available_tables else available_tables[:1]


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

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
            table_pattern = r'^(\w+):'
            table_names = []
            for line in tool_result.split('\n'):
                line = line.strip()
                match = re.match(table_pattern, line)
                if match:
                    table_names.append(match.group(1))

            if not table_names:
                db = llm_manager.get_database()
                table_names = db.get_usable_table_names()

            tables = table_names
        else:
            tables = []

        state["available_tables"] = tables

        ablation_flags = state.get("ablation_flags") or {}
        selected_tables, raw_selected_tables = _select_relevant_tables(
            user_query=state["user_query"],
            tool_result=tool_result,
            available_tables=tables,
            llm_manager=llm_manager,
            disable_llm_stage=ablation_flags.get("disable_table_selection_llm", False),
        )

        state["selected_tables"] = selected_tables
        try:
            meta = state.get("response_metadata", {}) or {}
            meta.update({
                "raw_selected_tables": raw_selected_tables,
                "validated_selected_tables": selected_tables,
            })
            state["response_metadata"] = meta
        except Exception:
            pass

        tool_call_result = ToolCallResult(
            tool_name="sql_db_list_tables",
            tool_input={},
            tool_output=tool_result,
            success=True,
            execution_time=time.time() - start_time,
        )

        state = add_tool_call_result(state, tool_call_result)

        ai_response = f"Found {len(tables)} tables: {', '.join(tables[:3])}{'...' if len(tables) > 3 else ''}"
        state = add_ai_message(state, ai_response)

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.TABLE_DISCOVERY, execution_time)

        logger.info("Tables discovered", extra={
            "total_tables": len(tables),
            "table_list": ', '.join(tables),
            "selected_tables": ', '.join(state['selected_tables']),
            "raw_selected_tables": ', '.join(raw_selected_tables),
            "execution_time": execution_time,
        })

        return state

    except Exception as e:
        error_message = f"Table listing failed: {str(e)}"
        state = add_error(state, error_message, "table_discovery_error", ExecutionPhase.TABLE_DISCOVERY,
                          taxonomy=TX.WRONG_TABLE_SELECTION)

        state["available_tables"] = ["sus_data", "cid_detalhado"]
        state["selected_tables"] = ["sus_data"]

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.TABLE_DISCOVERY, execution_time)

        return state
