"""
Hybrid classification utilities for routing queries to DATABASE / CONVERSATIONAL / SCHEMA.

Provides:
- Text normalization (lowercase + diacritics removal)
- Heuristic scoring via PT keywords
- SQL snippet detection (rare but strong signal)
- Robust JSON extraction/parsing for LLM outputs
- Score combination helpers
"""

import json
import re
import unicodedata

ROUTES = ("DATABASE", "CONVERSATIONAL", "SCHEMA")


def normalize_text(text: str) -> str:
    text = (text or "").strip().lower()
    # Remove diacritics (acentos)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text


def detect_sql_snippets(text: str) -> bool:
    """Detect explicit SQL presence in text (code fences or SQL keywords)."""
    if not text:
        return False
    t = text.lower()
    if "```sql" in t or "select " in t or " join " in t or " where " in t or " group by " in t:
        return True
    return False


KEYWORDS_PT: dict[str, tuple[str, ...]] = {
    # Data/aggregation/filters
    "DATABASE": (
        "quantos",
        "quantidade",
        "numero",
        "número",
        "total",
        "media",
        "média",
        "taxa",
        "proporcao",
        "proporção",
        "top",
        "ranking",
        "mais comuns",
        "mais comum",
        "listar",
        "mostrar",
        "por cidade",
        "por ano",
        "por sexo",
        "distribuicao",
        "distribuição",
        "contagem",
        "contar",
        "soma",
        "sum",
        "avg",
        "media",
        "mediana",
        # Common data-query starters (covers MIN/MAX/COUNT/SUM questions)
        "qual",
        "quais",
        "principais",
        "principal",
        "menor",
        "maior",
        # "registrado/cadastrado" = data in the system (not SCHEMA introspection)
        "registrado",
        "registrada",
        "registrados",
        "registradas",
        "cadastrado",
        "cadastrada",
        "cadastrados",
        "cadastradas",
    ),
    # Explanations/definitions
    "CONVERSATIONAL": (
        "o que e",
        "o que eh",
        "o que significa",
        "definicao",
        "definição",
        "explica",
        "explicar",
        "por que",
        "porque",
        "como funciona",
        "diferenca",
        "diferença",
        "explique",
    ),
    # Schema/structure
    "SCHEMA": (
        "tabelas",
        "colunas",
        "schema",
        "estrutura",
        "dicionario de dados",
        "quais campos",
        "mostrar estrutura",
        "descrever tabela",
        "describe",
    ),
}


def keyword_scores(text: str) -> dict[str, int]:
    t = normalize_text(text)
    scores = {r: 0 for r in ROUTES}
    for route, kws in KEYWORDS_PT.items():
        for kw in kws:
            if kw in t:
                scores[route] += 1
    return scores


def heuristic_route(text: str) -> tuple[str, dict[str, int]]:
    scores = keyword_scores(text)
    # Pick max score; tie-break preference: SCHEMA > DATABASE > CONVERSATIONAL (safer)
    order = ["SCHEMA", "DATABASE", "CONVERSATIONAL"]
    best = max(order, key=lambda r: (scores.get(r, 0), -order.index(r)))
    return best, scores


def try_extract_json_block(s: str) -> dict | None:
    """Try to parse JSON from string; fallback to the first {...} block."""
    if not s:
        return None
    s = s.strip()
    # Direct parse
    try:
        return json.loads(s)
    except Exception:
        pass
    # Find first JSON object block
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def combine_scores(
    llm_route: str | None, llm_conf: float | None, heur_scores: dict[str, int], w_llm: float = 0.7
) -> str:
    """Combine LLM confidence with heuristic (normalized) to pick final route."""
    # Normalize heuristic scores into [0,1]
    max_h = max(heur_scores.values()) if heur_scores else 0
    norm = {r: (heur_scores[r] / max_h) if max_h > 0 else 0.0 for r in ROUTES}

    # If LLM data missing, use heuristic only
    if not llm_route or llm_conf is None:
        return max(ROUTES, key=lambda r: norm[r])

    # Weighted sum
    scores = {}
    for r in ROUTES:
        llm_term = llm_conf if r == llm_route else (1.0 - (llm_conf or 0.0)) * 0.5
        scores[r] = w_llm * llm_term + (1 - w_llm) * norm[r]
    # Pick best
    return max(ROUTES, key=lambda r: scores[r])
