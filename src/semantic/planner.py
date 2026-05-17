"""Conservative semantic planner for broad Text-to-SQL intent contracts.

This module intentionally avoids benchmark-specific rules. It extracts reusable
semantic patterns such as rates, rankings, per-group top-N, temporal series,
absence conditions, and null-bucket requirements.
"""

from __future__ import annotations

import re

from .plan_schema import (
    AnswerShape,
    SemanticDimension,
    SemanticFilter,
    SemanticMetric,
    SemanticPlan,
)
from .profile_store import SemanticProfileStore

_UF_RE = re.compile(
    r"\b(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b",
    re.I,
)

_STATE_NAME_TO_UF = {
    "acre": "AC",
    "alagoas": "AL",
    "amapá": "AP",
    "amapa": "AP",
    "amazonas": "AM",
    "bahia": "BA",
    "ceará": "CE",
    "ceara": "CE",
    "distrito federal": "DF",
    "espírito santo": "ES",
    "espirito santo": "ES",
    "goiás": "GO",
    "goias": "GO",
    "maranhão": "MA",
    "maranhao": "MA",
    "mato grosso": "MT",
    "mato grosso do sul": "MS",
    "minas gerais": "MG",
    "pará": "PA",
    "paraíba": "PB",
    "paraiba": "PB",
    "paraná": "PR",
    "parana": "PR",
    "pernambuco": "PE",
    "piauí": "PI",
    "piaui": "PI",
    "rio de janeiro": "RJ",
    "rio grande do norte": "RN",
    "rio grande do sul": "RS",
    "rondônia": "RO",
    "rondonia": "RO",
    "roraima": "RR",
    "santa catarina": "SC",
    "são paulo": "SP",
    "sao paulo": "SP",
    "sergipe": "SE",
    "tocantins": "TO",
}

_SOCIOECONOMIC_WIDE_METRICS = {
    "mortalidade_infantil_1ano",
    "populacao_total",
    "pib_per_capita",
    "leitos_sus_total",
    "medicos_total",
}

_UNSUPPORTED_SCHEMA_METRIC_PATTERNS = {
    "idhm": ["idhm", "índice de desenvolvimento humano", "indice de desenvolvimento humano"],
    "bolsa_familia": ["bolsa família", "bolsa familia"],
    "saneamento": ["saneamento", "esgotamento sanitário", "esgotamento sanitario"],
}


def _is_scalar_age_extrema_query(query_lower: str) -> bool:
    has_age = re.search(r"\bidade(?:s)?\b", query_lower)
    has_fact_scope = _contains_any(
        query_lower,
        ["internação", "internacao", "internações", "internacoes", "paciente", "pacientes"],
    )
    asks_min_or_max = re.search(r"\b(?:menor|mínima|minima|maior|máxima|maxima)\b", query_lower)
    return bool(has_age and has_fact_scope and asks_min_or_max)


def _is_scalar_value_extrema_query(query_lower: str) -> bool:
    """Detect scalar extrema questions over fact measures, not ranked entity lists."""
    if not re.search(
        r"\bqual\b[\s\S]{0,80}\b(?:maior|menor|máxima|maxima|mínima|minima)\b", query_lower
    ):
        return False
    if re.search(r"\bquais\b", query_lower):
        return False
    if _contains_any(
        query_lower,
        [
            "por estado",
            "por município",
            "por municipio",
            "por hospital",
            "por especialidade",
            "em cada",
            "de cada",
            "para cada",
        ],
    ):
        return False
    return _contains_any(
        query_lower,
        [
            "valor de serviço profissional",
            "valor de servico profissional",
            "serviço profissional",
            "servico profissional",
            "permanência hospitalar",
            "permanencia hospitalar",
            "dias de internação",
            "dias de internacao",
            "dias internados",
            "valor de internação",
            "valor de internacao",
            "valor da internação",
            "valor da internacao",
            "valor gasto",
            "custo",
            "val_sp",
            "val_sh",
            "val_tot",
        ],
    )


def _is_scalar_extrema_query(query_lower: str) -> bool:
    return _is_scalar_age_extrema_query(query_lower) or _is_scalar_value_extrema_query(query_lower)


def _has_identified_race_color_filter(query_lower: str) -> bool:
    has_race_color = _contains_any(query_lower, ["raça", "raca", "raça/cor", "raca/cor"])
    has_identified_scope = _contains_any(
        query_lower,
        [
            "identificada",
            "identificado",
            "identificadas",
            "identificados",
            "informada",
            "informado",
            "informadas",
            "informados",
            "registrada",
            "registrado",
            "registradas",
            "registrados",
            "excluindo sem informação",
            "excluindo sem informacao",
            "sem informação exclu",
            "sem informacao exclu",
        ],
    )
    return has_race_color and has_identified_scope


def _has_explicit_age_segments(query_lower: str) -> bool:
    return bool(
        re.search(r"\bmenos\s+de\s+\d+\s+anos?", query_lower)
        and re.search(r"\bentre\s+\d+\s+e\s+\d+\s+anos?", query_lower)
        and re.search(r"\b(?:acima|mais)\s+de\s+\d+\s+anos?", query_lower)
    )


def _has_cumulative_coverage_request(query_lower: str) -> bool:
    return bool(
        _contains_any(
            query_lower,
            [
                "cobrem até",
                "cobrem ate",
                "cobrir até",
                "cobrir ate",
                "percentual acumulado",
                "acumulado",
                "pareto",
            ],
        )
        and re.search(r"\b\d{1,3}\s*%", query_lower)
    )


def _extract_cumulative_threshold(query_lower: str) -> int | None:
    match = re.search(r"\b(\d{1,3})\s*%", query_lower)
    if not match:
        return None
    threshold = int(match.group(1))
    return threshold if 0 < threshold <= 100 else None


def _has_dual_top_n_intersection_request(query_lower: str) -> bool:
    return bool(
        _contains_any(query_lower, ["simultaneamente", "interseção", "intersecao"])
        and "top" in query_lower
        and _contains_any(query_lower, ["volume", "taxa de mortalidade"])
    )


def _has_death_cause_context(query_lower: str) -> bool:
    return _contains_any(
        query_lower,
        [
            "causa de morte",
            "causas de morte",
            "causa da morte",
            "causas da morte",
            "causa do óbito",
            "causas do óbito",
            "causa do obito",
            "causas do obito",
            "motivo de morte",
            "motivos de morte",
            "motivo da morte",
            "motivos da morte",
            "motivo do óbito",
            "motivos do óbito",
            "motivo do obito",
            "motivos do obito",
        ],
    )


def _extract_top_n(query_lower: str) -> int | None:
    number_words = {
        "um": 1,
        "uma": 1,
        "dois": 2,
        "duas": 2,
        "três": 3,
        "tres": 3,
        "quatro": 4,
        "cinco": 5,
        "seis": 6,
        "sete": 7,
        "oito": 8,
        "nove": 9,
        "dez": 10,
    }
    patterns = [
        r"\btop\s*-?\s*(\d+)\b",
        r"\b(\d+)\s+(?:principais|maiores|menores|mais\s+comuns|mais\s+frequentes)\b",
        r"\b(?:os|as)?\s*(\d+)\s+(?:munic[ií]pios|cidades|hospitais|procedimentos|diagn[oó]sticos|causas?|categorias?|itens?)\b",
        r"\b(?:os|as)\s+(\d+)\s+\w+\s+(?:com|de|mais|maior|menor)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, query_lower)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    word_pattern = "|".join(number_words)
    word_patterns = [
        rf"\b(?:os|as)\s+({word_pattern})\s+(?:munic[ií]pios|cidades|hospitais|procedimentos|diagn[oó]sticos|causas?|categorias?|itens?)\b",
        rf"\b({word_pattern})\s+(?:principais|maiores|menores|mais\s+comuns|mais\s+frequentes)\b",
    ]
    for pattern in word_patterns:
        match = re.search(pattern, query_lower)
        if match:
            return number_words[match.group(1)]
    if _is_scalar_extrema_query(query_lower):
        return None
    if re.search(
        r"\bprincipal\s+(?:causa|motivo)\s+(?:de|da|do)\s+(?:morte|[óo]bito)\b", query_lower
    ):
        return 1
    if re.search(r"\b(?:maior|menor|mais\s+comum|mais\s+frequente)\b", query_lower):
        return 1
    return None


def _extract_min_group_count(query_lower: str) -> int | None:
    patterns = [
        r"(?:mais\s+de|acima\s+de|mínimo\s+de|minimo\s+de)\s+(\d+)\s+interna[cç][oõ]es",
        r"(?:com|considerando)\s+(?:apenas\s+)?(?:grupos\s+com\s+)?(?:mais\s+de|mínimo\s+de|minimo\s+de)\s+(\d+)\b(?!\s+(?:anos?|de\s+idade)\b)",
    ]
    for pattern in patterns:
        match = re.search(pattern, query_lower)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def _extract_year_ranges(query_lower: str) -> list[tuple[str, str]]:
    ranges: list[tuple[str, str]] = []
    for match in re.finditer(
        r"\b((?:19|20)\d{2})\s*(?:-|a|até|ate)\s*((?:19|20)\d{2})\b",
        query_lower,
        re.I,
    ):
        ranges.append((match.group(1), match.group(2)))
    return ranges


def _extract_recent_year_window(query_lower: str) -> int | None:
    for pattern in [
        r"\b(?:últimos|ultimos|últimas|ultimas)\s+(\d+)\s+anos\b",
        r"\b(?:nos\s+)?(?:anos\s+)?mais\s+recentes\s*\(?\s*(\d+)\s+anos?\s*\)?",
    ]:
        match = re.search(pattern, query_lower, re.I)
        if match:
            return int(match.group(1))
    return None


def _dimension(name: str, source: str, role: str = "group") -> SemanticDimension:
    return SemanticDimension(name=name, source=source, role=role)


def _contains_any(query_lower: str, tokens: list[str]) -> bool:
    for token in tokens:
        if " " in token:
            if token in query_lower:
                return True
        elif re.search(rf"(?<!\w){re.escape(token)}(?!\w)", query_lower):
            return True
    return False


def _mentions_male(query_lower: str) -> bool:
    return bool(re.search(r"\b(homens?|masculin[oa]s?)\b", query_lower))


def _mentions_female(query_lower: str) -> bool:
    return bool(re.search(r"\b(mulheres?|ulheres?|feminin[oa]s?)\b", query_lower))


def _mentions_both_sexes(query_lower: str) -> bool:
    return _mentions_male(query_lower) and _mentions_female(query_lower)


def _extract_min_age(query_lower: str) -> int | None:
    for pattern in [
        r"\b(?:com|pacientes\s+com)\s+mais\s+de\s+(\d+)\s+anos\b",
        r"\bidade\s+acima\s+de\s+(\d+)\s+anos\b",
        r"\bmaiores\s+de\s+(\d+)\s+anos\b",
        r"\bidade\s*>\s*(\d+)\b",
    ]:
        match = re.search(pattern, query_lower)
        if match:
            return int(match.group(1))
    return None


def _extract_age_filters(query_lower: str) -> list[SemanticFilter]:
    filters: list[SemanticFilter] = []
    if _has_explicit_age_segments(query_lower):
        return filters
    for pattern in [
        r"\b(?:com|pacientes\s+com)\s+menos\s+de\s+(\d+)\s+anos?\b",
        r"\bmenores\s+de\s+(\d+)\s+anos?\b",
        r"\bidade\s*<\s*(\d+)\b",
    ]:
        match = re.search(pattern, query_lower)
        if not match:
            continue
        value = int(match.group(1))
        if value == 1:
            filters.append(SemanticFilter(field="idade", values=["0"], operator="="))
        else:
            filters.append(SemanticFilter(field="idade", values=[str(value)], operator="<"))
        return filters

    min_age = _extract_min_age(query_lower)
    if min_age is not None:
        filters.append(SemanticFilter(field="idade", values=[str(min_age)], operator=">"))
    return filters


def _extract_death_cause_description_term(query_lower: str) -> str | None:
    patterns = [
        r"\binterna[cç][oõ]es\s+por\s+(.+?)\s+ocasionaram\s+em\s+morte\b",
        r"\b(?:mortes|óbitos|obitos)\s+por\s+(.+?)(?:\?|$)",
        r"\bcaus(?:a|as)\s+de\s+morte\s+por\s+(.+?)(?:\?|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, query_lower)
        if not match:
            continue
        term = re.sub(
            r"\b(?:registradas?|ocasionadas?|em|internacoes|internações)\b", " ", match.group(1)
        )
        term = re.sub(r"[^\wÀ-ÿ -]", " ", term)
        term = re.sub(r"\s+", " ", term).strip()
        if term and not _is_grouping_or_temporal_term(term):
            return term
    return None


def _is_grouping_or_temporal_term(term: str) -> bool:
    """Avoid treating "mortes por <dimension>" as CID death-cause text."""

    normalized = term.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    grouping_terms = {
        "ano",
        "anos",
        "mês",
        "mes",
        "meses",
        "trimestre",
        "trimestres",
        "semestre",
        "semestres",
        "data",
        "periodo",
        "período",
        "estado",
        "estados",
        "uf",
        "ufs",
        "municipio",
        "município",
        "municipios",
        "municípios",
        "cidade",
        "cidades",
        "sexo",
        "genero",
        "gênero",
        "idade",
        "faixa etaria",
        "faixa etária",
        "hospital",
        "hospitais",
        "especialidade",
        "especialidades",
        "procedimento",
        "procedimentos",
        "regiao",
        "região",
        "regioes",
        "regiões",
    }
    if normalized in grouping_terms:
        return True
    return any(normalized.startswith(f"{term} ") for term in grouping_terms)


def _has_side_by_side_state_comparison(query_lower: str) -> bool:
    return _contains_any(
        query_lower,
        [
            "lado a lado",
            "comparando lado a lado",
            "comparação lado a lado",
            "comparacao lado a lado",
        ],
    ) and _contains_any(query_lower, ["estado", "estados", "uf", "ufs"])


def _has_parallel_state_top_n_context(query_lower: str) -> bool:
    if _contains_any(query_lower, ["combinado", "combinada", "total combinado"]):
        return False
    if _contains_any(query_lower, ["simultaneamente", "interseção", "intersecao"]):
        return False
    return bool(
        re.search(
            r"\b(?:no|na|do|da)\s+estado\s+d[eo]\s+\w+[\s\S]{0,80}\be\s+(?:no|na|do|da)\s+estado\s+d[eo]\s+\w+",
            query_lower,
            re.I,
        )
        or re.search(r"\bestados?\s+[a-z]{2}\s+e\s+[a-z]{2}\b", query_lower, re.I)
    )


def _catalog_cardinality_target(query_lower: str) -> str | None:
    """Detect reference-table cardinality intent, not fact-observed usage."""
    has_count = _contains_any(
        query_lower,
        ["quantos", "quantas", "número de", "numero de", "total de", "quantidade de"],
    )
    if not has_count:
        return None

    has_catalog_language = _contains_any(
        query_lower,
        [
            "existem",
            "existe",
            "estão cadastrados",
            "estao cadastrados",
            "cadastrados",
            "cadastradas",
            "disponíveis",
            "disponiveis",
            "distintos",
            "distintas",
            "diferentes",
            "tipos",
            "cobertos",
            "cobertas",
            "cobertura",
            "banco de dados",
        ],
    )
    has_fact_observation_language = _contains_any(
        query_lower,
        [
            "internações",
            "internacoes",
            "registrados em internações",
            "registrados nas internações",
            "observados",
            "usados",
            "utilizados",
            "pacientes",
            "internados",
            "hospitalizações",
            "hospitalizacoes",
        ],
    )
    if has_fact_observation_language:
        return None

    if _contains_any(query_lower, ["cid", "cid-10", "cids"]) and has_catalog_language:
        return "cid_catalog_count"

    if (
        _contains_any(
            query_lower,
            [
                "vínculo previdenciário",
                "vinculo previdenciario",
                "vínculos previdenciários",
                "vinculos previdenciarios",
                "situação previdenciária",
                "situacao previdenciaria",
            ],
        )
        and has_catalog_language
    ):
        return "vincprev_catalog_count"

    if _contains_any(query_lower, ["estado", "estados", "uf", "ufs"]) and _contains_any(
        query_lower, ["banco de dados", "cobertos", "cobertas", "cobertura"]
    ):
        return "estado_coverage_count"

    if _contains_any(query_lower, ["município", "municipio", "municípios", "municipios"]):
        asks_reference_count = has_catalog_language or _contains_any(
            query_lower,
            [
                "no estado",
                "do estado",
                "da uf",
                "na uf",
                "cadastrados no total",
                "cadastrados",
            ],
        )
        if asks_reference_count:
            return "municipio_catalog_count"

    return None


def _has_hospital_location_context(query_lower: str) -> bool:
    explicit_hospital_context = _contains_any(
        query_lower,
        [
            "atende",
            "atendem",
            "atendimento",
            "internacao_procedimento",
            "localização do hospital",
            "localizacao do hospital",
            "cidade do hospital",
            "município do hospital",
            "municipio do hospital",
            "onde ficam hospitais",
            "onde estão os hospitais",
            "onde estao os hospitais",
        ],
    )
    procedure_city_context = bool(
        re.search(r"\bnas\s+cidades?\b", query_lower)
        and _contains_any(
            query_lower, ["procedimento", "procedimentos", "atendimento", "internacao_procedimento"]
        )
    )
    return explicit_hospital_context or procedure_city_context


def _has_group_phrase(query_lower: str, dimension: str) -> bool:
    dimension_terms = {
        "estado": ["estado", "uf"],
        "municipio": ["município", "municipio", "cidade"],
        "municipio_hospital": [
            "município",
            "municipio",
            "cidade",
            "município de atendimento",
            "municipio de atendimento",
        ],
        "estado_hospital": ["estado", "uf", "estado de atendimento", "estado do hospital"],
        "hospital": ["hospital"],
        "especialidade": ["especialidade"],
        "diagnostico": ["diagnóstico", "diagnostico", "cid", "doença", "doenca"],
        "procedimento": ["procedimento"],
        "contraceptivo": [
            "contraceptivo",
            "contraceptivos",
            "método contraceptivo",
            "metodo contraceptivo",
        ],
        "sexo": ["sexo"],
        "raca_cor": ["raça", "raca", "cor"],
        "instrucao": [
            "instrução",
            "instrucao",
            "escolaridade",
            "nível de instrução",
            "nivel de instrucao",
            "grau de instrução",
            "grau de instrucao",
        ],
        "idade": ["idade", "idades"],
        "faixa_etaria": [
            "faixa etária",
            "faixa etaria",
            "faixa de idade",
            "grupo etário",
            "grupo etario",
        ],
        "ano": ["ano"],
        "mes": ["mês", "mes"],
        "trimestre": ["trimestre"],
        "dia_semana": ["dia da semana", "dias da semana"],
    }
    prefixes = ["por", "por cada", "para cada", "em cada", "de cada"]
    for term in dimension_terms.get(dimension, []):
        for prefix in prefixes:
            if f"{prefix} {term}" in query_lower:
                return True
    return False


def _is_entity_list_question(query_lower: str, dimension: str) -> bool:
    entity_patterns = {
        "estado": r"\bquais\s+(?:são\s+)?(?:os\s+|as\s+)?estados\b",
        "municipio": r"\bquais\s+(?:são\s+)?(?:os\s+|as\s+)?munic[ií]pios\b",
        "municipio_hospital": r"\bquais\s+(?:são\s+)?(?:os\s+|as\s+)?munic[ií]pios\b",
        "hospital": r"\bquais\s+(?:são\s+)?(?:os\s+|as\s+)?hospitais\b",
        "especialidade": r"\bquais\s+(?:são\s+)?(?:as\s+)?especialidades\b",
        "diagnostico": r"\bquais\s+(?:são\s+)?(?:os\s+|as\s+)?(?:c[oó]digos\s+cid|diagn[oó]sticos|cids|doenças|doencas)\b",
        "procedimento": r"\bquais\s+(?:são\s+)?(?:os\s+)?procedimentos\b",
        "contraceptivo": r"\b(?:qual|quais)\b[\s\S]{0,80}\b(?:contraceptivo|contraceptivos|m[eé]todo contraceptivo|m[eé]todos contraceptivos)\b",
    }
    pattern = entity_patterns.get(dimension)
    return bool(pattern and re.search(pattern, query_lower, re.I))


def _is_ranked_entity_group_question(query_lower: str, dimension: str) -> bool:
    terms = {
        "estado": r"estados?|ufs?",
        "estado_hospital": r"estados?|ufs?",
        "municipio": r"munic[ií]pios?|cidades?",
        "municipio_hospital": r"munic[ií]pios?|cidades?",
        "hospital": r"hospitais|cnes",
        "especialidade": r"especialidades?",
        "diagnostico": r"diagn[oó]sticos?|cids?|doen[cç]as?",
        "procedimento": r"procedimentos?",
    }
    term = terms.get(dimension)
    if not term:
        return False
    term_group = rf"(?:{term})"
    entity_near_rank = re.search(
        rf"\b{term_group}\b[\s\S]{{0,80}}\b(?:com|que\s+(?:teve|tiveram|tem|têm)|de)\b"
        r"[\s\S]{0,80}\b(?:mais|maior|menor|menos)\b",
        query_lower,
        re.I,
    )
    rank_near_entity = re.search(
        r"\b(?:mais|maior|menor|menos)\b[\s\S]{0,80}\b"
        rf"{term_group}\b",
        query_lower,
        re.I,
    )
    return bool(entity_near_rank or rank_near_entity)


def _is_temporal_entity_question(query_lower: str, dimension: str) -> bool:
    temporal_patterns = {
        "ano": [
            r"\bem\s+qual\s+ano\b",
            r"\bqual\s+ano\b",
            r"\bano\s+ocorreu\b",
        ],
        "mes": [
            r"\bem\s+qual\s+m[eê]s\b",
            r"\bqual\s+m[eê]s\b",
            r"\bm[eê]s\s+de\s+cada\s+ano\b",
        ],
    }
    return any(
        re.search(pattern, query_lower, re.I) for pattern in temporal_patterns.get(dimension, [])
    )


def _geography_mention_is_filter_context(query_lower: str, dimension: str) -> bool:
    if dimension not in {"municipio", "municipio_hospital", "estado", "estado_hospital"}:
        return False
    if _is_entity_list_question(query_lower, dimension):
        return False
    if _has_group_phrase(query_lower, dimension):
        return False
    has_geo_filter = bool(_UF_RE.search(query_lower)) or any(
        re.search(rf"(?<!\w){re.escape(name)}(?!\w)", query_lower, re.I)
        for name in _STATE_NAME_TO_UF
    )
    has_non_geo_rank_target = _contains_any(
        query_lower,
        [
            "procedimento",
            "procedimentos",
            "diagnóstico",
            "diagnostico",
            "cid",
            "hospital",
            "hospitais",
            "instrução",
            "instrucao",
            "escolaridade",
            "nível de instrução",
            "nivel de instrucao",
            "município",
            "municipio",
            "municípios",
            "municipios",
            "cidade",
            "cidades",
        ],
    )
    return has_geo_filter and has_non_geo_rank_target


def _filter_output_dimensions(
    dimensions: list[SemanticDimension],
    query_lower: str,
    *,
    top_n: int | None,
    has_temporal_trend: bool,
    has_distribution: bool,
    has_attribute_profile: bool,
    has_delta: bool,
) -> list[SemanticDimension]:
    """Keep only dimensions that define output grain, not scalar filters."""
    result: list[SemanticDimension] = []
    for dim in dimensions:
        if dim.name == "ano":
            keep = (
                has_temporal_trend
                or has_delta
                or _has_group_phrase(query_lower, dim.name)
                or _is_temporal_entity_question(query_lower, dim.name)
            )
        elif dim.name in {"mes", "trimestre", "dia_semana"}:
            keep = _has_group_phrase(query_lower, dim.name) or _is_temporal_entity_question(
                query_lower, dim.name
            )
        elif dim.name == "diagnostico" and _diagnosis_mention_is_filter_context(query_lower):
            keep = False
        elif _geography_mention_is_filter_context(query_lower, dim.name):
            keep = False
        elif dim.name in {"sexo", "raca_cor", "instrucao"}:
            keep = (
                has_distribution
                or has_attribute_profile
                or _has_group_phrase(query_lower, dim.name)
            )
        elif dim.name in {"idade", "faixa_etaria"}:
            keep = (
                has_distribution
                or _has_group_phrase(query_lower, dim.name)
                or _has_explicit_age_segments(query_lower)
            )
        else:
            keep = (
                has_distribution
                or _has_group_phrase(query_lower, dim.name)
                or _is_entity_list_question(query_lower, dim.name)
                or _is_ranked_entity_group_question(query_lower, dim.name)
                or bool(top_n)
            )
        if keep:
            result.append(dim)
    return result


def _counted_entity_from_scalar_question(
    query_lower: str,
    raw_dimensions: list[SemanticDimension],
    metrics: list[SemanticMetric],
) -> str | None:
    """Return the entity being counted without making it an output dimension."""
    if not any(metric.expression_type == "count" for metric in metrics):
        return None
    if not _contains_any(
        query_lower,
        ["quantos", "quantas", "número de", "numero de", "quantidade de", "total de"],
    ):
        return None
    if any(
        token in query_lower
        for token in [
            "por ",
            "para cada",
            "em cada",
            "de cada",
            "quais ",
            "distribuição",
            "distribuicao",
        ]
    ):
        return None

    priority = [
        "hospital",
        "municipio",
        "municipio_hospital",
        "estado",
        "estado_hospital",
        "diagnostico",
        "procedimento",
        "sexo",
        "idade",
    ]
    raw_names = [dim.name for dim in raw_dimensions]
    for name in priority:
        if name in raw_names:
            return name
    return None


def _answer_kind_for_row_grain(row_grain: str) -> str:
    return {
        "single_scalar": "scalar",
        "one_row_per_group": "grouped_table",
        "top_n_global": "top_n_global",
        "top_n_per_group": "top_n_per_group",
        "time_series": "time_series",
    }.get(row_grain, "unknown")


def _expected_row_count_for_row_grain(row_grain: str) -> str:
    return {
        "single_scalar": "one",
        "top_n_global": "bounded_n",
        "one_row_per_group": "one_per_group",
        "top_n_per_group": "one_per_group",
        "time_series": "one_per_group",
    }.get(row_grain, "unknown")


def _top_n_partition_dimensions(
    dimensions: list[SemanticDimension],
    query_lower: str,
    *,
    top_n_scope: str,
) -> list[str]:
    if top_n_scope != "per_group":
        return []
    return [dim.name for dim in dimensions if _has_group_phrase(query_lower, dim.name)]


def _diagnosis_mention_is_filter_context(query_lower: str) -> bool:
    """Treat disease categories as filters unless the user asks for a breakdown."""
    asks_scalar_count = _contains_any(
        query_lower,
        [
            "quantas",
            "quantos",
            "total",
            "percentual",
            "porcentagem",
            "taxa",
            "número de",
            "numero de",
            "quantidade de",
        ],
    )
    has_category = _contains_any(
        query_lower,
        [
            "doença respiratória",
            "doenca respiratoria",
            "doenças respiratórias",
            "doencas respiratorias",
        ],
    )
    asks_breakdown = _contains_any(
        query_lower,
        [
            "por diagnóstico",
            "por diagnostico",
            "por cid",
            "distribuição",
            "distribuicao",
            "quais diagnósticos",
            "quais diagnosticos",
        ],
    )
    return asks_scalar_count and has_category and not asks_breakdown


def _has_attribute_profile_intent(query_lower: str, dimensions: list[SemanticDimension]) -> bool:
    """Detect categorical profile questions such as "qual o sexo/raça/instrução dos pacientes"."""
    if not any(dim.name in {"sexo", "raca_cor", "instrucao"} for dim in dimensions):
        return False
    if not re.search(r"\b(?:qual|quais|como)\b", query_lower):
        return False
    if any(
        token in query_lower
        for token in [
            "taxa",
            "percentual",
            "proporção",
            "proporcao",
            "média",
            "media",
            "maior",
            "menor",
            "top",
        ]
    ):
        return False
    return _contains_any(
        query_lower,
        [
            "pacientes",
            "internados",
            "internadas",
            "internações",
            "internacoes",
            "hospitalizações",
            "hospitalizacoes",
        ],
    )


def _should_preserve_multi_value_filter_dimension(query_lower: str) -> bool:
    if _contains_any(
        query_lower,
        [
            "combinado",
            "combinada",
            "somado",
            "somada",
            "juntos",
            "juntas",
            "agregado",
            "agregada",
            "no total",
        ],
    ):
        return False
    if _contains_any(query_lower, ["simultaneamente", "interseção", "intersecao"]):
        return False
    return True


def _infer_dimensions(query_lower: str) -> list[SemanticDimension]:
    dims: list[SemanticDimension] = []
    hospital_location_context = _has_hospital_location_context(query_lower) or _contains_any(
        query_lower,
        ["hospital", "hospitais", "cnes"],
    )
    checks = [
        (
            "estado_hospital" if hospital_location_context else "estado",
            "municipios.SG_UF",
            ["estado", "estados", "uf", "ufs"],
        ),
        (
            "municipio_hospital" if hospital_location_context else "municipio",
            "municipios.NO_MUNICIPIO",
            ["município", "municipio", "municípios", "municipios", "cidade", "cidades"],
        ),
        ("hospital", "internacoes.CNES", ["hospital", "hospitais", "cnes"]),
        ("especialidade", "especialidade.DESCRICAO", ["especialidade"]),
        (
            "diagnostico",
            "cid.DESCRICAO",
            [
                "diagnóstico",
                "diagnostico",
                "diagnósticos",
                "diagnosticos",
                "cid",
                "causa de morte",
                "causas de morte",
                "causa da morte",
                "causas da morte",
                "causa do óbito",
                "causas do óbito",
                "causa do obito",
                "causas do obito",
                "motivo de morte",
                "motivos de morte",
                "motivo da morte",
                "motivos da morte",
                "motivo do óbito",
                "motivos do óbito",
                "motivo do obito",
                "motivos do obito",
                "motivo de internação",
                "motivo de internacao",
                "motivos de internação",
                "motivos de internacao",
                "doença",
                "doenca",
                "doenças",
                "doencas",
            ],
        ),
        ("procedimento", "procedimentos.NOME_PROC", ["procedimento", "procedimentos"]),
        (
            "contraceptivo",
            "contraceptivos.DESCRICAO",
            ["contraceptivo", "contraceptivos", "método contraceptivo", "metodo contraceptivo"],
        ),
        (
            "sexo",
            "internacoes.SEXO",
            [
                "sexo",
                "homem",
                "homens",
                "mulher",
                "mulheres",
                "ulher",
                "ulheres",
                "masculino",
                "feminino",
            ],
        ),
        ("raca_cor", "internacoes.RACA_COR", ["raça", "raca", "cor"]),
        (
            "instrucao",
            "instrucao.DESCRICAO",
            [
                "instrução",
                "instrucao",
                "escolaridade",
                "nível de instrução",
                "nivel de instrucao",
                "grau de instrução",
                "grau de instrucao",
            ],
        ),
        (
            "faixa_etaria",
            "internacoes.IDADE",
            ["faixa etária", "faixa etaria", "faixa de idade", "grupo etário", "grupo etario"],
        ),
        ("idade", "internacoes.IDADE", ["idade", "idades"]),
        (
            "ano",
            "EXTRACT(YEAR FROM internacoes.DT_INTER)",
            ["ano", "anual", "evolução", "evolucao"],
        ),
        ("mes", "EXTRACT(MONTH FROM internacoes.DT_INTER)", ["mês", "mes", "mensal"]),
        (
            "trimestre",
            "EXTRACT(QUARTER FROM internacoes.DT_INTER)",
            ["trimestre", "trimestral"],
        ),
        (
            "dia_semana",
            "tempo.dia_semana",
            ["dia da semana", "dias da semana"],
        ),
    ]
    for name, source, tokens in checks:
        if _contains_any(query_lower, tokens):
            dims.append(_dimension(name, source))
    if _has_explicit_age_segments(query_lower) and not any(
        dim.name == "faixa_etaria" for dim in dims
    ):
        dims.append(_dimension("faixa_etaria", "internacoes.IDADE"))
    if _extract_recent_year_window(query_lower) is not None and not any(
        dim.name == "ano" for dim in dims
    ):
        dims.append(_dimension("ano", "EXTRACT(YEAR FROM internacoes.DT_INTER)"))
    return dims


def _infer_metrics(query_lower: str) -> list[SemanticMetric]:
    metrics: list[SemanticMetric] = []
    catalog_metric = _catalog_cardinality_target(query_lower)

    if catalog_metric:
        metrics.append(SemanticMetric(name=catalog_metric, expression_type="count"))
    else:
        if _has_cumulative_coverage_request(query_lower):
            metrics.append(
                SemanticMetric(
                    name="percentual_acumulado",
                    expression_type="rate",
                    required_filters=["SUM(COUNT(*)) OVER"],
                )
            )
        if _contains_any(
            query_lower,
            ["custo por dia", "custo/dia", "custo por diária", "custo por diaria"],
        ):
            metrics.append(
                SemanticMetric(
                    name="custo_por_dia",
                    expression_type="ratio",
                    required_filters=["SUM(VAL_TOT)", "SUM(DIAS_PERM)"],
                )
            )
        if _contains_any(
            query_lower,
            [
                "taxa de internação em uti",
                "taxa de internacao em uti",
                "taxa de uti",
                "percentual de internações em uti",
                "percentual de internacoes em uti",
            ],
        ):
            metrics.append(
                SemanticMetric(
                    name="taxa_uti",
                    expression_type="rate",
                    numerator_condition="VAL_UTI > 0",
                    denominator_scope="all_rows_matching_scope_filters",
                )
            )
        is_extreme_max = re.search(r"\b(?:maior|máxima|maxima)\b", query_lower)
        is_extreme_min = re.search(r"\b(?:menor|mínima|minima)\b", query_lower)
        extreme_type = "max" if is_extreme_max else "min" if is_extreme_min else None
        if _is_scalar_age_extrema_query(query_lower):
            if extreme_type == "min":
                metrics.append(SemanticMetric(name="idade_minima", expression_type="min"))
            elif extreme_type == "max":
                metrics.append(SemanticMetric(name="idade_maxima", expression_type="max"))
        if _is_scalar_value_extrema_query(query_lower) and extreme_type is not None:
            if _contains_any(
                query_lower,
                [
                    "serviço profissional",
                    "servico profissional",
                    "valor de serviço profissional",
                    "valor de servico profissional",
                    "val_sp",
                ],
            ):
                metrics.append(
                    SemanticMetric(
                        name="valor_servico_profissional",
                        expression_type=extreme_type,
                        required_filters=[f"{extreme_type.upper()}(VAL_SP)"],
                    )
                )
            elif _contains_any(
                query_lower,
                [
                    "permanência hospitalar",
                    "permanencia hospitalar",
                    "dias de internação",
                    "dias de internacao",
                    "dias internados",
                ],
            ):
                metrics.append(
                    SemanticMetric(
                        name="permanencia_hospitalar",
                        expression_type=extreme_type,
                        required_filters=[f"{extreme_type.upper()}(DIAS_PERM)"],
                    )
                )
            elif _contains_any(
                query_lower,
                [
                    "serviço hospitalar",
                    "servico hospitalar",
                    "valor de serviço hospitalar",
                    "valor de servico hospitalar",
                    "val_sh",
                ],
            ):
                metrics.append(
                    SemanticMetric(
                        name="valor_servico_hospitalar",
                        expression_type=extreme_type,
                        required_filters=[f"{extreme_type.upper()}(VAL_SH)"],
                    )
                )
            else:
                metrics.append(
                    SemanticMetric(
                        name="valor_internacao",
                        expression_type=extreme_type,
                        required_filters=[f"{extreme_type.upper()}(VAL_TOT)"],
                    )
                )
        if _contains_any(query_lower, ["total", "valor total", "total gasto"]) and _contains_any(
            query_lower,
            [
                "dias de internação",
                "dias de internacao",
                "dias internados",
                "dias de permanência",
                "dias de permanencia",
            ],
        ):
            metrics.append(
                SemanticMetric(
                    name="total_dias_permanencia",
                    expression_type="sum",
                    required_filters=["SUM(DIAS_PERM)"],
                )
            )
        elif _contains_any(query_lower, ["total", "valor total", "total gasto"]) and _contains_any(
            query_lower,
            [
                "serviços profissionais",
                "servicos profissionais",
                "serviço profissional",
                "servico profissional",
                "val_sp",
            ],
        ):
            metrics.append(
                SemanticMetric(
                    name="total_servico_profissional",
                    expression_type="sum",
                    required_filters=["SUM(VAL_SP)"],
                )
            )
        elif _contains_any(query_lower, ["total", "valor total", "total gasto"]) and _contains_any(
            query_lower,
            [
                "serviço hospitalar",
                "servico hospitalar",
                "val_sh",
            ],
        ):
            metrics.append(
                SemanticMetric(
                    name="total_servico_hospitalar",
                    expression_type="sum",
                    required_filters=["SUM(VAL_SH)"],
                )
            )
        elif _contains_any(query_lower, ["valor total", "total gasto"]) and _contains_any(
            query_lower, ["internação", "internacao", "internações", "internacoes"]
        ):
            metrics.append(
                SemanticMetric(
                    name="valor_total_internacoes",
                    expression_type="sum",
                    required_filters=["SUM(VAL_TOT)"],
                )
            )
        if "mortalidade infantil" in query_lower:
            metrics.append(
                SemanticMetric(
                    name="mortalidade_infantil_1ano",
                    expression_type="avg",
                    required_filters=['AVG(s."VL_MORT_INFANTIL")'],
                )
            )
        if _contains_any(query_lower, ["população", "populacao", "habitantes"]):
            metrics.append(
                SemanticMetric(
                    name="populacao_total",
                    expression_type="sum",
                    required_filters=['SUM(s."QT_POPULACAO")'],
                )
            )
        if _contains_any(query_lower, ["pib per capita", "produto interno bruto per capita"]):
            metrics.append(
                SemanticMetric(
                    name="pib_per_capita",
                    expression_type="avg",
                    required_filters=['AVG(s."VL_PIB_PERCAPITA")'],
                )
            )
        if _contains_any(query_lower, ["leitos sus", "leito sus"]):
            metrics.append(
                SemanticMetric(
                    name="leitos_sus_total",
                    expression_type="sum",
                    required_filters=['SUM(s."QT_LEITOS_SUS")'],
                )
            )
        if _contains_any(query_lower, ["médicos", "medicos"]):
            metrics.append(
                SemanticMetric(
                    name="medicos_total",
                    expression_type="sum",
                    required_filters=['SUM(s."QT_MEDICOS")'],
                )
            )
    if "mortalidade infantil" not in query_lower and any(
        token in query_lower for token in ["taxa de mortalidade", "mortalidade hospitalar"]
    ):
        metrics.append(
            SemanticMetric(
                name="taxa_mortalidade",
                expression_type="rate",
                numerator_condition="MORTE = true",
                denominator_scope="all_rows_matching_non_outcome_filters",
            )
        )
    elif not metrics and any(
        token in query_lower for token in ["taxa", "percentual", "proporção", "proporcao"]
    ):
        metrics.append(
            SemanticMetric(
                name="proporcao",
                expression_type="rate",
                denominator_scope="all_rows_matching_scope_filters",
            )
        )

    if _contains_any(query_lower, ["receita total", "receita", "faturamento total"]):
        metrics.append(
            SemanticMetric(
                name="receita_total",
                expression_type="sum",
                required_filters=["SUM(VAL_TOT)"],
            )
        )

    has_specific_average_metric = False
    if _contains_any(
        query_lower,
        [
            "dias de internação",
            "dias de internacao",
            "dias de permanência",
            "dias de permanencia",
            "tempo de permanência",
            "tempo de permanencia",
        ],
    ) and any(token in query_lower for token in ["média", "media"]):
        metrics.append(
            SemanticMetric(
                name="media_dias_permanencia",
                expression_type="avg",
                required_filters=["AVG(DIAS_PERM)"],
            )
        )
        has_specific_average_metric = True

    if _contains_any(
        query_lower,
        ["val_sh", "serviço hospitalar", "servico hospitalar", "valor de serviço hospitalar"],
    ) and any(token in query_lower for token in ["valor médio", "valor medio", "média", "media"]):
        metrics.append(
            SemanticMetric(
                name="media_val_sh",
                expression_type="avg",
                required_filters=["AVG(VAL_SH)"],
            )
        )
        has_specific_average_metric = True

    if (
        "mortalidade infantil" not in query_lower
        and not any(metric.expression_type == "rate" for metric in metrics)
        and not _contains_any(
            query_lower,
            [
                "mortalidade infantil",
                "população",
                "populacao",
                "habitantes",
                "pib per capita",
                "leitos sus",
                "médicos",
                "medicos",
            ],
        )
        and not has_specific_average_metric
        and any(
            token in query_lower
            for token in [
                "custo médio",
                "custo medio",
                "valor médio",
                "valor medio",
                "média",
                "media",
            ]
        )
    ):
        metric_name = "custo_medio_uti" if "uti" in query_lower else "media"
        required = ["VAL_UTI > 0"] if "uti" in query_lower else []
        metrics.append(
            SemanticMetric(name=metric_name, expression_type="avg", required_filters=required)
        )

    has_socioeconomico_metric = any(
        metric.name in _SOCIOECONOMIC_WIDE_METRICS for metric in metrics
    )

    has_explicit_non_count_metric = any(
        metric.expression_type in {"sum", "avg", "min", "max", "rate", "delta", "value", "ratio"}
        for metric in metrics
    )
    if (
        not catalog_metric
        and not has_socioeconomico_metric
        and not has_explicit_non_count_metric
        and (
            any(
                token in query_lower
                for token in ["total", "quantos", "quantas", "número de", "numero de", "quantidade"]
            )
            or any(
                token in query_lower
                for token in ["pacientes", "internacoes", "internaçoes", "internações"]
            )
        )
    ):
        metrics.append(SemanticMetric(name="total", expression_type="count"))

    if any(
        token in query_lower for token in ["crescimento", "queda", "variação", "variacao", "delta"]
    ):
        metrics.append(SemanticMetric(name="delta_temporal", expression_type="delta"))

    if not metrics and any(token in query_lower for token in ["óbito", "obito", "morte", "mortes"]):
        metrics.append(
            SemanticMetric(
                name="total_mortes",
                expression_type="count",
                required_filters=["MORTE = true"],
            )
        )

    if not metrics:
        metrics.append(SemanticMetric(name="requested_metric", expression_type="unknown"))

    return metrics


def _unsupported_schema_metrics(query_lower: str) -> list[str]:
    unsupported: list[str] = []
    for metric_name, aliases in _UNSUPPORTED_SCHEMA_METRIC_PATTERNS.items():
        if _contains_any(query_lower, aliases):
            unsupported.append(metric_name)
    return unsupported


def _infer_filters(query: str, query_lower: str) -> list[SemanticFilter]:
    filters: list[SemanticFilter] = []
    ufs = sorted({m.group(1).upper() for m in _UF_RE.finditer(query) if m.group(1).isupper()})
    for state_name, uf in sorted(
        _STATE_NAME_TO_UF.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if re.search(rf"(?<!\w){re.escape(state_name)}(?!\w)", query_lower, re.I):
            ufs.append(uf)
    ufs = sorted(set(ufs))
    if ufs:
        filters.append(
            SemanticFilter(field="estado", values=ufs, operator="IN" if len(ufs) > 1 else "=")
        )

    recent_year_window = _extract_recent_year_window(query_lower)
    if recent_year_window is not None:
        filters.append(
            SemanticFilter(
                field="recent_years_available",
                values=[str(recent_year_window)],
                operator="last_n_available",
            )
        )

    year_ranges = _extract_year_ranges(query_lower)
    years = sorted({m.group(0) for m in re.finditer(r"\b(?:19|20)\d{2}\b", query)})
    if len(year_ranges) >= 2:
        range_years = {year for year_range in year_ranges for year in year_range}
        for index, (start_year, end_year) in enumerate(year_ranges[:2], start=1):
            filters.append(
                SemanticFilter(
                    field=f"period_{index}",
                    values=[start_year, end_year],
                    operator="BETWEEN",
                )
            )
        years = [year for year in years if year not in range_years]
    elif year_ranges:
        start_year, end_year = year_ranges[0]
        filters.append(
            SemanticFilter(field="ano_intervalo", values=[start_year, end_year], operator="BETWEEN")
        )
        years = [year for year in years if year not in {start_year, end_year}]
    if years:
        filters.append(
            SemanticFilter(field="ano", values=years, operator="IN" if len(years) > 1 else "=")
        )

    if _contains_any(
        query_lower,
        ["uti", "unidade de terapia intensiva", "terapia intensiva", "custo de uti"],
    ):
        filters.append(SemanticFilter(field="uti", values=["VAL_UTI > 0"], operator="semantic"))
    if _contains_any(
        query_lower,
        [
            "obstétrica",
            "obstetrica",
            "obstétricas",
            "obstetricas",
            "obstétrico",
            "obstetrico",
            "obstétricos",
            "obstetricos",
            "parto",
            "gestante",
            "gestantes",
        ],
    ):
        filters.append(
            SemanticFilter(field="obstetrico", values=["ESPEC = 2"], operator="semantic")
        )
    if _contains_any(query_lower, ["inverno", "junho a agosto", "junho até agosto"]):
        filters.append(
            SemanticFilter(field="mes_internacao", values=["6", "7", "8"], operator="IN")
        )
    if _contains_any(
        query_lower,
        [
            "doença respiratória",
            "doenca respiratoria",
            "doenças respiratórias",
            "doencas respiratorias",
        ],
    ):
        filters.append(
            SemanticFilter(field="diagnostico_principal_prefix", values=["J%"], operator="LIKE")
        )
    if (
        _contains_any(query_lower, ["diagnóstico principal", "diagnostico principal"])
        and _contains_any(
            query_lower,
            ["diagnóstico secundário", "diagnostico secundario", "secundário", "secundario"],
        )
        and _contains_any(query_lower, ["tanto", "ambos", "ambas"])
    ):
        filters.append(
            SemanticFilter(
                field="diagnostico_principal_required", values=["IS NOT NULL"], operator="semantic"
            )
        )
        filters.append(
            SemanticFilter(
                field="diagnostico_secundario_required", values=["IS NOT NULL"], operator="semantic"
            )
        )
    if _mentions_both_sexes(query_lower):
        filters.append(SemanticFilter(field="sexo", values=["1", "3"], operator="IN"))
    else:
        if _mentions_male(query_lower):
            filters.append(SemanticFilter(field="sexo", values=["1"], operator="="))
        if _mentions_female(query_lower):
            filters.append(SemanticFilter(field="sexo", values=["3"], operator="="))
    if _has_identified_race_color_filter(query_lower):
        filters.append(
            SemanticFilter(
                field="raca_cor_identificada",
                values=["RACA_COR IN (1, 2, 3, 4, 5)"],
                operator="semantic",
            )
        )
    filters.extend(_extract_age_filters(query_lower))
    death_cause_term = _extract_death_cause_description_term(query_lower)
    if death_cause_term:
        filters.append(
            SemanticFilter(
                field="diagnostico_principal_descricao",
                values=[death_cause_term],
                operator="ILIKE",
            )
        )
    asks_rate = any(
        token in query_lower for token in ["taxa", "percentual", "proporção", "proporcao"]
    )
    if (
        any(token in query_lower for token in ["óbito", "obito", "morte", "mortes"])
        and not asks_rate
    ):
        filters.append(
            SemanticFilter(field="desfecho", values=["MORTE = true"], operator="semantic")
        )

    return filters


def build_semantic_plan(
    user_query: str,
    profile_store: SemanticProfileStore | None = None,
) -> SemanticPlan:
    """Build a generic semantic contract for a user question."""
    query = user_query or ""
    q = query.lower()

    top_n = _extract_top_n(q)
    unsupported_schema_metrics = _unsupported_schema_metrics(q)
    explicit_min_group_count = _extract_min_group_count(q)
    raw_dimensions = _infer_dimensions(q)
    metrics = _infer_metrics(q)
    filters = _infer_filters(query, q)
    metric_names = {metric.name for metric in metrics}
    catalog_cardinality_metrics = {
        "cid_catalog_count",
        "vincprev_catalog_count",
        "municipio_catalog_count",
        "estado_coverage_count",
    }
    is_catalog_cardinality = bool(metric_names & catalog_cardinality_metrics)

    has_monthly_trend = _contains_any(q, ["mensal", "mensais", "por mês", "por mes", "monthly"])
    has_temporal_trend = (
        has_monthly_trend
        or any(
            token in q
            for token in [
                "evolução",
                "evolucao",
                "série temporal",
                "serie temporal",
                "ao longo",
                "anual",
            ]
        )
        or _extract_recent_year_window(q) is not None
    )
    has_sex_breakdown = (
        not has_temporal_trend
        and _mentions_both_sexes(q)
        and _contains_any(
            q,
            [
                "entre",
                "comparando",
                "comparar",
                "compare",
                "comparação",
                "comparacao",
                "pizza",
                "pie",
                "donut",
                "rosca",
            ],
        )
    )
    has_distribution = (
        any(token in q for token in ["distribuição", "distribuicao", "como se distribui"])
        or has_sex_breakdown
    )
    has_moving_average = _contains_any(q, ["média móvel", "media movel"])
    has_quartile_distribution = _contains_any(q, ["quartil", "quartis"])
    has_cumulative_coverage = _has_cumulative_coverage_request(q)
    has_dual_top_n_intersection = _has_dual_top_n_intersection_request(q)
    has_attribute_profile = _has_attribute_profile_intent(q, raw_dimensions)
    has_explicit_age_segments = _has_explicit_age_segments(q)
    excludes_unknown_bucket = _contains_any(
        q,
        [
            "excluindo sem informação",
            "excluindo sem informacao",
            "excluir sem informação",
            "excluir sem informacao",
            "sem informação exclu",
            "sem informacao exclu",
        ],
    )
    has_unknown_bucket = (not excludes_unknown_bucket) and any(
        token in q
        for token in [
            "sem informação",
            "sem informacao",
            "não informado",
            "nao informado",
            "incluindo os casos sem",
        ]
    )
    has_absence = (not excludes_unknown_bucket) and (
        any(
            token in q
            for token in [
                "nunca",
                "nenhum",
                "nenhuma",
                "sem registro",
                "não tiveram",
                "nao tiveram",
            ]
        )
        or ("sem " in q and not has_unknown_bucket)
    )
    has_above_below_cohort = _contains_any(q, ["acima e abaixo", "abaixo e acima"]) or (
        _contains_any(q, ["compare", "comparar", "comparação", "comparacao"])
        and _contains_any(q, ["acima da média", "acima da media"])
        and _contains_any(q, ["abaixo da média", "abaixo da media"])
    )
    has_rate = any(metric.expression_type == "rate" for metric in metrics)
    has_delta = any(metric.expression_type == "delta" for metric in metrics)
    has_side_by_side_state = _has_side_by_side_state_comparison(q)
    dimensions = _filter_output_dimensions(
        raw_dimensions,
        q,
        top_n=top_n,
        has_temporal_trend=has_temporal_trend,
        has_distribution=has_distribution,
        has_attribute_profile=has_attribute_profile,
        has_delta=has_delta,
    )
    if has_temporal_trend and not any(
        dim.name in {"ano", "mes", "trimestre", "dia_semana"} for dim in dimensions
    ):
        temporal_name = "mes" if has_monthly_trend else "ano"
        temporal_source = (
            'EXTRACT(MONTH FROM internacoes."DT_INTER")'
            if temporal_name == "mes"
            else 'EXTRACT(YEAR FROM internacoes."DT_INTER")'
        )
        dimensions.append(
            SemanticDimension(
                name=temporal_name,
                source=temporal_source,
                role="group",
            )
        )
    if _should_preserve_multi_value_filter_dimension(q):
        multi_value_filter_fields = {
            semantic_filter.field for semantic_filter in filters if len(semantic_filter.values) > 1
        }
        if multi_value_filter_fields & {"estado", "estado_residencia"} and not any(
            dim.name in {"estado", "estado_hospital"} for dim in dimensions
        ):
            state_dimension = next(
                (dim for dim in raw_dimensions if dim.name in {"estado", "estado_hospital"}),
                None,
            )
            if state_dimension is not None:
                dimensions.append(state_dimension)

    dimensions = [
        dim
        for dim in dimensions
        if not (
            dim.name in {"estado", "estado_hospital", "municipio", "municipio_hospital"}
            and _geography_mention_is_filter_context(q, dim.name)
            and not _should_preserve_multi_value_filter_dimension(q)
        )
    ]

    if has_side_by_side_state:
        dimensions = [dim for dim in dimensions if dim.name not in {"estado", "estado_hospital"}]

    per_group_tokens = [
        "por estado",
        "em cada estado",
        "de cada estado",
        "por município",
        "por municipio",
        "em cada município",
        "em cada municipio",
        "por hospital",
        "em cada hospital",
        "por especialidade",
        "em cada especialidade",
        "por ano",
        "em cada ano",
        "de cada ano",
        "para cada ano",
        "por sexo",
        "para cada sexo",
        "em cada sexo",
        "cada sexo",
        "por faixa",
        "para cada faixa",
        "em cada faixa",
        "por grupo",
        "para cada grupo",
        "em cada grupo",
    ]
    has_multi_state_filter = any(
        semantic_filter.field in {"estado", "estado_residencia"} and len(semantic_filter.values) > 1
        for semantic_filter in filters
    )
    top_n_scope = (
        "per_group"
        if top_n
        and (
            any(token in q for token in per_group_tokens)
            or has_explicit_age_segments
            or (has_multi_state_filter and _has_parallel_state_top_n_context(q))
        )
        else ("global" if top_n else "none")
    )

    if has_temporal_trend or has_delta or has_moving_average:
        intent = "trend"
    elif top_n:
        intent = "ranking"
    elif has_distribution or has_attribute_profile:
        intent = "distribution"
    elif has_rate:
        intent = "rate"
    elif any(metric.expression_type in {"min", "max"} for metric in metrics):
        intent = "lookup"
    elif any(metric.name == "total" for metric in metrics) or any(
        token in q for token in ["quantos", "quantas", "número de", "numero de", "total de"]
    ):
        intent = "count"
    else:
        intent = "unknown"

    required_dimensions = [
        dim.name
        for dim in dimensions
        if dim.name
        in {
            "estado",
            "estado_hospital",
            "municipio",
            "municipio_hospital",
            "hospital",
            "especialidade",
            "diagnostico",
            "procedimento",
            "contraceptivo",
            "sexo",
            "raca_cor",
            "instrucao",
            "idade",
            "faixa_etaria",
            "ano",
            "mes",
            "trimestre",
            "dia_semana",
            "quartil",
        }
    ]
    constraints: list[str] = []
    null_policy: list[str] = []
    partition_dimensions = _top_n_partition_dimensions(
        dimensions,
        q,
        top_n_scope=top_n_scope,
    )
    if top_n_scope == "per_group" and has_explicit_age_segments and not partition_dimensions:
        partition_dimensions = ["faixa_etaria"]
    if (
        top_n_scope == "per_group"
        and has_multi_state_filter
        and not partition_dimensions
        and any(dim.name in {"estado", "estado_hospital"} for dim in dimensions)
    ):
        partition_dimensions = [
            next(dim.name for dim in dimensions if dim.name in {"estado", "estado_hospital"})
        ]
    ranked_dimensions = (
        [dim for dim in required_dimensions if dim not in partition_dimensions]
        if top_n_scope == "per_group"
        else []
    )

    if is_catalog_cardinality:
        constraints.append("catalog_cardinality_must_use_reference_table")
    if has_moving_average:
        constraints.append("moving_average_requires_preaggregated_time_series")
    if any(semantic_filter.field == "recent_years_available" for semantic_filter in filters):
        constraints.append("relative_recent_years_use_available_data_max_year")
    if has_quartile_distribution:
        constraints.append("quartile_distribution_requires_ntile_interval")
        if not any(dim.name == "quartil" for dim in dimensions):
            dimensions.append(
                SemanticDimension(
                    name="quartil",
                    source="NTILE(4) OVER (ORDER BY COUNT(*))",
                    role="group",
                )
            )
        if "quartil" not in required_dimensions:
            required_dimensions.append("quartil")
    if has_cumulative_coverage:
        constraints.append("cumulative_coverage_threshold_required")
        cumulative_threshold = _extract_cumulative_threshold(q)
        if cumulative_threshold is not None:
            filters.append(
                SemanticFilter(
                    field="cumulative_percentage_threshold",
                    values=[str(cumulative_threshold)],
                    operator="<=",
                )
            )
    if top_n_scope == "per_group":
        constraints.append("top_n_per_group_requires_window_partition")
    if (
        "diagnostico" in required_dimensions
        and _has_death_cause_context(q)
        and not _contains_any(q, ["cid_morte", "cid morte"])
    ):
        constraints.append("death_cause_requires_diag_princ_with_morte")
    if has_side_by_side_state:
        constraints.append("side_by_side_state_pivot_required")
    if has_rate:
        constraints.append("rate_denominator_must_preserve_full_scope")
    raw_hospital_location_context = any(
        dim.name in {"municipio_hospital", "estado_hospital"} for dim in raw_dimensions
    )
    if any(dim.name in {"municipio_hospital", "estado_hospital"} for dim in dimensions) or (
        raw_hospital_location_context
        and _geography_mention_is_filter_context(q, "municipio_hospital")
    ):
        constraints.append("join_path_hospital_location_required")
    if any(
        _geography_mention_is_filter_context(q, dim.name)
        for dim in raw_dimensions
        if dim.name in {"municipio", "municipio_hospital", "estado", "estado_hospital"}
    ):
        constraints.append("geographic_filter_dimension_not_output")
    if _diagnosis_mention_is_filter_context(q):
        constraints.append("diagnosis_filter_dimension_not_output")
    if "contraceptivo" in required_dimensions:
        constraints.append("contraceptive_obstetric_filter_required")
        if not any(semantic_filter.field == "obstetrico" for semantic_filter in filters):
            filters.append(
                SemanticFilter(field="obstetrico", values=["ESPEC = 2"], operator="semantic")
            )
    if "sexo" in required_dimensions:
        constraints.append("sex_label_output_required")
    if "instrucao" in required_dimensions:
        constraints.append("domain_instrucao_valid_required")
        if not any(semantic_filter.field == "instrucao_valid" for semantic_filter in filters):
            filters.append(
                SemanticFilter(
                    field="instrucao_valid",
                    values=["INSTRU IS NOT NULL", "INSTRU != 0"],
                    operator="semantic",
                )
            )
    if "raca_cor" in required_dimensions:
        constraints.append("categorical_lookup_label_required")
    if metric_names & _SOCIOECONOMIC_WIDE_METRICS:
        constraints.append("socioeconomico_column_metric_required")
    if len(metric_names & _SOCIOECONOMIC_WIDE_METRICS) >= 2:
        constraints.append("socioeconomico_multi_column_metrics_required")
    if has_absence:
        constraints.append("absence_condition_requires_antijoin_or_aggregate_zero")
    if (
        has_absence
        and _contains_any(q, ["causa de morte", "causas de morte", "óbitos", "obitos"])
        and _contains_any(q, ["diagnóstico principal", "diagnostico principal"])
        and _contains_any(q, ["cid_morte", "cid morte"])
    ):
        constraints.append("death_cause_cid_requires_cid_morte_antijoin")
    if any(
        semantic_filter.field == "diagnostico_principal_descricao" for semantic_filter in filters
    ):
        constraints.append("death_cause_description_requires_diag_princ_with_morte")
    period_filters = [
        semantic_filter
        for semantic_filter in filters
        if semantic_filter.field.startswith("period_")
    ]
    if has_delta or "entre" in q and len([f for f in filters if f.field == "ano"]) >= 1:
        constraints.append("temporal_comparison_requires_separate_period_aggregates")
    if has_delta and len(period_filters) >= 2:
        constraints.append("temporal_comparison_requires_matched_period_entities")
        constraints.append("temporal_comparison_outputs_period_counts_and_delta")
        if _contains_any(q, ["crescimento", "aumento", "maior crescimento"]):
            constraints.append("temporal_growth_uses_after_minus_before")
        if _contains_any(q, ["queda", "redução", "reducao", "diminuição", "diminuicao"]):
            constraints.append("temporal_decline_uses_before_minus_after")
    if has_unknown_bucket:
        null_policy.append("include_unknown_bucket_with_left_join_or_coalesce")
    if (
        has_rate
        and any(
            semantic_filter.field == "diagnostico_principal_prefix" for semantic_filter in filters
        )
        and "trimestre" in required_dimensions
    ):
        constraints.append("percentage_denominator_matches_filtered_category")
    if (
        has_rate
        and "dia_semana" in required_dimensions
        and any(semantic_filter.field == "uti" for semantic_filter in filters)
    ):
        constraints.append("filtered_cohort_percentage_distribution")
        if "rate_denominator_must_preserve_full_scope" in constraints:
            constraints.remove("rate_denominator_must_preserve_full_scope")
    if has_rate and _contains_any(
        q,
        [
            "duas vezes",
            "2 vezes",
        ],
    ):
        constraints.append("reference_rate_comparison_required")
    if has_dual_top_n_intersection:
        constraints.append("dual_top_n_intersection_required")

    high_cardinality_average_rank = (
        top_n
        and top_n_scope == "per_group"
        and any(metric.expression_type in {"avg", "rate"} for metric in metrics)
        and any(
            dim in {"hospital", "municipio", "municipio_hospital"} for dim in required_dimensions
        )
    )
    if high_cardinality_average_rank:
        constraints.append("top_n_average_high_cardinality_requires_minimum_group_size")

    if explicit_min_group_count is not None:
        filters.append(
            SemanticFilter(
                field="minimum_group_count",
                values=[str(explicit_min_group_count)],
                operator=">",
            )
        )
    elif high_cardinality_average_rank:
        filters.append(SemanticFilter(field="minimum_group_count", values=["100"], operator=">"))

    if intent == "count" and not required_dimensions and not top_n:
        row_grain = "single_scalar"
    elif (
        not required_dimensions
        and not top_n
        and not has_temporal_trend
        and not has_above_below_cohort
        and any(metric.expression_type != "unknown" for metric in metrics)
    ):
        row_grain = "single_scalar"
    elif has_above_below_cohort:
        row_grain = "one_row_per_group"
    elif top_n_scope == "per_group":
        row_grain = "top_n_per_group"
    elif top_n_scope == "global":
        row_grain = "top_n_global"
    elif has_temporal_trend or has_moving_average:
        row_grain = "time_series"
    elif required_dimensions:
        row_grain = "one_row_per_group"
    else:
        row_grain = "unknown"

    requires_group_by = bool(required_dimensions and row_grain != "single_scalar")
    value_metric_ranking = row_grain == "top_n_global" and (
        any(metric.expression_type == "value" for metric in metrics)
        or any(metric.name == "populacao_total" for metric in metrics)
    )
    if value_metric_ranking:
        requires_group_by = False

    output_dimensions = list(required_dimensions)
    filter_dimensions = [
        dim.name
        for dim in raw_dimensions
        if dim.name not in output_dimensions
        and (
            any(semantic_filter.field.startswith(dim.name) for semantic_filter in filters)
            or _geography_mention_is_filter_context(q, dim.name)
            or _diagnosis_mention_is_filter_context(q)
        )
    ]
    counted_entity = _counted_entity_from_scalar_question(q, raw_dimensions, metrics)
    forbidden_output_dimensions = []
    if row_grain == "single_scalar":
        forbidden_output_dimensions = [
            dim.name for dim in raw_dimensions if dim.name not in output_dimensions
        ]

    answer_shape = AnswerShape(
        row_grain=row_grain,
        top_n=top_n,
        top_n_scope=top_n_scope,
        required_dimensions=required_dimensions,
        partition_dimensions=partition_dimensions,
        ranked_dimensions=ranked_dimensions,
        requires_group_by=requires_group_by,
        include_unknown_bucket=has_unknown_bucket,
        answer_kind=_answer_kind_for_row_grain(row_grain),
        expected_row_count=_expected_row_count_for_row_grain(row_grain),
        output_dimensions=output_dimensions,
        filter_dimensions=sorted(set(filter_dimensions)),
        counted_entity=counted_entity,
        forbidden_output_dimensions=sorted(set(forbidden_output_dimensions)),
    )

    base_grain = "internacao"
    if "cid_catalog_count" in metric_names:
        base_grain = "cid_catalog"
    elif "vincprev_catalog_count" in metric_names:
        base_grain = "vincprev_catalog"
    elif metric_names & {"municipio_catalog_count", "estado_coverage_count"}:
        base_grain = "municipio_catalog"
    elif any(
        token in q
        for token in [
            "mortalidade infantil",
            "população",
            "populacao",
            "habitantes",
            "pib per capita",
            "leitos sus",
            "médicos",
            "medicos",
        ]
    ):
        base_grain = "municipio_ano"
    elif "procedimento" in q:
        base_grain = "procedimento_ocorrencia"

    plan = SemanticPlan(
        intent=intent,
        base_grain=base_grain,
        metrics=metrics,
        dimensions=dimensions,
        filters=filters,
        answer_shape=answer_shape,
        constraints=constraints,
        null_policy=null_policy,
        ambiguities=[
            f"unsupported_metric:{metric_name}" for metric_name in unsupported_schema_metrics
        ],
    )
    if profile_store is not None:
        _enrich_plan_with_profile(plan, query, profile_store)
    return plan


_DIMENSION_PROFILE_COLUMNS = {
    "estado": ("municipios", "SG_UF"),
    "hospital": ("internacoes", "CNES"),
    "procedimento": ("internacao_procedimento", "PROC_REA"),
    "sexo": ("internacoes", "SEXO"),
    "raca_cor": ("internacoes", "RACA_COR"),
    "ano": ("internacoes", "DT_INTER"),
    "mes": ("internacoes", "DT_INTER"),
}


def _enrich_plan_with_profile(
    plan: SemanticPlan,
    user_query: str,
    profile_store: SemanticProfileStore,
) -> None:
    q = user_query.lower()

    if any(dim.name in {"ano", "mes"} for dim in plan.dimensions) or _contains_any(
        q, ["ano", "anual", "mensal", "mês", "mes", "evolução", "evolucao"]
    ):
        temporal_range = profile_store.temporal_range("internacoes", "DT_INTER")
        if temporal_range:
            min_value, max_value = temporal_range
            plan.ambiguities.append(
                f"profile_temporal_coverage: internacoes.DT_INTER ranges from {min_value} to {max_value}"
            )
            _append_temporal_filter_warnings(plan, min_value, max_value)

    for dim in plan.dimensions:
        column_ref = _DIMENSION_PROFILE_COLUMNS.get(dim.name)
        if not column_ref:
            continue
        table, column = column_ref
        column_profile = profile_store.get_column(table, column)
        if column_profile is None:
            continue
        if column_profile.kind == "identifier" or profile_store.high_cardinality(table, column):
            plan.ambiguities.append(
                f"profile_cardinality: {dim.name} uses high-cardinality identifier {table}.{column}"
            )
        null_rate = profile_store.null_rate(table, column)
        if null_rate and null_rate > 0:
            plan.ambiguities.append(
                f"profile_nulls: {table}.{column} has null_rate={null_rate:.3f}"
            )

    if plan.answer_shape.include_unknown_bucket and not plan.null_policy:
        plan.null_policy.append("include_unknown_bucket_with_left_join_or_coalesce")

    if "sexo" in plan.answer_shape.required_dimensions:
        _add_domain_hint(plan, profile_store, "internacoes", "SEXO")


def _append_temporal_filter_warnings(
    plan: SemanticPlan,
    min_value: str | None,
    max_value: str | None,
) -> None:
    if not min_value or not max_value:
        return
    min_year = _extract_year(min_value)
    max_year = _extract_year(max_value)
    if min_year is None or max_year is None:
        return
    for semantic_filter in plan.filters:
        if semantic_filter.field != "ano":
            continue
        for value in semantic_filter.values:
            try:
                year = int(value)
            except ValueError:
                continue
            if year < min_year or year > max_year:
                plan.ambiguities.append(
                    f"profile_temporal_filter_out_of_range: ano={year} outside {min_year}-{max_year}"
                )


def _add_domain_hint(
    plan: SemanticPlan,
    profile_store: SemanticProfileStore,
    table: str,
    column: str,
) -> None:
    profile = profile_store.get_column(table, column)
    if profile is None or not profile.top_values:
        return
    values = [str(item.get("value")) for item in profile.top_values[:5]]
    plan.ambiguities.append(f"profile_domain_values: {table}.{column} common_values={values}")


def _extract_year(value: str) -> int | None:
    match = re.search(r"\b(?:19|20)\d{2}\b", value)
    if not match:
        return None
    return int(match.group(0))
