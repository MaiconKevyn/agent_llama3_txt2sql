"""Execution-time SQL contracts shared by agent nodes and manager helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..semantic.plan_schema import SemanticPlan
from ..utils.sql_safety import is_select_only


@dataclass(frozen=True)
class SQLExecutionContractResult:
    allowed: bool
    reason: str = ""

    @property
    def error_message(self) -> str:
        if self.allowed:
            return ""
        return f"SQL execution blocked: {self.reason}"


def validate_sql_execution_contract(sql_query: str) -> SQLExecutionContractResult:
    ok, reason = is_select_only(sql_query)
    return SQLExecutionContractResult(allowed=ok, reason=reason)


def sql_mentions_output_dimension(sql: str, dimension: str) -> bool:
    text = sql.lower()
    patterns = {
        "estado": [r"\bsg_uf\b", r"\bestado\b"],
        "estado_hospital": [r"\bsg_uf\b", r"\bestado\b"],
        "municipio": [r"\bno_municipio\b", r"\bmunicipio\b", r"\bmunic[ií]pio\b"],
        "municipio_hospital": [r"\bno_municipio\b", r"\bmunicipio\b", r"\bmunic[ií]pio\b"],
        "regiao_saude": [
            r"\bno_regiao_saude\b",
            r"\bregiao_saude\b",
            r"\bregi[aã]o\s+de\s+sa[uú]de\b",
        ],
        "hospital": [r"\bcnes\b", r"\bhospital\b"],
        "especialidade": [r"\bespecialidade\b", r"\bespec\b", r"\bdescri[cç][aã]o\b"],
        "cid_capitulo": [
            r"\bcap[ií]tulo\b",
            r"\bcapitulo_cid\b",
            r"\bcid_capitulo\b",
            r"\bds_capitulo\b",
            r"\bsubstr\s*\(",
        ],
        "cid_categoria": [
            r"\bcategoria\b",
            r"\bcategoria_cid\b",
            r"\bcid_categoria\b",
            r"\bds_categoria\b",
        ],
        "cid_grupo": [r"\bgrupo\b", r"\bgrupo_cid\b", r"\bcid_grupo\b", r"\bds_grupo\b"],
        "cid_restrsexo": [r"\brestr(?:icao|ição|icoes|ições)?_?sexo\b", r"\brestrsexo\b"],
        "cid_codigo": [r"\bcid\b"],
        "cid_descricao": [r"\bdescri[cç][aã]o\b", r"\bdescricao\b"],
        "diagnostico": [r"\bdiag_princ\b", r"\bcid\b", r"\bdescri[cç][aã]o\b"],
        "procedimento": [r"\bproc_rea\b", r"\bnome_proc\b", r"\bprocedimento\b"],
        "marca_uti": [r"\bmarca_uti\b", r"\btipo_uti\b", r"\bdescri[cç][aã]o\b"],
        "sexo": [r"\bsexo\b", r"\bdescri[cç][aã]o\b"],
        "raca_cor": [r"\braca_cor\b", r"\bra[cç]a\b", r"\bcor\b"],
        "instrucao": [r"\binstru\b", r"\binstrucao\b", r"\binstru[cç][aã]o\b"],
        "idade": [r"\bidade\b"],
        "faixa_etaria": [r"\bfaixa\b", r"\bidade\b"],
        "ano": [r"\bano\b", r"\bextract\s*\(\s*year\b"],
        "mes": [r"\bmes\b", r"\bextract\s*\(\s*month\b"],
        "trimestre": [r"\btrimestre\b", r"\bextract\s*\(\s*quarter\b"],
        "dia_semana": [r"\bdia_semana\b", r"\bdayofweek\b", r"\bisodow\b"],
    }
    return any(re.search(pattern, text, re.I) for pattern in patterns.get(dimension, []))


def validate_post_execution_contract(
    semantic_plan: SemanticPlan | dict | None,
    sql: str,
    *,
    results: list[dict],
    row_count: int,
) -> tuple[bool, str | None]:
    if not semantic_plan or not sql:
        return True, None
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    unsupported = [
        ambiguity.removeprefix("unsupported_metric:")
        for ambiguity in plan.ambiguities
        if ambiguity.startswith("unsupported_metric:")
    ]
    if unsupported:
        return False, (
            "POST EXECUTION CONTRACT ERROR: query used unavailable schema metric(s): "
            + ", ".join(sorted(unsupported))
        )

    required_dimensions = plan.answer_shape.required_dimensions
    if required_dimensions and plan.answer_shape.row_grain != "single_scalar":
        missing_dimensions = [
            dimension
            for dimension in required_dimensions
            if not sql_mentions_output_dimension(sql, dimension)
        ]
        if missing_dimensions:
            return False, (
                "POST EXECUTION CONTRACT ERROR: successful SQL is missing requested output "
                f"dimension(s): {', '.join(missing_dimensions)}."
            )
        if (
            row_count <= 1
            and not results
            and plan.answer_shape.expected_row_count == "one_per_group"
        ):
            return False, (
                "POST EXECUTION CONTRACT ERROR: grouped query returned no rows, so it did not "
                "materialize the requested output dimensions."
            )
    return True, None
