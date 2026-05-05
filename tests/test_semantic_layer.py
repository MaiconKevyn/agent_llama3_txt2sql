from src.agent.plan_gate import plan_gate_node
from src.agent.state_helpers import create_initial_messages_state
from src.application.config.simple_config import OrchestratorConfig
from src.application.prompts.table_selection.catalog import resolve_table_selection_strategy
from src.semantic.catalog import (
    catalog_summary,
    load_semantic_catalog,
    render_catalog_context_for_plan,
    render_catalog_prompt_context,
)
from src.semantic.data_profile import (
    ColumnProfileSpec,
    build_column_profile_queries,
    build_default_profile_query_sets,
)
from src.semantic.equivalence import same_semantic_pattern, semantic_sql_signature
from src.semantic.error_taxonomy import (
    SemanticErrorCategory,
    build_semantic_error_record,
    classify_semantic_error,
)
from src.semantic.planner import build_semantic_plan
from src.semantic.validators import validate_sql_against_semantic_plan


def test_semantic_plan_detects_generic_top_n_per_group():
    plan = build_semantic_plan("Quais são os 5 hospitais com maior custo médio de UTI por estado?")

    assert plan.intent == "ranking"
    assert plan.answer_shape.top_n == 5
    assert plan.answer_shape.top_n_scope == "per_group"
    assert "top_n_per_group_requires_window_partition" in plan.constraints
    assert "estado" in plan.answer_shape.required_dimensions
    assert "hospital" in plan.answer_shape.required_dimensions


def test_plan_gate_persists_semantic_telemetry_metadata():
    state = create_initial_messages_state(
        user_query="Quais são os 3 hospitais com maior custo médio de UTI por estado?",
        session_id="semantic-telemetry-test",
    )

    new_state = plan_gate_node(state)
    metadata = new_state["response_metadata"]

    assert "semantic_plan" in metadata
    assert "semantic_constraints" in metadata
    assert "top_n_per_group_requires_window_partition" in metadata["semantic_constraints"]


def test_semantic_catalog_loads_versioned_metrics_dimensions_and_rules():
    catalog = load_semantic_catalog()
    summary = catalog_summary()

    assert catalog.version >= 1
    assert "taxa_mortalidade" in catalog.metrics
    assert catalog.metrics["taxa_mortalidade"].denominator == "COUNT(*)"
    assert "hospital" in catalog.dimensions
    assert catalog.dimensions["hospital"].output_policy == "preserve_cnes_identifier"
    assert "top_n_per_group" in catalog.macros
    assert summary["rule_count"] >= 4


def test_semantic_catalog_prompt_context_is_selective_and_reusable():
    context = render_catalog_prompt_context(
        metric_names=["taxa_mortalidade"],
        dimension_names=["hospital"],
        rule_names=["rate_denominator_must_preserve_full_scope"],
    )

    assert "taxa_mortalidade" in context
    assert "denominator=COUNT(*)" in context
    assert "source=internacoes.CNES" in context
    assert "rate_denominator_must_preserve_full_scope" in context
    assert "total_obitos" not in context


def test_semantic_catalog_context_can_be_rendered_from_plan():
    plan = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado?")
    context = render_catalog_context_for_plan(plan)

    assert "taxa_mortalidade" in context
    assert "estado_residencia" in context
    assert "ano_internacao" in context
    assert "rate_denominator_must_preserve_full_scope" in context


def test_data_profile_query_builder_creates_summary_and_top_values_sql():
    query_set = build_column_profile_queries(
        ColumnProfileSpec(table="internacoes", column="MORTE", kind="categorical", top_k=5)
    )

    assert 'COUNT(DISTINCT "MORTE") AS distinct_count' in query_set.summary_sql
    assert 'SUM(CASE WHEN "MORTE" IS NULL THEN 1 ELSE 0 END)' in query_set.summary_sql
    assert query_set.top_values_sql is not None
    assert 'GROUP BY "MORTE"' in query_set.top_values_sql
    assert "LIMIT 5" in query_set.top_values_sql


def test_semantic_error_taxonomy_classifies_validator_messages():
    assert (
        classify_semantic_error("SQL has no PARTITION BY for top-N per group")
        == SemanticErrorCategory.TOP_N_SCOPE
    )
    assert (
        classify_semantic_error(
            "Mortality-rate SQL filters MORTE=true in WHERE, damaging denominator"
        )
        == SemanticErrorCategory.RATE_DENOMINATOR
    )
    record = build_semantic_error_record("SQL does not use NOT EXISTS for absence")
    assert record.category == SemanticErrorCategory.ABSENCE_CONDITION
    assert record.severity == "error"


def test_semantic_sql_signature_captures_structural_features():
    sql = """
        SELECT mu.estado, COUNT(*),
               SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
        WHERE mu.estado IN ('SP', 'RJ')
        GROUP BY mu.estado
    """

    signature = semantic_sql_signature(sql)

    assert signature.tables == {"internacoes", "municipios"}
    assert signature.has_conditional_mortality_numerator
    assert "estado" in signature.group_by


def test_semantic_sql_equivalence_ignores_alias_and_formatting_differences():
    left = """
        SELECT mu.estado, COUNT(*)
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
        WHERE mu.estado IN ('SP', 'RJ')
        GROUP BY mu.estado
    """
    right = """
        SELECT m.estado, COUNT(*)
        FROM internacoes AS x
        JOIN municipios AS m ON x."MUNIC_RES" = m.codigo_6d
        WHERE m.estado IN ('SP', 'RJ')
        GROUP BY m.estado
    """

    assert same_semantic_pattern(left, right)


def test_data_profile_query_builder_adds_ranges_for_numeric_columns():
    query_set = build_column_profile_queries(
        ColumnProfileSpec(table="internacoes", column="VAL_UTI", kind="numeric")
    )

    assert 'MIN("VAL_UTI") AS min_value' in query_set.summary_sql
    assert 'MAX("VAL_UTI") AS max_value' in query_set.summary_sql
    assert query_set.top_values_sql is None


def test_default_profile_specs_cover_core_semantic_columns():
    query_sets = build_default_profile_query_sets()
    pairs = {(query_set.table, query_set.column) for query_set in query_sets}

    assert ("internacoes", "MORTE") in pairs
    assert ("internacoes", "VAL_UTI") in pairs
    assert ("internacoes", "DT_INTER") in pairs
    assert ("municipios", "estado") in pairs


def test_semantic_plan_detects_para_cada_as_top_n_per_group():
    plan = build_semantic_plan("Quais são os 5 procedimentos mais comuns para cada sexo?")

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
    plan = build_semantic_plan("Quais são os 3 hospitais com maior custo médio de UTI por estado?")
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
    plan = build_semantic_plan("Quais são os 3 hospitais com maior custo médio de UTI por estado?")
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


def test_semantic_validator_accepts_per_group_rank_alias_not_named_rn():
    plan = build_semantic_plan("Quais são os 3 hospitais com maior custo médio de UTI por estado?")
    sql = """
        SELECT estado, "CNES", custo
        FROM (
            SELECT mu.estado, i."CNES", AVG(i."VAL_UTI") AS custo,
                   RANK() OVER (PARTITION BY mu.estado ORDER BY AVG(i."VAL_UTI") DESC) AS ranking
            FROM internacoes i
            JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
            WHERE i."VAL_UTI" > 0
            GROUP BY mu.estado, i."CNES"
        ) ranked
        WHERE ranking <= 3
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


def test_semantic_validator_does_not_treat_conditional_numerator_as_filtered_denominator():
    plan = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado?")
    sql = """
        SELECT mu.estado, EXTRACT(YEAR FROM i."DT_INTER") AS ano,
               SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) AS mortes,
               COUNT(*) AS total,
               SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
        WHERE mu.estado IN ('SP', 'RJ')
        GROUP BY mu.estado, ano
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert passed, message


def test_semantic_validator_rejects_group_by_missing_required_dimension():
    plan = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado?")
    sql = """
        SELECT mu.estado, EXTRACT(YEAR FROM i."DT_INTER") AS ano,
               SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
        GROUP BY ano
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "estado" in (message or "")


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


def test_semantic_validator_accepts_case_unknown_bucket_policy():
    plan = build_semantic_plan(
        "Qual a distribuição por categoria incluindo os casos sem informação?"
    )
    sql = """
        SELECT
            CASE WHEN c."DESCRICAO" IS NULL THEN 'Sem informação' ELSE c."DESCRICAO" END AS categoria,
            COUNT(*)
        FROM internacoes i
        LEFT JOIN categoria c ON i."CAT" = c."CAT"
        GROUP BY categoria
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert passed, message


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
