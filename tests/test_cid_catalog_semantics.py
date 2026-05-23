from src.agent.cid_catalog_sql import build_deterministic_cid_catalog_sql
from src.agent.sql_generation import (
    _build_deterministic_grouped_sql,
    _build_deterministic_scalar_sql,
)
from src.semantic.plan_reconciler import reconcile_semantic_plans
from src.semantic.planner import build_semantic_plan
from src.semantic.validators import validate_sql_against_semantic_plan


def test_cid_group_count_uses_group_catalog_column():
    plan = build_semantic_plan("Quantos grupos CID distintos existem?")

    sql = _build_deterministic_scalar_sql(plan)

    assert plan.base_grain == "cid_catalog"
    assert sql == 'SELECT COUNT(DISTINCT "DS_GRUPO") AS total_grupos_cid FROM cid;'


def test_cid_catalog_sql_template_is_isolated_from_main_sql_generator():
    plan = build_semantic_plan("Quais codigos CID relacionados a pneumonia existem na base?")

    sql = build_deterministic_cid_catalog_sql(plan)

    assert sql is not None
    assert 'FROM cid' in sql
    assert "\"CID\" LIKE 'J12%'" in sql
    assert "\"CID\" LIKE 'J18%'" in sql


def test_cid_restriction_catalog_groups_by_restrsexo():
    plan = build_semantic_plan("Quais restricoes de sexo aparecem no catalogo CID?")

    sql = _build_deterministic_grouped_sql(plan)

    assert plan.base_grain == "cid_catalog"
    assert sql is not None
    assert 'SELECT "RESTRSEXO" AS restricao_sexo' in sql
    assert 'GROUP BY "RESTRSEXO"' in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_cid_catalog_lookup_returns_codes_and_hierarchy_for_named_disease():
    plan = build_semantic_plan("Quais codigos CID relacionados a pneumonia existem na base?")

    sql = _build_deterministic_grouped_sql(plan)

    assert plan.base_grain == "cid_catalog"
    assert sql is not None
    assert '"CID" AS cid' in sql
    assert '"DESCRICAO" AS descricao' in sql
    assert '"DS_CATEGORIA" AS categoria_cid' in sql
    assert '"DS_GRUPO" AS grupo_cid' in sql
    assert "\"CID\" LIKE 'J12%'" in sql
    assert "\"CID\" LIKE 'J18%'" in sql


def test_cid_catalog_prefix_lookup_applies_cid_like_filter():
    plan = build_semantic_plan("Liste CIDs cujo codigo comeca com J18.")

    sql = _build_deterministic_grouped_sql(plan)

    assert plan.base_grain == "cid_catalog"
    assert sql is not None
    assert "\"CID\" LIKE 'J18%'" in sql


def test_cid_duplicate_description_lookup_groups_and_having():
    plan = build_semantic_plan("Existem descricoes CID repetidas?")

    sql = _build_deterministic_grouped_sql(plan)

    assert plan.base_grain == "cid_catalog"
    assert "cid_duplicate_description_lookup_required" in plan.constraints
    assert sql is not None
    assert 'GROUP BY "DESCRICAO"' in sql
    assert "HAVING COUNT(*) > 1" in sql


def test_cid_catalog_obstetric_lookup_does_not_require_internacao_filter():
    plan = build_semantic_plan("Quais capitulos CID mencionam gravidez, parto ou puerperio?")

    sql = _build_deterministic_grouped_sql(plan)

    assert plan.base_grain == "cid_catalog"
    assert not any(filter_.field == "obstetrico" for filter_ in plan.filters)
    assert sql is not None
    assert "\"CID\" LIKE 'O%'" in sql
    assert 'i."ESPEC"' not in sql


def test_cid_frequent_categories_for_children_use_internacoes_and_age_filter():
    plan = build_semantic_plan("Quais categorias CID foram mais frequentes em criancas?")

    sql = _build_deterministic_grouped_sql(plan)

    assert plan.base_grain == "internacao"
    assert plan.answer_shape.row_grain == "top_n_global"
    assert sql is not None
    assert 'JOIN cid c ON i."DIAG_PRINC" = c."CID"' in sql
    assert 'i."IDADE" < 18' in sql
    assert "LIMIT 10" in sql


def test_disease_family_count_uses_cid_hierarchy_context_with_join():
    plan = build_semantic_plan(
        "Quantas internacoes tiveram diagnostico principal relacionado a doencas respiratorias?"
    )

    sql = _build_deterministic_scalar_sql(plan)

    assert plan.base_grain == "internacao"
    assert sql is not None
    assert 'JOIN cid c ON i."DIAG_PRINC" = c."CID"' in sql
    assert 'c."DS_CAPITULO"' in sql
    assert 'c."DS_GRUPO"' in sql


def test_internacao_category_question_uses_cid_category_lookup_dimension():
    plan = build_semantic_plan(
        "Quais categorias CID foram mais frequentes entre internacoes femininas?"
    )

    sql = _build_deterministic_grouped_sql(plan)

    assert plan.base_grain == "internacao"
    assert "cid_categoria" in plan.answer_shape.required_dimensions
    assert sql is not None
    assert 'JOIN cid c ON i."DIAG_PRINC" = c."CID"' in sql
    assert 'c."DS_CATEGORIA" AS categoria_cid' in sql
    assert 'i."SEXO" IN (3)' in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_cid_description_long_stay_question_preserves_join_and_grouping():
    plan = build_semantic_plan(
        "Quais descricoes CID tiveram mais internacoes com longa permanencia?"
    )

    sql = _build_deterministic_grouped_sql(plan)

    assert plan.base_grain == "internacao"
    assert plan.answer_shape.row_grain == "top_n_global"
    assert "cid_descricao" in plan.answer_shape.required_dimensions
    assert any(filter_.field == "longa_permanencia" for filter_ in plan.filters)
    assert sql is not None
    assert 'JOIN cid c ON i."DIAG_PRINC" = c."CID"' in sql
    assert 'c."DESCRICAO" AS descricao' in sql
    assert 'i."DIAS_PERM" >= 30' in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_reconciler_preserves_cid_hierarchy_dimensions():
    heuristic = build_semantic_plan(
        "Quais categorias CID foram mais frequentes entre internacoes femininas?"
    )
    candidate = heuristic.model_copy(
        update={
            "dimensions": [],
            "answer_shape": heuristic.answer_shape.model_copy(update={"required_dimensions": []}),
        }
    )

    reconciled = reconcile_semantic_plans(heuristic, candidate).reconciled_plan

    assert "cid_categoria" in reconciled.answer_shape.required_dimensions
    assert [dimension.name for dimension in reconciled.dimensions] == ["cid_categoria"]


def test_post_execution_contract_accepts_cid_catalog_dimensions():
    from src.agent.execution import _validate_post_execution_contract

    catalog_plan = build_semantic_plan(
        "Quais codigos CID relacionados a pneumonia existem na base?"
    )
    catalog_sql = (
        'SELECT "CID" AS cid, "DESCRICAO" AS descricao,'
        ' "DS_CATEGORIA" AS categoria_cid, "DS_GRUPO" AS grupo_cid,'
        ' "DS_CAPITULO" AS capitulo_cid FROM cid'
    )

    passed, message = _validate_post_execution_contract(
        catalog_plan,
        catalog_sql,
        results=[{"cid": "J18", "descricao": "Pneumonia p/microorg NE"}],
        row_count=1,
    )

    assert passed is True, message

    grouped_plan = build_semantic_plan(
        "Quais categorias CID foram mais frequentes entre internacoes femininas?"
    )
    grouped_sql = (
        'SELECT c."DS_CATEGORIA" AS categoria_cid, COUNT(*) AS total_internacoes '
        'FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" '
        'GROUP BY c."DS_CATEGORIA"'
    )

    passed, message = _validate_post_execution_contract(
        grouped_plan,
        grouped_sql,
        results=[{"categoria_cid": "Pneumonia", "total_internacoes": 10}],
        row_count=1,
    )

    assert passed is True, message
