"""Table discovery and selection nodes + helpers."""

import re
import time
from typing import Any

from langchain_core.messages import HumanMessage

from ..application.prompts.table_selection.catalog import (
    render_table_description_lines,
    render_table_selection_prompt,
    resolve_table_selection_strategy,
)
from ..utils.logging_config import get_nodes_logger
from .llm_manager import OpenAILLMManager, get_llm_manager
from .state_helpers import add_ai_message, add_error, add_tool_call_result, update_phase
from .state_models import TX, ExecutionPhase, MessagesStateTXT2SQL, ToolCallResult

logger = get_nodes_logger()


TABLE_SELECTION_MODE_FULL_CASCADE = "full_cascade"
TABLE_SELECTION_MODE_HEURISTIC_ONLY = "heuristic_only"
TABLE_SELECTION_MODE_EMBEDDING_ONLY = "embedding_only"
TABLE_SELECTION_MODE_HEURISTIC_EMBEDDING_ONLY = "heuristic_embedding_only"
TABLE_SELECTION_MODE_LLM_ONLY = "llm_only"
TABLE_SELECTION_MODE_LLM_DISABLED_FALLBACK = "llm_disabled_current_fallback"

DEFAULT_TABLE_SELECTION_MODE = TABLE_SELECTION_MODE_FULL_CASCADE
DEFAULT_TABLE_DESCRIPTION_VARIANT = "current"
DEFAULT_TABLE_SELECTION_PROMPT_VARIANT = "current"


# ---------------------------------------------------------------------------
# Stage 1: keyword/regex heuristic
# ---------------------------------------------------------------------------

def _heuristic_table_selection(
    user_query: str, available_tables: list[str]
) -> tuple[list[str], float]:
    """
    Stage 1: keyword-based fast table selection.
    Returns (tables, confidence). If confidence >= 0.85, skips LLM call.
    """
    q = user_query.lower()

    if re.search(r'mortalidade infantil|taxa de mortalidade infantil', q):
        return (['socioeconomico'], 0.95)

    if re.search(r'taxa de mortalidade.*(?:n[ií]vel|grau)\s+de\s+instru[cç][aã]o|taxa de mortalidade.*escolaridade', q):
        return (['internacoes', 'municipios', 'instrucao'], 0.94)

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

    if re.search(r'munic[ií]pios?.*(atend\w+|receb\w+).*pacientes?', q):
        return (['internacoes', 'hospital', 'municipios'], 0.93)

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


def _build_table_description_lines(
    available_tables: list[str],
    description_variant: str = DEFAULT_TABLE_DESCRIPTION_VARIANT,
) -> list[str]:
    """Format available tables into prompt-friendly description lines."""
    return render_table_description_lines(
        available_tables,
        description_variant=description_variant,
    )


def _build_llm_selection_prompt(
    user_query: str,
    available_tables: list[str],
    description_variant: str = DEFAULT_TABLE_DESCRIPTION_VARIANT,
    prompt_variant: str = DEFAULT_TABLE_SELECTION_PROMPT_VARIANT,
) -> str:
    """Build the prompt for the LLM fallback stage."""
    return render_table_selection_prompt(
        user_query=user_query,
        available_tables=available_tables,
        description_variant=description_variant,
        prompt_variant=prompt_variant,
    )


def _run_embedding_table_selection(
    user_query: str,
    available_tables: list[str],
) -> tuple[list[str], float]:
    """Run stage 2 embedding selector."""
    from .table_selector import get_embedding_selector

    return get_embedding_selector().select(
        user_query,
        available_tables=available_tables,
        threshold=0.50,
        top_k=3,
    )


def _run_llm_table_selection(
    user_query: str,
    available_tables: list[str],
    llm_manager: Any,
    description_variant: str = DEFAULT_TABLE_DESCRIPTION_VARIANT,
    prompt_variant: str = DEFAULT_TABLE_SELECTION_PROMPT_VARIANT,
) -> dict[str, Any]:
    """Run stage 3 LLM selector and return parsing details."""
    selection_prompt = _build_llm_selection_prompt(
        user_query=user_query,
        available_tables=available_tables,
        description_variant=description_variant,
        prompt_variant=prompt_variant,
    )
    response = llm_manager.invoke_chat([HumanMessage(content=selection_prompt)])
    raw_response = response.content.strip() if hasattr(response, "content") else str(response)
    parsed_tables = _parse_llm_table_selection(raw_response, available_tables)
    return {
        "prompt": selection_prompt,
        "raw_response": raw_response,
        "parsed_tables": parsed_tables,
    }


def select_tables_with_debug(
    user_query: str,
    available_tables: list[str],
    llm_manager: Any | None = None,
    mode: str = DEFAULT_TABLE_SELECTION_MODE,
    description_variant: str = DEFAULT_TABLE_DESCRIPTION_VARIANT,
    prompt_variant: str = DEFAULT_TABLE_SELECTION_PROMPT_VARIANT,
) -> dict[str, Any]:
    """Select tables and expose stage-by-stage telemetry for benchmarking."""
    debug: dict[str, Any] = {
        "mode": mode,
        "description_variant": description_variant,
        "prompt_variant": prompt_variant,
        "heuristic": {"selected_tables": [], "confidence": 0.0},
        "embedding": {"selected_tables": [], "confidence": 0.0},
        "llm": {"parsed_tables": [], "raw_response": "", "prompt": ""},
        "fallback": {"selected_tables": []},
        "stage_used": "none",
        "raw_selected_tables": [],
        "validated_selected_tables": [],
        "error": "",
    }

    def _finalize(raw_tables: list[str], stage_used: str) -> dict[str, Any]:
        validated = _validate_table_selection(user_query, raw_tables, available_tables)
        debug["stage_used"] = stage_used
        debug["raw_selected_tables"] = list(raw_tables)
        debug["validated_selected_tables"] = validated
        return debug

    try:
        logger.info("Intelligent table selection started", extra={"mode": mode})

        if mode in (
            TABLE_SELECTION_MODE_FULL_CASCADE,
            TABLE_SELECTION_MODE_HEURISTIC_ONLY,
            TABLE_SELECTION_MODE_HEURISTIC_EMBEDDING_ONLY,
            TABLE_SELECTION_MODE_LLM_DISABLED_FALLBACK,
        ):
            heur_tables, heur_confidence = _heuristic_table_selection(user_query, available_tables)
            debug["heuristic"] = {
                "selected_tables": list(heur_tables),
                "confidence": heur_confidence,
            }
            if heur_confidence >= 0.85 and heur_tables:
                logger.info("Heuristic table selection", extra={"tables": heur_tables, "conf": heur_confidence})
                return _finalize(heur_tables, "heuristic")
            if mode == TABLE_SELECTION_MODE_HEURISTIC_ONLY:
                return _finalize(heur_tables, "heuristic")

        if mode in (
            TABLE_SELECTION_MODE_FULL_CASCADE,
            TABLE_SELECTION_MODE_EMBEDDING_ONLY,
            TABLE_SELECTION_MODE_HEURISTIC_EMBEDDING_ONLY,
            TABLE_SELECTION_MODE_LLM_DISABLED_FALLBACK,
        ):
            try:
                emb_tables, emb_confidence = _run_embedding_table_selection(user_query, available_tables)
                debug["embedding"] = {
                    "selected_tables": list(emb_tables),
                    "confidence": emb_confidence,
                }
                if emb_confidence >= 0.50 and emb_tables:
                    logger.info(
                        "Embedding table selection",
                        extra={"tables": emb_tables, "conf": round(emb_confidence, 3)},
                    )
                    return _finalize(emb_tables, "embedding")
            except Exception as exc:
                debug["embedding"]["error"] = str(exc)
                logger.warning("Embedding stage failed", extra={"error": str(exc)})
            if mode == TABLE_SELECTION_MODE_EMBEDDING_ONLY:
                return _finalize(debug["embedding"]["selected_tables"], "embedding")
            if mode == TABLE_SELECTION_MODE_HEURISTIC_EMBEDDING_ONLY:
                return _finalize(debug["embedding"]["selected_tables"], "embedding")

        if mode == TABLE_SELECTION_MODE_LLM_DISABLED_FALLBACK:
            fallback = _get_intelligent_fallback(user_query, available_tables)
            debug["fallback"]["selected_tables"] = list(fallback)
            logger.info("table_selection: LLM stage disabled by mode — using intelligent fallback")
            return _finalize(fallback, "fallback")

        if mode in (TABLE_SELECTION_MODE_FULL_CASCADE, TABLE_SELECTION_MODE_LLM_ONLY):
            if llm_manager is None:
                raise ValueError("llm_manager is required for LLM-based table selection modes")
            llm_debug = _run_llm_table_selection(
                user_query=user_query,
                available_tables=available_tables,
                llm_manager=llm_manager,
                description_variant=description_variant,
                prompt_variant=prompt_variant,
            )
            debug["llm"] = llm_debug
            logger.info("LLM table selection response", extra={"raw_response": llm_debug["raw_response"][:200]})

            parsed_tables = llm_debug["parsed_tables"]
            if parsed_tables:
                return _finalize(parsed_tables, "llm")

            fallback = _get_intelligent_fallback(user_query, available_tables)
            debug["fallback"]["selected_tables"] = list(fallback)
            logger.warning("No valid tables selected by LLM, using fallback")
            return _finalize(fallback, "fallback_after_llm")

        raise ValueError(f"Unsupported table selection mode: {mode}")

    except Exception as e:
        debug["error"] = str(e)
        logger.error("Table selection failed", extra={"error": str(e), "mode": mode})
        debug["raw_selected_tables"] = list(available_tables)
        debug["validated_selected_tables"] = list(available_tables)
        debug["stage_used"] = "error"
        return debug


def _select_relevant_tables(
    user_query: str,
    tool_result: str,
    available_tables: list[str],
    llm_manager: OpenAILLMManager,
    disable_llm_stage: bool = False,
    mode: str | None = None,
    description_variant: str = DEFAULT_TABLE_DESCRIPTION_VARIANT,
    prompt_variant: str = DEFAULT_TABLE_SELECTION_PROMPT_VARIANT,
) -> tuple[list[str], list[str]]:
    """
    3-stage table selection cascade:
      Stage 1: heuristic (instant)
      Stage 2: embedding similarity (< 10 ms)
      Stage 3: LLM (fallback for ambiguous queries — skipped when disable_llm_stage=True)

    Returns (validated_tables, raw_tables).
    """
    resolved_mode = mode or (
        TABLE_SELECTION_MODE_LLM_DISABLED_FALLBACK
        if disable_llm_stage
        else TABLE_SELECTION_MODE_FULL_CASCADE
    )
    debug = select_tables_with_debug(
        user_query=user_query,
        available_tables=available_tables,
        llm_manager=llm_manager,
        mode=resolved_mode,
        description_variant=description_variant,
        prompt_variant=prompt_variant,
    )

    logger.info("Table selection completed", extra={
        "query": user_query[:100],
        "available": available_tables,
        "selected": debug["validated_selected_tables"],
        "raw_selected": debug["raw_selected_tables"],
        "stage_used": debug["stage_used"],
        "type": "Single table" if len(debug["validated_selected_tables"]) == 1 else "Multi-table",
    })
    return debug["validated_selected_tables"], debug["raw_selected_tables"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_llm_table_selection(response: str, available_tables: list[str]) -> list[str]:
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
    selected_tables: list[str],
    available_tables: list[str],
) -> list[str]:
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

    if re.search(r'n[ií]vel\s+de\s+instru[cç][aã]o|grau\s+de\s+instru[cç][aã]o|escolaridade', query_lower):
        for tbl in ('internacoes', 'instrucao'):
            if tbl not in validated_tables and tbl in available_tables:
                validated_tables.append(tbl)
                logger.info("Added table for education-level analysis", extra={"table": tbl})

    if re.search(r'hospitais?|cnes', query_lower) and re.search(
        r'\bestados?\b|\buf\b|munic[ií]pios?|cidades?|localiza[cç][aã]o|atend\w+|receb\w+',
        query_lower,
    ):
        for tbl in ('internacoes', 'hospital', 'municipios'):
            if tbl not in validated_tables and tbl in available_tables:
                validated_tables.append(tbl)
                logger.info("Added table for hospital-location join path", extra={"table": tbl})

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

    # Rule 7: sex filters/grouping usually come directly from internacoes.
    # Keep `sexo` only when the query explicitly asks for the label/description itself.
    if 'sexo' in validated_tables and 'internacoes' in validated_tables:
        needs_sex_label = any(
            phrase in query_lower
            for phrase in [
                'descrição do sexo',
                'descricao do sexo',
                'nome do sexo',
                'rótulo do sexo',
                'rotulo do sexo',
                'label do sexo',
            ]
        )
        if not needs_sex_label:
            validated_tables.remove('sexo')
            logger.info("Removed 'sexo' - internacoes already supports sex filter/grouping")

    # Rule 8: municipality-of-care questions require hospital geography, not residence geography.
    is_care_municipality_query = (
        re.search(r'munic[ií]p', query_lower) is not None
        and (
            re.search(r'atend\w+', query_lower) is not None
            or 'localização do hospital' in query_lower
            or 'localizacao do hospital' in query_lower
            or 'hospital' in query_lower
        )
    )
    if is_care_municipality_query:
        if 'hospital' not in validated_tables and 'hospital' in available_tables:
            validated_tables.append('hospital')
            logger.info("Added 'hospital' for municipality-of-care query")
        if 'municipios' not in validated_tables and 'municipios' in available_tables:
            validated_tables.append('municipios')
            logger.info("Added 'municipios' for municipality-of-care query")

    if validated_tables != selected_tables:
        logger.debug("Table validation completed", extra={
            "original": selected_tables,
            "validated": validated_tables,
        })

    return validated_tables


def _get_intelligent_fallback(user_query: str, available_tables: list[str]) -> list[str]:
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
        strategy = resolve_table_selection_strategy(
            preset_name=ablation_flags.get("table_selection_preset"),
            mode=ablation_flags.get("table_selection_mode"),
            description_variant=ablation_flags.get("table_selection_description_variant"),
            prompt_variant=ablation_flags.get("table_selection_prompt_variant"),
        )
        selection_mode = strategy["mode"]
        if (
            selection_mode == DEFAULT_TABLE_SELECTION_MODE
            and ablation_flags.get("disable_table_selection_llm", False)
        ):
            selection_mode = TABLE_SELECTION_MODE_LLM_DISABLED_FALLBACK

        selected_tables, raw_selected_tables = _select_relevant_tables(
            user_query=state["user_query"],
            tool_result=tool_result,
            available_tables=tables,
            llm_manager=llm_manager,
            disable_llm_stage=(selection_mode == TABLE_SELECTION_MODE_LLM_DISABLED_FALLBACK),
            mode=selection_mode,
            description_variant=strategy["description_variant"],
            prompt_variant=strategy["prompt_variant"],
        )

        state["selected_tables"] = selected_tables
        try:
            meta = state.get("response_metadata", {}) or {}
            meta.update({
                "raw_selected_tables": raw_selected_tables,
                "validated_selected_tables": selected_tables,
                "table_selection_preset": strategy["preset_name"],
                "table_selection_mode": selection_mode,
                "table_selection_description_variant": strategy["description_variant"],
                "table_selection_prompt_variant": strategy["prompt_variant"],
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
