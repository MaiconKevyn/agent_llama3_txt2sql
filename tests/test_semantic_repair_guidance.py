from src.agent.semantic_repair import (
    build_semantic_repair_context,
    extract_violated_contract,
    load_repair_guidance,
)
from src.semantic.error_taxonomy import SemanticErrorCategory
from src.semantic.planner import build_semantic_plan


def test_repair_guidance_loads_all_core_categories():
    catalog = load_repair_guidance()

    assert SemanticErrorCategory.RATE_DENOMINATOR in catalog.guidance
    assert SemanticErrorCategory.TOP_N_SCOPE in catalog.guidance
    assert SemanticErrorCategory.ABSENCE_CONDITION in catalog.guidance
    assert SemanticErrorCategory.JOIN_PATH in catalog.guidance
    assert catalog.guidance[SemanticErrorCategory.RATE_DENOMINATOR].preserve_scope_filters


def test_rate_denominator_guidance_includes_conditional_aggregation_instruction():
    plan = build_semantic_plan("Qual a taxa de mortalidade por estado?")
    context = build_semantic_repair_context(
        "SEMANTIC PLAN ERROR: mortality-rate denominator is filtered by MORTE in WHERE",
        plan,
    )

    assert context.error.category == SemanticErrorCategory.RATE_DENOMINATOR
    assert "SUM(CASE WHEN" in context.prompt_block
    assert "metrics.denominator_scope" in context.violated_contract


def test_top_n_guidance_mentions_window_partition_and_preserves_scope_filters():
    plan = build_semantic_plan("Quais são os 3 hospitais com maior custo médio de UTI por estado?")
    context = build_semantic_repair_context(
        "SEMANTIC PLAN ERROR: top-N per group requires a window ranking function",
        plan,
    )

    assert context.error.category == SemanticErrorCategory.TOP_N_SCOPE
    assert "PARTITION BY" in context.prompt_block
    assert "Preserve todos os filtros de escopo" in context.prompt_block
    assert context.violated_contract["answer_shape.top_n"] == 3


def test_absence_guidance_rejects_negative_filter_pattern():
    context = build_semantic_repair_context(
        "SEMANTIC PLAN ERROR: absence/non-occurrence is missing NOT EXISTS",
        build_semantic_plan("Quais hospitais nunca registraram cobrança de UTI?"),
    )

    assert context.error.category == SemanticErrorCategory.ABSENCE_CONDITION
    assert "NOT EXISTS" in context.prompt_block
    assert "WHERE condicao = 0" in context.prompt_block


def test_join_path_guidance_includes_catalog_path_instruction():
    context = build_semantic_repair_context(
        "AST CONTRACT ERROR: SQL join path for estado does not include catalog edge internacoes.MUNIC_RES -> municipios.codigo_6d",
        build_semantic_plan("Quais hospitais nunca registraram cobrança de UTI por estado?"),
    )

    assert context.error.category == SemanticErrorCategory.JOIN_PATH
    assert "catalogo semantico" in context.prompt_block
    assert "answer_shape.required_dimensions" in context.violated_contract


def test_extract_violated_contract_handles_nested_lists_without_ground_truth():
    plan = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado?")
    contract = extract_violated_contract(
        plan,
        ["metrics.denominator_scope", "answer_shape.required_dimensions"],
    )

    assert contract["metrics.denominator_scope"] == ["all_rows_matching_non_outcome_filters"]
    assert contract["answer_shape.required_dimensions"] == ["estado", "ano"]
