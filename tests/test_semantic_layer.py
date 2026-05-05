from src.semantic.planner import build_semantic_plan
from src.semantic.validators import validate_sql_against_semantic_plan
from src.application.config.simple_config import OrchestratorConfig
from src.application.prompts.table_selection.catalog import resolve_table_selection_strategy


def test_semantic_plan_detects_generic_top_n_per_group():
    plan = build_semantic_plan(
        "Quais são os 5 hospitais com maior custo médio de UTI por estado?"
    )

    assert plan.intent == "ranking"
    assert plan.answer_shape.top_n == 5
    assert plan.answer_shape.top_n_scope == "per_group"
    assert "top_n_per_group_requires_window_partition" in plan.constraints
    assert "estado" in plan.answer_shape.required_dimensions
    assert "hospital" in plan.answer_shape.required_dimensions


def test_semantic_plan_detects_para_cada_as_top_n_per_group():
    plan = build_semantic_plan(
        "Quais são os 5 procedimentos mais comuns para cada sexo?"
    )

    assert plan.intent == "ranking"
    assert plan.answer_shape.top_n_scope == "per_group"
    assert "top_n_per_group_requires_window_partition" in plan.constraints
    assert "sexo" in plan.answer_shape.required_dimensions


def test_semantic_plan_detects_rate_without_outcome_filter():
    plan = build_semantic_plan("Qual a taxa de mortalidade por município?")

    assert plan.intent == "rate"
    assert any(metric.name == "taxa_mortalidade" for metric in plan.metrics)
    assert "rate_denominator_must_preserve_full_scope" in plan.constraints
    assert not any(f.field == "desfecho" for f in plan.filters)
    assert "faixa_etaria" not in plan.answer_shape.required_dimensions


def test_semantic_plan_does_not_confuse_mortalidade_with_idade_dimension():
    plan = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado?")

    assert "estado" in plan.answer_shape.required_dimensions
    assert "ano" in plan.answer_shape.required_dimensions
    assert "faixa_etaria" not in plan.answer_shape.required_dimensions


def test_semantic_validator_rejects_global_limit_for_per_group_top_n():
    plan = build_semantic_plan(
        "Quais são os 3 hospitais com maior custo médio de UTI por estado?"
    )
    sql = """
        SELECT mu.estado, i."CNES", AVG(i."VAL_UTI") AS custo
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
        WHERE i."VAL_UTI" > 0
        GROUP BY mu.estado, i."CNES"
        ORDER BY custo DESC
        LIMIT 3
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "ROW_NUMBER" in (message or "")


def test_semantic_validator_accepts_per_group_window_pattern():
    plan = build_semantic_plan(
        "Quais são os 3 hospitais com maior custo médio de UTI por estado?"
    )
    sql = """
        SELECT estado, "CNES", custo
        FROM (
            SELECT mu.estado, i."CNES", AVG(i."VAL_UTI") AS custo,
                   ROW_NUMBER() OVER (PARTITION BY mu.estado ORDER BY AVG(i."VAL_UTI") DESC) AS rn
            FROM internacoes i
            JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
            WHERE i."VAL_UTI" > 0
            GROUP BY mu.estado, i."CNES"
        ) sub
        WHERE rn <= 3
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert passed, message


def test_semantic_validator_rejects_mortality_rate_with_filtered_denominator():
    plan = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado?")
    sql = """
        SELECT mu.estado, EXTRACT(YEAR FROM i."DT_INTER") AS ano,
               COUNT(*) AS total,
               ROUND(COUNT(*) * 100.0 / COUNT(*), 2) AS taxa_mortalidade
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
        WHERE i."MORTE" = true
        GROUP BY mu.estado, ano
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "denominator" in (message or "")


def test_semantic_validator_requires_unknown_bucket_policy():
    plan = build_semantic_plan(
        "Qual a distribuição por categoria incluindo os casos sem informação?"
    )
    sql = """
        SELECT c."DESCRICAO", COUNT(*)
        FROM internacoes i
        JOIN categoria c ON i."CAT" = c."CAT"
        GROUP BY c."DESCRICAO"
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "COALESCE" in (message or "")


def test_semantic_validator_accepts_aggregate_zero_absence_condition():
    plan = build_semantic_plan(
        "Quais hospitais com mais de 1000 internações nunca tiveram internação em UTI?"
    )
    sql = """
        SELECT "CNES", COUNT(*) AS total
        FROM internacoes
        GROUP BY "CNES"
        HAVING COUNT(*) > 1000
           AND SUM(CASE WHEN "VAL_UTI" > 0 THEN 1 ELSE 0 END) = 0
        ORDER BY total DESC
        LIMIT 10
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert passed, message


def test_orchestrator_config_defaults_do_not_mask_table_selection_preset_without_langchain():
    cfg = OrchestratorConfig()
    strategy = resolve_table_selection_strategy(
        preset_name=cfg.table_selection_preset,
        mode=cfg.table_selection_mode,
        description_variant=cfg.table_selection_description_variant,
        prompt_variant=cfg.table_selection_prompt_variant,
    )

    assert strategy["preset_name"] == "llm_best"
    assert strategy["mode"] == "llm_only"
    assert strategy["description_variant"] == "role_guardrails"
    assert strategy["prompt_variant"] == "decision_checklist"
