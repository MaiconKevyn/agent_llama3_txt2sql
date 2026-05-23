"""Pure CID-related semantic rules used by the planner."""

from __future__ import annotations

import re

from .plan_schema import SemanticFilter

CID_CATALOG_DIMENSION_SOURCES = {
    "cid_codigo": "cid.CID",
    "cid_descricao": "cid.DESCRICAO",
    "cid_categoria": "cid.DS_CATEGORIA",
    "cid_grupo": "cid.DS_GRUPO",
    "cid_capitulo": "cid.DS_CAPITULO",
    "cid_restrsexo": "cid.RESTRSEXO",
}


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def has_missing_cid_lookup_request(query_lower: str) -> bool:
    has_primary_diagnosis = _contains_any(
        query_lower,
        [
            "diagnosticos principais",
            "diagnósticos principais",
            "diagnostico principal",
            "diagnóstico principal",
            "diag_princ",
        ],
    )
    has_catalog = _contains_any(query_lower, ["catalogo cid", "catálogo cid", "cid"])
    has_missing_lookup = _contains_any(
        query_lower,
        [
            "nao existem",
            "não existem",
            "nao existe",
            "não existe",
            "sem lookup",
            "sem cadastro",
            "fora do catalogo",
            "fora do catálogo",
        ],
    )
    return has_primary_diagnosis and has_catalog and has_missing_lookup


def has_cid_chapter_context(query_lower: str) -> bool:
    return bool(
        re.search(r"\bcap[ií]tulos?\s+(?:do\s+)?cid\b", query_lower, re.I)
        or re.search(r"\bcid[\s-]*10\s+cap[ií]tulos?\b", query_lower, re.I)
    )


def has_cid_catalog_lookup_context(query_lower: str) -> bool:
    if not re.search(r"\b(?:cids?|cid[\s-]*10|cid10)\b", query_lower, re.I):
        return False
    if _contains_any(
        query_lower,
        [
            "frequente",
            "frequentes",
            "frequencia",
            "freqüência",
            "concentram",
            "concentraram",
            "tiveram mais",
            "aparecem mais",
            "em criancas",
            "em crianças",
            "em idosos",
            "em idosas",
        ],
    ):
        return False
    if _contains_any(
        query_lower,
        [
            "internação",
            "internacao",
            "internações",
            "internacoes",
            "hospitalização",
            "hospitalizacao",
            "hospitalizações",
            "hospitalizacoes",
            "paciente",
            "pacientes",
            "internado",
            "internada",
            "internados",
            "internadas",
            "óbito",
            "obito",
            "óbitos",
            "obitos",
            "morte",
            "mortes",
            "mortalidade",
            "valor",
            "custo",
            "gasto",
            "permanência",
            "permanencia",
            "uti",
        ],
    ):
        return False
    return _contains_any(
        query_lower,
        [
            "catalogo",
            "catálogo",
            "base",
            "existem",
            "existe",
            "liste",
            "listar",
            "quais",
            "código",
            "codigo",
            "códigos",
            "codigos",
            "descrição",
            "descricao",
            "descrições",
            "descricoes",
            "categoria cid",
            "categorias cid",
            "grupo cid",
            "grupos cid",
            "capitulo cid",
            "capítulo cid",
            "restricao",
            "restrição",
            "restricoes",
            "restrições",
        ],
    )


def extract_explicit_cid_prefix_filters(query_lower: str) -> list[SemanticFilter]:
    patterns = [
        r"\bcids?\b[\s\S]{0,60}\b(?:c[oó]digo\s+)?(?:come[cç]a|inicia)\s+com\s+([a-z]\d{1,2}[a-z0-9]?)\b",
        r"\bc[oó]digo\s+come[cç]a\s+com\s+([a-z]\d{1,2}[a-z0-9]?)\b",
        r"\bprefixo\s+cid\s+([a-z]\d{1,2}[a-z0-9]?)\b",
    ]
    filters: list[SemanticFilter] = []
    seen: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, query_lower, re.I):
            prefix = match.group(1).upper()
            if not prefix.endswith("%"):
                prefix = f"{prefix}%"
            if prefix in seen:
                continue
            seen.add(prefix)
            filters.append(
                SemanticFilter(
                    field="diagnostico_principal_prefix", values=[prefix], operator="LIKE"
                )
            )
    return filters


def extract_cid_catalog_search_terms(query_lower: str) -> list[str]:
    patterns = [
        r"\b(?:representam|relacionad[oa]s?\s+a|para|mencionam|cont[eê]m|contem)\s+(.+?)\??$",
        r"\bquero\s+analisar\s+(.+?)\.\s+quais\s+cids?\b",
    ]
    terms: list[str] = []
    for pattern in patterns:
        match = re.search(pattern, query_lower, re.I)
        if not match:
            continue
        raw = match.group(1)
        raw = re.sub(
            r"\b(?:cid|cids|diagn[oó]stico|principal|devo|considerar)\b", " ", raw, flags=re.I
        )
        for part in re.split(r"\s+ou\s+|\s+e\s+|,", raw):
            value = re.sub(r"\s+", " ", part).strip(" .?")
            if len(value) >= 3:
                terms.append(value)
    return list(dict.fromkeys(terms))


def cid_catalog_dimension_from_query(query_lower: str) -> str | None:
    if re.search(r"\brestri[cç][oõ]es?\b[\s\S]{0,60}\bsexo\b", query_lower, re.I):
        return "cid_restrsexo"
    if re.search(r"\bgrupos?\s+(?:do\s+)?cid\b", query_lower, re.I):
        return "cid_grupo"
    if re.search(r"\bcategorias?\s+(?:do\s+)?cid\b", query_lower, re.I):
        return "cid_categoria"
    if has_cid_chapter_context(query_lower):
        return "cid_capitulo"
    if re.search(r"\bdescri[cç][oõ]es?\s+(?:do\s+)?cid\b", query_lower, re.I):
        return "cid_descricao"
    if re.search(r"\b(?:c[oó]digos?\s+cid|cids?)\b", query_lower, re.I):
        return "cid_codigo"
    return None


def is_cid_duplicate_description_query(query_lower: str) -> bool:
    return bool(
        _contains_any(
            query_lower, ["descricoes cid", "descrições cid", "descricao cid", "descrição cid"]
        )
        and _contains_any(query_lower, ["repetidas", "repetidos", "duplicadas", "duplicados"])
    )
