"""Contract rubric for intent/tool-planning generalization checks."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.agent.intent_plan import build_intent_plan
from src.agent.plan_auditor import audit_pre_sql_plan
from src.agent.sql_generation import _build_deterministic_chart_sql
from src.semantic.planner import build_semantic_plan
from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
from src.visualization.intent import detect_visualization_intent


class IntentGeneralizationQuestion(BaseModel):
    id: str
    persona: str
    question: str
    family: str
    expected_intent: dict[str, str]
    expected_concepts: list[str] = Field(default_factory=list)
    expected_tables: list[str] = Field(default_factory=list)
    judge: str
    anti_overfit_family: str


@dataclass(frozen=True)
class IntentGeneralizationTrace:
    intent_plan: dict[str, Any]
    semantic_plan: dict[str, Any]
    chart_plan: dict[str, Any]
    plan_audit: dict[str, Any]
    generated_chart_sql: str | None
    chart_sql_valid: bool
    chart_sql_message: str | None
    resolved_concepts: list[str]

    def model_dump(self) -> dict[str, Any]:
        return {
            "intent_plan": self.intent_plan,
            "semantic_plan": self.semantic_plan,
            "chart_plan": self.chart_plan,
            "plan_audit": self.plan_audit,
            "generated_chart_sql": self.generated_chart_sql,
            "chart_sql_valid": self.chart_sql_valid,
            "chart_sql_message": self.chart_sql_message,
            "resolved_concepts": self.resolved_concepts,
        }


def load_intent_generalization_questions(
    path: Path | None = None,
) -> list[IntentGeneralizationQuestion]:
    path = path or Path(__file__).with_name("intent_generalization_questions.jsonl")
    questions: list[IntentGeneralizationQuestion] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            questions.append(IntentGeneralizationQuestion.model_validate_json(line))
        except Exception as exc:
            raise ValueError(f"Invalid intent question at {path}:{line_number}: {exc}") from exc
    return questions


def build_intent_generalization_trace(question: str) -> IntentGeneralizationTrace:
    intent_plan = build_intent_plan(question)
    semantic_plan = build_semantic_plan(question)
    chart_plan = build_chart_plan(
        question,
        detect_visualization_intent(question),
        semantic_plan.model_dump(exclude_none=True),
    )
    plan_audit = audit_pre_sql_plan(
        user_query=question,
        semantic_plan=semantic_plan,
        chart_plan=chart_plan,
    )
    generated_chart_sql = (
        _build_deterministic_chart_sql(semantic_plan, chart_plan)
        if chart_plan.requested
        else None
    )
    chart_sql_valid, chart_sql_message = validate_sql_against_chart_plan(
        chart_plan,
        generated_chart_sql or "",
    )
    resolved_concepts = _resolved_concepts(
        question=question,
        intent_plan=intent_plan.model_dump(exclude_none=True),
        semantic_plan=semantic_plan.model_dump(exclude_none=True),
        plan_audit=plan_audit,
    )
    return IntentGeneralizationTrace(
        intent_plan=intent_plan.model_dump(exclude_none=True),
        semantic_plan=semantic_plan.model_dump(exclude_none=True),
        chart_plan=chart_plan.model_dump(exclude_none=True),
        plan_audit=plan_audit,
        generated_chart_sql=generated_chart_sql,
        chart_sql_valid=chart_sql_valid,
        chart_sql_message=chart_sql_message,
        resolved_concepts=sorted(resolved_concepts),
    )


def score_intent_generalization(
    item: IntentGeneralizationQuestion,
    trace: IntentGeneralizationTrace,
) -> dict[str, Any]:
    missing: list[str] = []
    expected_presentation = item.expected_intent.get("presentation")
    expected_task = item.expected_intent.get("task")
    intent_plan = trace.intent_plan

    if expected_presentation and intent_plan.get("presentation") != expected_presentation:
        missing.append(
            f"presentation:{intent_plan.get('presentation')}!={expected_presentation}"
        )

    if expected_task and not _task_matches(
        expected=expected_task,
        actual=str(intent_plan.get("primary_task") or ""),
        semantic_intent=str(trace.semantic_plan.get("intent") or ""),
    ):
        missing.append(f"task:{intent_plan.get('primary_task')}!={expected_task}")

    if item.judge == "safe_refusal":
        if intent_plan.get("primary_task") != "out_of_scope":
            missing.append("safe_refusal:not_out_of_scope")
        return _score_result(item, trace, missing)

    resolved = set(trace.resolved_concepts)
    for concept in item.expected_concepts:
        if concept in _OPTIONAL_CONCEPTS:
            continue
        if concept not in resolved:
            missing.append(f"concept:{concept}")

    if "chart_contract" in item.judge:
        if not trace.chart_plan.get("requested"):
            missing.append("chart:not_requested")
        elif not trace.chart_sql_valid:
            missing.append(f"chart_sql:{trace.chart_sql_message or 'invalid'}")

    if item.judge == "no_respiratory_overtrigger" and "respiratory_cid" in resolved:
        missing.append("overtrigger:respiratory_cid")
    if item.judge == "no_death_overtrigger" and "death_outcome" in resolved:
        missing.append("overtrigger:death_outcome")
    if item.judge == "no_child_overtrigger" and "child_age_policy" in resolved:
        missing.append("overtrigger:child_age_policy")
    if item.judge == "no_under18_overtrigger" and "child_age_policy" in resolved:
        missing.append("overtrigger:under18_default_for_custom_age")

    if not trace.plan_audit.get("passed") and item.judge != "safe_refusal":
        for error in trace.plan_audit.get("errors", []):
            missing.append(f"plan_audit:{error.get('code')}")

    return _score_result(item, trace, missing)


def dump_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


_OPTIONAL_CONCEPTS = {
    "observational_caveat",
    "seasonality",
    "causality",
}


def _score_result(
    item: IntentGeneralizationQuestion,
    trace: IntentGeneralizationTrace,
    missing: list[str],
) -> dict[str, Any]:
    unique_missing = list(dict.fromkeys(missing))
    return {
        "passed": not unique_missing,
        "missing": unique_missing,
        "family": item.family,
        "judge": item.judge,
        "resolved_concepts": trace.resolved_concepts,
        "chart_sql_valid": trace.chart_sql_valid,
        "chart_sql_message": trace.chart_sql_message,
    }


def _task_matches(*, expected: str, actual: str, semantic_intent: str) -> bool:
    if actual == expected:
        return True
    compatible = {
        "trend": {"chart", "comparison", "data_quality"},
        "chart": {"trend", "breakdown", "ranking"},
        "association": {"comparison", "ranking"},
        "comparison": {"association"},
        "breakdown": {"chart", "distribution"},
        "ranking": {"chart"},
        "direct_metric": {"chart", "count", "rate"},
        "data_quality": {"count", "trend"},
    }
    return actual in compatible.get(expected, set()) or semantic_intent in compatible.get(
        expected, set()
    )


def _resolved_concepts(
    *,
    question: str,
    intent_plan: dict[str, Any],
    semantic_plan: dict[str, Any],
    plan_audit: dict[str, Any],
) -> set[str]:
    concepts = set(plan_audit.get("resolved_concepts") or [])
    normalized = _normalize(question)

    for metric in semantic_plan.get("metrics") or []:
        name = str(metric.get("name") or "")
        expression_type = str(metric.get("expression_type") or "")
        if name in {"total_mortes", "taxa_mortalidade"} or metric.get("numerator_condition"):
            concepts.add("death_outcome")
        if name == "taxa_mortalidade" or expression_type == "rate":
            concepts.add("mortality_rate")
        if (
            name in {"receita_total", "custo_medio", "custo_por_dia", "valor_total_uti"}
            or name.startswith("custo_")
        ):
            concepts.add("cost")
        if name == "media_dias_permanencia":
            concepts.add("length_of_stay")
        if name in {"pib_per_capita", "leitos_sus_1000", "medicos_1000"}:
            concepts.add("socioeconomic_metric")

    for item in semantic_plan.get("dimensions") or []:
        _add_dimension_concept(concepts, str(item.get("name") or ""))
    for item in semantic_plan.get("answer_shape", {}).get("required_dimensions") or []:
        _add_dimension_concept(concepts, str(item))

    for filter_ in semantic_plan.get("filters") or []:
        field = str(filter_.get("field") or "")
        values = [str(value) for value in filter_.get("values") or []]
        operator = str(filter_.get("operator") or "")
        _add_filter_concepts(concepts, field, values, operator)

    if intent_plan.get("primary_task") == "out_of_scope":
        _add_out_of_scope_concepts(concepts, normalized)
    if semantic_plan.get("intent") == "association":
        concepts.add("observational_caveat")
    if "inverno" in normalized or "sazon" in normalized:
        concepts.add("seasonality")

    constraints = set(semantic_plan.get("constraints") or [])
    if "socioeconomico_column_metric_required" in constraints:
        concepts.add("socioeconomic_metric")
    if "diagnosis_concept_resolution_required" in constraints:
        concepts.add("diagnosis_lookup")

    if re.search(r"\b((?:19|20)\d{2})\b", normalized):
        concepts.add("year")
    if "faixa etaria" in normalized or "faixa etária" in normalized:
        concepts.add("age_band")
    if re.search(r"\bidade\b", normalized):
        concepts.add("age")
    if "idoso" in normalized or "60 anos ou mais" in normalized:
        concepts.add("elderly_policy")
    if "respirat" in normalized or "cid j" in normalized:
        concepts.add("respiratory_cid")
    if any(token in normalized for token in ["pneumonia", "asma", "cancer", "neoplasia", "cid"]):
        concepts.add("diagnosis_lookup")
    if any(
        token in normalized
        for token in [
            "sem municipio",
            "nao tem municipio",
            "não tem municipio",
            "municipio de residencia mapeado",
            "codigos de municipio",
            "códigos de município",
            "lookup",
            "codigo de municipio",
        ]
    ):
        concepts.add("missing_lookup")
    if "mortalidade infantil" in normalized:
        concepts.add("socioeconomic_metric")
    if any(token in normalized for token in ["custo", "valor total", "receita"]):
        concepts.add("cost")
    if "uti" in normalized:
        concepts.add("uti")
    if "municipio" in normalized or "município" in normalized:
        concepts.add("municipality")
    if "hospital" in normalized or "hospitais" in normalized:
        concepts.add("hospital")
    if "permanencia" in normalized or "permanência" in normalized:
        concepts.add("length_of_stay")
    if "especialidade" in normalized:
        concepts.add("specialty")
    if "pelo menos" in normalized or "no minimo" in normalized or "no mínimo" in normalized:
        concepts.add("minimum_group_count")
    if "raca" in normalized or "raça" in normalized or "cor" in normalized:
        concepts.add("race_color")
    if "cobertura" in normalized:
        concepts.add("coverage")
    if "diag_princ" in normalized or "diagnostico principal ausente" in normalized:
        concepts.add("missing_diagnosis")
    if "causa de morte" in normalized or "causas de morte" in normalized:
        concepts.add("death_cause_field")
    if "menores de" in normalized or "menos de" in normalized:
        concepts.add("custom_child_age_policy")
    if re.search(
        r"\b(?:entre\s+)?((?:19|20)\d{2})\s*(?:-|a|ate|até|e)\s*((?:19|20)\d{2})\b",
        normalized,
    ):
        concepts.add("year_range")
    if "sexo" in normalized or "homens" in normalized or "mulheres" in normalized:
        concepts.add("sex")
    if "obstetric" in normalized or "obstetrícia" in normalized or "obstetricia" in normalized:
        concepts.add("obstetric")

    return concepts


def _add_dimension_concept(concepts: set[str], name: str) -> None:
    mapping = {
        "ano": "year",
        "mes": "month",
        "idade": "age",
        "faixa_etaria": "age_band",
        "sexo": "sex",
        "municipio": "municipality",
        "municipio_hospital": "municipality",
        "hospital": "hospital",
        "estado": "state",
        "estado_hospital": "state",
        "raca_cor": "race_color",
        "procedimento": "procedure",
        "especialidade": "specialty",
        "cid_capitulo": "cid_chapter",
        "diagnostico": "diagnosis_lookup",
    }
    concept = mapping.get(name)
    if concept:
        concepts.add(concept)


def _add_filter_concepts(
    concepts: set[str],
    field: str,
    values: list[str],
    operator: str,
) -> None:
    if field == "idade":
        numeric_values = [_parse_int(value) for value in values]
        if operator in {"<", "<="} and numeric_values:
            value = numeric_values[0]
            concepts.add("child_age_policy" if value == 18 else "custom_child_age_policy")
        if operator in {">", ">="} and numeric_values and numeric_values[0] >= 60:
            concepts.add("elderly_policy")
    if field == "recent_years_available":
        concepts.add("last_n_available_years")
    if field == "minimum_group_count":
        concepts.add("minimum_group_count")
    if field == "uti":
        concepts.add("uti")
    if field == "ano" or field.startswith("period_"):
        concepts.add("year")
    if field == "desfecho":
        concepts.add("death_outcome")
    if field.startswith("diagnostico_principal"):
        concepts.add("diagnosis_lookup")
        if any(value.upper() == "J%" for value in values):
            concepts.add("respiratory_cid")
    if field in {"municipio", "municipio_residencia", "municipios_residencia_sem_lookup"}:
        concepts.add("municipality")
    if field in {"estado", "estado_residencia"}:
        concepts.add("state")
    if "sem_lookup" in field or "sem_" in field:
        concepts.add("missing_lookup")
    if "diag" in field and ("sem" in field or "ausente" in field):
        concepts.add("missing_diagnosis")


def _add_out_of_scope_concepts(concepts: set[str], normalized: str) -> None:
    token_map = {
        "unsupported_medication": ["antibiotico", "antibiótico", "remedio", "remédio", "medicamento"],
        "unsupported_vaccine": ["vacina", "vacinacao", "vacinação"],
        "unsupported_labs": ["hemograma", "laboratorio", "laboratório"],
        "unsupported_followup": ["sobrevida", "apos alta", "após alta", "reinternacao", "reinternação"],
        "unsupported_causality": ["causou", "causal"],
        "unsupported_neighborhood": ["bairro"],
        "unsupported_income": ["renda individual"],
        "unsupported_vitals": ["saturacao", "saturação", "sinais vitais"],
    }
    for concept, tokens in token_map.items():
        if any(token in normalized for token in tokens):
            concepts.add(concept)


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()
