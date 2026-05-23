"""Deterministic guardrails for when multi-query is allowed."""

import re
import time

from ..semantic.analytic_templates import analytic_metadata_for_plan
from ..semantic.planner import build_semantic_plan
from ..semantic.profile_store import load_profile_store
from ..utils.logging_config import get_nodes_logger
from .state_helpers import add_ai_message, update_phase
from .state_models import ExecutionPhase, MessagesStateTXT2SQL, QueryPlan, SubQuery

logger = get_nodes_logger()

_UNSUPPORTED_SCHEMA_METRIC_LABELS = {
    "medicacao": "medicamentos",
    "exames_laboratoriais": "exames laboratoriais",
    "vacina": "vacinacao",
    "area_rural_urbana": "zona rural ou urbana",
    "bairro": "bairro de residencia",
    "renda_individual": "renda individual do paciente",
    "plano_saude": "plano de saude do paciente",
    "sobrevida_pos_alta": "sobrevida apos alta sem seguimento",
    "reinternacao": "reinternacao sem identificador longitudinal",
    "consulta_ambulatorial": "tempo ate consulta ambulatorial",
    "resultado_imagem": "resultado de imagem",
    "sinais_vitais": "sinais vitais",
}

MULTI_ELIGIBLE_PLAN_TYPES = {
    "fanout_concat",
    "bind_then_query",
    "verification_side_query",
}

_RANKING_PATTERN = re.compile(
    r"(top\s*\d+|ranking|maior(?:es)?|menor(?:es)?|mais\s+(?:comum|frequente|realizad[oa]s?|alto|alta)|principais?)",
    re.I,
)
_SINGLE_WINDOW_GROUP_PATTERN = re.compile(
    r"(por|em cada|de cada)\s+(estado|munic[ií]pio|hospital|especialidade|cidade|uf|regi[aã]o)",
    re.I,
)
_SINGLE_CTE_PATTERN = re.compile(
    r"(crescimento|queda|varia[cç][aã]o|delta|evolu[cç][aã]o|compar[ae]|entre\s+\d{4}.*\d{4}|per[ií]odo|ao longo do tempo|s[ée]rie temporal)",
    re.I,
)
_SET_INTERSECTION_PATTERN = re.compile(
    r"(interse[cç][aã]o|ao mesmo tempo|simultaneamente|top\s*\d+.*top\s*\d+|est[aã]o entre.*e entre)",
    re.I,
)
_GLOBAL_LOCAL_AVG_PATTERN = re.compile(
    r"(acima da m[eé]dia|abaixo da m[eé]dia|m[eé]dia estadual|m[eé]dia nacional|m[eé]dia do estado|m[eé]dia do brasil|2x a m[eé]dia|duas vezes a m[eé]dia)",
    re.I,
)
_PIVOT_COMPARE_PATTERN = re.compile(
    r"(lado a lado|versus|\bvs\b|compare|compara[cç][aã]o|em rela[cç][aã]o a)",
    re.I,
)
_BIND_PATTERN = re.compile(
    r"(depois|em seguida|a partir desse|a partir deste|desse hospital|deste hospital|desse munic[ií]pio|deste munic[ií]pio|s[ée]rie temporal)",
    re.I,
)
_ENTITY_DISCOVERY_PATTERN = re.compile(
    r"(qual|encontre|descubra).*(hospital|munic[ií]pio|cidade|procedimento|diagn[oó]stico)",
    re.I,
)
_VERIFICATION_PATTERN = re.compile(
    r"(verifique|valide|confira|checagem|cheque)",
    re.I,
)
_FANOUT_PATTERN = re.compile(
    r"(por sexo|sexo masculino|sexo feminino|entre homens e mulheres|faixa et[aá]ria|faixa de idade|grupo et[aá]rio)",
    re.I,
)
_GEO_RESIDENCE_OR_HOSPITAL_PATTERN = re.compile(
    r"\b(resid[eê]ncia|residente|moradia|domic[ií]lio|hospital|hospitais|atendimento|estabelecimento|movimento|habitantes|popula[cç][aã]o)\b",
    re.I,
)
_GEO_AMBIGUOUS_PATTERN = re.compile(
    r"\b(munic[ií]pio|munic[ií]pios|cidade|cidades|uf|estado|estados)\b", re.I
)
_MORTALITY_INFANTIL_EXPLICIT_PATTERN = re.compile(
    r"\b(indicador|socioecon[oô]mic[ao]|socioeconomic[ao]|nascidos vivos|intern[açc][oõ]es?|crian[cç]as?|pedi[aá]tric[ao]s?)\b",
    re.I,
)
_COVID_CASE_SCOPE_PATTERN = re.compile(
    r"\b(casos?|casos?\s+de)\s+(covid|covid-19|coronavirus|coronav[ií]rus)\b|\b(covid|covid-19|coronavirus|coronav[ií]rus)\b.*\bcasos?\b",
    re.I,
)
_GENERIC_CASE_SCOPE_PATTERN = re.compile(r"\bcasos?\b", re.I)
_CASE_SCOPE_EXPLICIT_PATTERN = re.compile(
    r"\b(intern[açc][oõ]es?|diagn[oó]stico principal|diag_princ|procedimento|causa de morte|[óo]bitos?|mortes?)\b",
    re.I,
)
_RENDA_MORTALITY_AMBIGUITY_PATTERN = re.compile(
    r"\brenda\b.*\bmortalidade\b|\bmortalidade\b.*\brenda\b", re.I
)


def _build_single_plan(user_query: str, plan_type: str, reasoning: str) -> QueryPlan:
    return QueryPlan(
        strategy="single",
        plan_type=plan_type,
        reasoning=reasoning,
        merge_strategy="none",
        output_nodes=["sq1"],
        expected_output_shape={},
        verifier_checks=[],
        fallback_policy={},
        sub_queries=[
            SubQuery(
                id="sq1",
                description=user_query,
                purpose="final_output",
                output_role="output",
            )
        ],
    )


def classify_plan_type(user_query: str) -> tuple[str, str]:
    """Classify the query into a routing bucket using deterministic heuristics."""
    query = (user_query or "").strip()

    if not query:
        return "single_default", "Query vazia; usar SQL único por segurança."

    if _GLOBAL_LOCAL_AVG_PATTERN.search(query):
        return (
            "global_local_avg",
            "Comparações contra média global/estadual devem permanecer em uma SQL.",
        )

    if _SET_INTERSECTION_PATTERN.search(query):
        return "set_intersection", "Interseções de rankings exigem semântica relacional única."

    if _PIVOT_COMPARE_PATTERN.search(query):
        return "pivot_compare", "Comparações lado a lado são mais seguras em uma única SQL."

    if _SINGLE_WINDOW_GROUP_PATTERN.search(query) and _RANKING_PATTERN.search(query):
        return "single_window", "Ranking por grupo com partição deve permanecer em uma única SQL."

    if _ENTITY_DISCOVERY_PATTERN.search(query) and _BIND_PATTERN.search(query):
        return "bind_then_query", "A pergunta pede descobrir uma entidade e depois detalhá-la."

    # Two named states + ranking ("3 X no estado A e no estado B") → per-group top-N
    _two_state_re = re.compile(
        r"no\s+estado\s+(?:de\s+|do\s+|da\s+)?[A-Z]{2}\b.*?\bno\s+estado\s+(?:de\s+|do\s+|da\s+)?[A-Z]{2}\b",
    )
    if _two_state_re.search(query) and _RANKING_PATTERN.search(query):
        return (
            "single_window",
            "Top-N por estado nomeado deve usar ROW_NUMBER OVER PARTITION BY em SQL única.",
        )

    if _SINGLE_CTE_PATTERN.search(query):
        return (
            "single_cte",
            "Comparações temporais e lógica global devem permanecer em uma única SQL.",
        )

    if _VERIFICATION_PATTERN.search(query):
        return "verification_side_query", "A pergunta sugere uma checagem auxiliar separada."

    if _FANOUT_PATTERN.search(query):
        return (
            "fanout_concat",
            "A pergunta pode ser particionada em grupos independentes com merge por concatenação.",
        )

    return "single_default", "Sem padrão de multi-query seguro; usar SQL único."


def _critical_ambiguity_question(user_query: str) -> tuple[str, str] | None:
    query = (user_query or "").strip()
    if not query:
        return None

    if _COVID_CASE_SCOPE_PATTERN.search(query) and not _CASE_SCOPE_EXPLICIT_PATTERN.search(query):
        return (
            "clinical_covid_case_scope",
            "Quando voce diz casos de covid, quer internacoes com diagnostico principal de covid, "
            "procedimentos relacionados, ou obitos hospitalares nesse escopo?",
        )

    if _GENERIC_CASE_SCOPE_PATTERN.search(query) and not _CASE_SCOPE_EXPLICIT_PATTERN.search(query):
        return (
            "generic_case_scope",
            "Quando voce diz casos, quer contar internacoes, diagnosticos principais, "
            "procedimentos ou obitos hospitalares?",
        )

    if _RENDA_MORTALITY_AMBIGUITY_PATTERN.search(query):
        return (
            "renda_mortality_scope",
            "Quando voce diz renda e mortalidade, quer usar algum indicador socioeconomico "
            "disponivel como proxy, ou renda individual do paciente? Renda individual nao esta "
            "disponivel no schema atual.",
        )

    if "mortalidade infantil" in query.lower() and not _MORTALITY_INFANTIL_EXPLICIT_PATTERN.search(
        query
    ):
        return (
            "mortality_infantil_scope",
            "Quando voce diz mortalidade infantil, quer o indicador socioeconomico de mortalidade "
            "infantil ou obitos em internacoes de criancas?",
        )

    if "mortalidade infantil" in query.lower() and _MORTALITY_INFANTIL_EXPLICIT_PATTERN.search(
        query
    ):
        return None

    if _GEO_AMBIGUOUS_PATTERN.search(query) and not _GEO_RESIDENCE_OR_HOSPITAL_PATTERN.search(
        query
    ):
        if re.search(
            r"\bmortalidade\b|\btaxa de mortalidade\b|\bintern\w+\b|[óo]bitos?|mortes?|covid|diagn[oó]stic",
            query,
            re.I,
        ):
            return (
                "geography_residence_vs_hospital",
                "Voce quer usar a geografia de residencia do paciente ou a geografia do hospital/atendimento?",
            )

    return None


def plan_gate_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """Apply deterministic routing guardrails before invoking the LLM planner."""
    start_time = time.time()

    user_query = state.get("user_query", "")

    if state.get("force_single_query"):
        plan_type = "single_default"
        reasoning = "force_single_query está ativo; planner multi desabilitado para esta execução."
    else:
        plan_type, reasoning = classify_plan_type(user_query)

    multi_query_allowed = plan_type in MULTI_ELIGIBLE_PLAN_TYPES

    state["plan_type"] = plan_type
    state["multi_query_allowed"] = multi_query_allowed
    state["allowed_multi_plan_types"] = sorted(MULTI_ELIGIBLE_PLAN_TYPES)
    state["execution_mode"] = "multi_candidate" if multi_query_allowed else "single"

    if not multi_query_allowed:
        state["query_plan"] = _build_single_plan(user_query, plan_type, reasoning)
        state["is_multi_query"] = False
    else:
        state["query_plan"] = None
        state["is_multi_query"] = False

    semantic_plan = build_semantic_plan(user_query, profile_store=load_profile_store())
    semantic_plan_dump = semantic_plan.model_dump(exclude_none=True)
    state["semantic_plan"] = semantic_plan_dump
    meta = state.get("response_metadata", {}) or {}
    meta["semantic_plan"] = semantic_plan_dump
    meta["semantic_constraints"] = semantic_plan.constraints
    meta["semantic_null_policy"] = semantic_plan.null_policy
    meta.update(analytic_metadata_for_plan(semantic_plan))
    unsupported_schema_metrics = [
        item.split(":", 1)[1]
        for item in semantic_plan.ambiguities
        if item.startswith("unsupported_metric:")
    ]
    if unsupported_schema_metrics:
        metric_list = ", ".join(
            _UNSUPPORTED_SCHEMA_METRIC_LABELS.get(metric, metric)
            for metric in unsupported_schema_metrics
        )
        state["needs_clarification"] = True
        state["clarification_question"] = (
            "A metrica solicitada nao esta disponivel no schema atual "
            f"({metric_list}). Posso responder usando metricas disponiveis como "
            "populacao, PIB per capita, mortalidade infantil, leitos SUS ou medicos?"
        )
        state["current_error"] = None
        state["multi_query_allowed"] = False
        state["execution_mode"] = "clarification"
        meta["unsupported_schema_metric"] = unsupported_schema_metrics
    else:
        ambiguity = _critical_ambiguity_question(user_query)
        if ambiguity:
            ambiguity_code, question = ambiguity
            state["needs_clarification"] = True
            state["clarification_question"] = question
            state["current_error"] = None
            state["multi_query_allowed"] = False
            state["execution_mode"] = "clarification"
            meta["critical_ambiguity"] = ambiguity_code
    state["response_metadata"] = meta

    logger.info(
        "Plan gate classified query",
        extra={
            "plan_type": plan_type,
            "multi_query_allowed": multi_query_allowed,
        },
    )

    state = add_ai_message(
        state,
        f"Plan gate: {plan_type} ({'multi elegível' if multi_query_allowed else 'single obrigatório'}). {reasoning}",
    )
    state = update_phase(state, ExecutionPhase.REASONING, time.time() - start_time)
    return state
