"""Analytic completeness rubric for agent responses."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class AnalyticQuestion(BaseModel):
    id: str
    question: str
    expected_template: str
    expectations: list[str] = Field(default_factory=list)


class AnalyticQuestionSet(BaseModel):
    version: int
    questions: list[AnalyticQuestion]

    @classmethod
    def load_default(cls) -> AnalyticQuestionSet:
        path = Path(__file__).with_name("analytic_questions.json")
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


class AnalyticRubricScore(BaseModel):
    score: float
    passed: dict[str, bool]
    missing: list[str]


_RUBRIC_WEIGHTS = {
    "concept_resolution": 1.0,
    "cohort_scope": 1.0,
    "denominator_present": 1.0,
    "group_distribution_present": 1.0,
    "comparative_metric_present": 1.0,
    "faithful_final_answer": 1.0,
    "no_causal_overclaim": 1.0,
    "no_sample_only": 1.0,
}


def score_analytic_response(
    *,
    question: str,
    response: str,
    sql: str | None = None,
    semantic_plan: dict[str, Any] | None = None,
) -> AnalyticRubricScore:
    """Score whether a response satisfies analytic-completeness requirements."""
    response_lower = (response or "").lower()
    sql_lower = (sql or "").lower()
    semantic_plan = semantic_plan or {}
    constraints = set(semantic_plan.get("constraints") or [])

    question_lower = (question or "").lower()
    passed = {
        "concept_resolution": _has_concept_resolution(
            question_lower, response_lower, sql_lower, semantic_plan
        ),
        "cohort_scope": _has_scope(response_lower),
        "denominator_present": _has_denominator(response_lower, sql_lower),
        "group_distribution_present": _has_group_distribution(response_lower, sql_lower),
        "comparative_metric_present": _has_comparative_metric(response_lower, sql_lower),
        "faithful_final_answer": _has_direct_answer(response_lower),
        "no_causal_overclaim": not _has_causal_overclaim(response_lower),
        "no_sample_only": not _is_sample_only(response_lower, sql_lower, constraints),
    }
    total_weight = sum(_RUBRIC_WEIGHTS.values())
    achieved = sum(weight for key, weight in _RUBRIC_WEIGHTS.items() if passed[key])
    missing = [key for key, value in passed.items() if not value]
    return AnalyticRubricScore(
        score=round(achieved / total_weight, 3),
        passed=passed,
        missing=missing,
    )


def _has_concept_resolution(
    question_lower: str,
    response_lower: str,
    sql_lower: str,
    semantic_plan: dict[str, Any],
) -> bool:
    if not _question_requires_clinical_concept_resolution(question_lower, semantic_plan):
        return True
    if re.search(r"\bcid\b|\bc\d{2}\b|\bj00-j99\b", response_lower, re.I):
        return True
    if "diagnosticos_alvo" in sql_lower or "diag_princ" in sql_lower:
        return True
    filters = semantic_plan.get("filters") or []
    return any(
        item.get("field") in {"diagnostico_principal_codigo", "diagnostico_principal_prefix"}
        for item in filters
        if isinstance(item, dict)
    )


def _question_requires_clinical_concept_resolution(
    question_lower: str,
    semantic_plan: dict[str, Any],
) -> bool:
    filters = semantic_plan.get("filters") or []
    if any(
        item.get("field") in {
            "diagnostico_principal_codigo",
            "diagnostico_principal_prefix",
            "diagnostico_principal_descricao",
        }
        for item in filters
        if isinstance(item, dict)
    ):
        return True
    return any(
        token in question_lower
        for token in [
            "cid",
            "diagnostico",
            "diagnóstico",
            "cancer",
            "câncer",
            "covid",
            "respir",
            "pulmon",
            "prostata",
            "próstata",
        ]
    )


def _has_scope(response_lower: str) -> bool:
    return any(token in response_lower for token in ["escopo", "coorte", "usado", "considerando"])


def _has_denominator(response_lower: str, sql_lower: str) -> bool:
    return "denominador" in response_lower or "denominador" in sql_lower


def _has_group_distribution(response_lower: str, sql_lower: str) -> bool:
    return bool(
        "|" in response_lower
        or "faixa etária" in response_lower
        or "faixa_etaria" in sql_lower
        or "group by" in sql_lower
        or "distribuição" in response_lower
        or "distribuicao" in response_lower
    )


def _has_comparative_metric(response_lower: str, sql_lower: str) -> bool:
    return bool(
        re.search(r"\b\d+(?:,\d+)?x\b", response_lower)
        or "rate_ratio" in sql_lower
        or "razão" in response_lower
        or "razao" in response_lower
        or "compar" in response_lower
        or "taxa" in response_lower
    )


def _has_direct_answer(response_lower: str) -> bool:
    return bool(response_lower.strip()) and any(
        token in response_lower[:160] for token in ["sim", "não", "nao", "há", "ha", "existe"]
    )


def _has_causal_overclaim(response_lower: str) -> bool:
    causal_terms = ["causa ", "causou", "provoca", "provocou", "determina", "impacta diretamente"]
    return any(term in response_lower for term in causal_terms)


def _is_sample_only(response_lower: str, sql_lower: str, constraints: set[str]) -> bool:
    sample_language = any(
        token in response_lower
        for token in ["amostra parcial", "exemplo", "por exemplo", "mostrando"]
    )
    unrequested_limit = (
        "limit " in sql_lower and "top_n" not in constraints and "analysis_type" not in sql_lower
    )
    return sample_language or unrequested_limit
