from src.agent.analytic_sql import build_analytic_sql_package
from src.agent.execution import repair_sql_node
from src.agent.response import _format_analytic_response_from_package
from src.agent.state_helpers import create_initial_messages_state
from src.semantic.plan_schema import AnswerShape, SemanticFilter, SemanticMetric, SemanticPlan
from src.semantic.planner import build_semantic_plan
from src.semantic.validators import validate_sql_against_semantic_plan


QUERY = "me mostre a evolucao de mortes por cancer nos ultimos 3 anos"


class _FakeLLMManager:
    def invoke_chat(self, _messages):
        raise AssertionError("deterministic repair should not fall back to LLM")


def _filter_values(plan: SemanticPlan, field: str) -> list[str]:
    values: list[str] = []
    for semantic_filter in plan.filters:
        if semantic_filter.field == field:
            values.extend(str(value) for value in semantic_filter.values)
    return values


def _cancer_death_trend_plan() -> SemanticPlan:
    return SemanticPlan(
        intent="trend",
        base_grain="internacao",
        metrics=[
            SemanticMetric(
                name="total_mortes",
                expression_type="count",
                required_filters=["MORTE = true"],
            )
        ],
        filters=[
            SemanticFilter(
                field="recent_years_available",
                values=["3"],
                operator="last_n_available",
            ),
            SemanticFilter(field="diagnostico_principal_descricao", values=["cancer"], operator="ILIKE"),
            SemanticFilter(field="desfecho", values=["MORTE = true"], operator="semantic"),
        ],
        answer_shape=AnswerShape(
            row_grain="time_series",
            required_dimensions=["ano"],
            requires_group_by=True,
            answer_kind="time_series",
            expected_row_count="one_per_group",
            output_dimensions=["ano"],
        ),
        constraints=[
            "relative_recent_years_use_available_data_max_year",
            "diagnosis_description_lookup_required",
            "death_cause_description_requires_diag_princ_with_morte",
        ],
    )


def test_cancer_death_trend_separates_clinical_term_from_recent_year_window():
    plan = build_semantic_plan(QUERY)

    assert _filter_values(plan, "diagnostico_principal_prefix") == ["C%"]
    assert _filter_values(plan, "diagnostico_principal_descricao") == []
    assert any("cancer" in value.lower() for value in _filter_values(plan, "diagnostico_conceito_label"))
    assert _filter_values(plan, "recent_years_available") == ["3"]
    assert _filter_values(plan, "desfecho") == ["MORTE = true"]
    assert not any(
        "ultimos 3 anos" in value
        for value in _filter_values(plan, "diagnostico_principal_descricao")
    )


def test_unknown_death_trend_keeps_only_disease_text_in_description_lookup():
    plan = build_semantic_plan(
        "me mostre a evolucao de mortes por doenca renal nos ultimos 3 anos"
    )

    assert _filter_values(plan, "diagnostico_principal_descricao") == ["doenca renal"]
    assert _filter_values(plan, "recent_years_available") == ["3"]


def test_explicit_years_stay_separate_from_resolved_respiratory_concept():
    plan = build_semantic_plan(
        "me mostre um grafico mostrando o numero total de mortes por causas respiratorias "
        "em 2021, 2022 e 2023"
    )

    assert _filter_values(plan, "diagnostico_principal_prefix") == ["J%"]
    assert _filter_values(plan, "diagnostico_principal_descricao") == []
    assert _filter_values(plan, "ano") == ["2021", "2022", "2023"]


def test_temporal_condition_trend_sql_applies_death_and_recent_year_scope():
    sql = build_analytic_sql_package(build_semantic_plan(QUERY))

    assert sql is not None
    sql_lower = sql.lower()
    assert 'i."morte" = true' in sql_lower
    assert "like 'c%'" in sql_lower
    assert "cancer nos ultimos 3 anos" not in sql_lower
    assert "current_date" not in sql_lower
    assert "now()" not in sql_lower
    assert "max(extract(year" in sql_lower
    assert " - 2" in sql_lower


def test_validator_accepts_normalized_cancer_repair_and_rejects_missing_death_filter():
    plan = _cancer_death_trend_plan()
    valid_sql = """
        WITH latest_year AS (
            SELECT MAX(EXTRACT(YEAR FROM i."DT_INTER")) AS max_year
            FROM internacoes i
        )
        SELECT EXTRACT(YEAR FROM i."DT_INTER") AS ano, COUNT(*) AS total_mortes
        FROM internacoes i
        JOIN cid c ON i."DIAG_PRINC" = c."CID"
        CROSS JOIN latest_year ly
        WHERE i."MORTE" = true
          AND c."DESCRICAO" ILIKE '%cancer%'
          AND EXTRACT(YEAR FROM i."DT_INTER") BETWEEN ly.max_year - 2 AND ly.max_year
        GROUP BY ano
        ORDER BY ano
    """
    missing_death_sql = valid_sql.replace('i."MORTE" = true\n          AND ', "")

    assert validate_sql_against_semantic_plan(plan, valid_sql) == (True, None)
    assert validate_sql_against_semantic_plan(plan, missing_death_sql) == (
        False,
        "SEMANTIC PLAN ERROR: SQL does not apply the requested death filter.",
    )


def test_repair_preserves_normalized_diagnosis_and_time_series_shape(monkeypatch):
    monkeypatch.setattr("src.agent.execution.get_llm_manager", lambda: _FakeLLMManager())
    plan = _cancer_death_trend_plan()
    state = create_initial_messages_state(QUERY, session_id="repair-test")
    state["generated_sql"] = "SELECT broken_sql"
    state["semantic_plan"] = plan.model_dump(exclude_none=True)
    state["current_error"] = (
        "SEMANTIC PLAN ERROR: diagnosis description lookup is missing expanded term(s): "
        "cancer nos ultimos 3 anos."
    )
    state["ablation_flags"] = {"enable_analytic_response_templates": True}

    updated = repair_sql_node(state)
    repaired_sql = updated["generated_sql"].lower()

    assert updated["current_error"] is None
    assert "cancer nos ultimos 3 anos" not in repaired_sql
    assert 'i."morte" = true' in repaired_sql
    assert "time_series" in repaired_sql
    assert "max(extract(year" in repaired_sql


def test_temporal_death_trend_response_labels_metric_as_deaths():
    response = _format_analytic_response_from_package(
        QUERY,
        {
            "analysis_type": "temporal_condition_trend",
            "resolved_concept": "CID C00-C97 - Neoplasias malignas (cancer)",
            "total_internacoes": 200744,
            "denominador": "internacoes por ano no mesmo escopo",
            "time_series": "2021:65640:11566528:567.5 | 2022:68572:12363889:554.62 | 2023:66532:12450724:534.36",
            "first_period": 2021,
            "first_total": 65640,
            "last_period": 2023,
            "last_total": 66532,
            "delta_absolute": 892,
            "delta_percent": 1.36,
            "peak_period": 2022,
            "peak_total": 68572,
        },
    )

    assert "| Ano | Mortes | Denominador | Taxa por 100 mil |" in response
    assert "200.744 mortes" in response
    assert "892 mortes" in response
    assert "68.572 mortes" in response
