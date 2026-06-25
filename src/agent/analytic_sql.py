"""Deterministic SQL packages for analytic response templates."""

from __future__ import annotations

import re

from ..semantic.plan_schema import SemanticPlan

_VALID_UF_VALUES = (
    "'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', "
    "'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', "
    "'SP', 'SE', 'TO'"
)


def build_analytic_sql_package(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    """Build the best deterministic analytic SQL package for a semantic plan."""
    return (
        build_age_diagnosis_association_sql(semantic_plan)
        or build_categorical_outcome_association_sql(semantic_plan)
        or build_geographic_condition_rate_sql(semantic_plan)
        or build_temporal_condition_trend_sql(semantic_plan)
    )


def build_age_diagnosis_association_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    """Build a one-row analytic package for age x diagnosis association questions."""
    plan = _coerce_semantic_plan(semantic_plan)
    if plan is None:
        return None
    if "age_diagnosis_association_required" not in plan.constraints:
        return None

    target_sql, resolved_concept_sql = _diagnosis_target_sql_from_plan(plan)
    if not target_sql:
        return None

    scope_conditions = _scope_conditions_from_plan(plan, "i")
    scope_where = f" AND {' AND '.join(scope_conditions)}" if scope_conditions else ""
    denominator_label = _denominator_label_from_plan(plan)

    return f"""
WITH diagnosticos_alvo("CID") AS (
    {target_sql}
), diagnosticos_resolvidos AS (
    SELECT d."CID", COALESCE(c."DESCRICAO", '') AS "DESCRICAO"
    FROM diagnosticos_alvo d
    LEFT JOIN cid c ON c."CID" = d."CID"
), coorte AS (
    SELECT i."IDADE", i."MORTE", i."NASC", i."DT_INTER"
    FROM internacoes i
    JOIN diagnosticos_alvo d ON i."DIAG_PRINC" = d."CID"
    WHERE i."IDADE" IS NOT NULL{scope_where}
), base_denominador AS (
    SELECT i."IDADE"
    FROM internacoes i
    WHERE i."IDADE" IS NOT NULL{scope_where}
), coorte_faixas AS (
    SELECT
        CASE
            WHEN "IDADE" < 40 THEN '00-39'
            WHEN "IDADE" BETWEEN 40 AND 49 THEN '40-49'
            WHEN "IDADE" BETWEEN 50 AND 59 THEN '50-59'
            WHEN "IDADE" BETWEEN 60 AND 69 THEN '60-69'
            WHEN "IDADE" BETWEEN 70 AND 79 THEN '70-79'
            ELSE '80+'
        END AS faixa_etaria,
        CASE
            WHEN "IDADE" < 40 THEN 1
            WHEN "IDADE" BETWEEN 40 AND 49 THEN 2
            WHEN "IDADE" BETWEEN 50 AND 59 THEN 3
            WHEN "IDADE" BETWEEN 60 AND 69 THEN 4
            WHEN "IDADE" BETWEEN 70 AND 79 THEN 5
            ELSE 6
        END AS ordem,
        "MORTE"
    FROM coorte
), denominador_faixas AS (
    SELECT
        CASE
            WHEN "IDADE" < 40 THEN '00-39'
            WHEN "IDADE" BETWEEN 40 AND 49 THEN '40-49'
            WHEN "IDADE" BETWEEN 50 AND 59 THEN '50-59'
            WHEN "IDADE" BETWEEN 60 AND 69 THEN '60-69'
            WHEN "IDADE" BETWEEN 70 AND 79 THEN '70-79'
            ELSE '80+'
        END AS faixa_etaria,
        CASE
            WHEN "IDADE" < 40 THEN 1
            WHEN "IDADE" BETWEEN 40 AND 49 THEN 2
            WHEN "IDADE" BETWEEN 50 AND 59 THEN 3
            WHEN "IDADE" BETWEEN 60 AND 69 THEN 4
            WHEN "IDADE" BETWEEN 70 AND 79 THEN 5
            ELSE 6
        END AS ordem,
        COUNT(*) AS total_denominador
    FROM base_denominador
    GROUP BY faixa_etaria, ordem
), faixas_etarias AS (
    SELECT
        d.faixa_etaria,
        d.ordem,
        COUNT(c.faixa_etaria) AS total_internacoes,
        d.total_denominador,
        ROUND(COUNT(c.faixa_etaria) * 100000.0 / NULLIF(d.total_denominador, 0), 2)
            AS taxa_por_100k_denominador,
        ROUND(COUNT(c.faixa_etaria) * 100.0 / NULLIF((SELECT COUNT(*) FROM coorte), 0), 2)
            AS percentual_casos
    FROM denominador_faixas d
    LEFT JOIN coorte_faixas c ON c.faixa_etaria = d.faixa_etaria
    GROUP BY d.faixa_etaria, d.ordem, d.total_denominador
), cortes_etarios AS (
    SELECT
        'maior_igual_50' AS corte,
        SUM(CASE WHEN "IDADE" >= 50 THEN 1 ELSE 0 END) AS casos,
        (SELECT COUNT(*) FROM base_denominador WHERE "IDADE" >= 50) AS denominador
    FROM coorte
    UNION ALL
    SELECT
        'menor_50' AS corte,
        SUM(CASE WHEN "IDADE" < 50 THEN 1 ELSE 0 END) AS casos,
        (SELECT COUNT(*) FROM base_denominador WHERE "IDADE" < 50) AS denominador
    FROM coorte
    UNION ALL
    SELECT
        'maior_igual_60' AS corte,
        SUM(CASE WHEN "IDADE" >= 60 THEN 1 ELSE 0 END) AS casos,
        (SELECT COUNT(*) FROM base_denominador WHERE "IDADE" >= 60) AS denominador
    FROM coorte
    UNION ALL
    SELECT
        'menor_60' AS corte,
        SUM(CASE WHEN "IDADE" < 60 THEN 1 ELSE 0 END) AS casos,
        (SELECT COUNT(*) FROM base_denominador WHERE "IDADE" < 60) AS denominador
    FROM coorte
), taxas_cortes AS (
    SELECT corte, casos * 1.0 / NULLIF(denominador, 0) AS taxa
    FROM cortes_etarios
), top_idades AS (
    SELECT "IDADE", COUNT(*) AS total_internacoes
    FROM coorte
    GROUP BY "IDADE"
    ORDER BY total_internacoes DESC, "IDADE" ASC
    LIMIT 3
), qualidade_idade AS (
    SELECT
        SUM(CASE WHEN "IDADE" = 0 THEN 1 ELSE 0 END) AS idade_zero_total,
        SUM(CASE
            WHEN "IDADE" = 0
             AND "NASC" IS NOT NULL
             AND "DT_INTER" IS NOT NULL
             AND date_diff('day', "NASC", "DT_INTER") >= 365
            THEN 1 ELSE 0 END
        ) AS idade_zero_inconsistente_nasc,
        SUM(CASE
            WHEN "IDADE" = 0
             AND "NASC" IS NOT NULL
             AND "DT_INTER" IS NOT NULL
             AND date_diff('day', "NASC", "DT_INTER") BETWEEN 0 AND 364
            THEN 1 ELSE 0 END
        ) AS idade_zero_compativel_menor_1_ano
    FROM coorte
)
SELECT
    'age_diagnosis_association' AS analysis_type,
    {resolved_concept_sql} AS resolved_concept,
    (SELECT COUNT(*) FROM coorte) AS total_internacoes,
    (SELECT SUM(CASE WHEN "MORTE" = true THEN 1 ELSE 0 END) FROM coorte) AS total_mortes,
    (SELECT ROUND(AVG("IDADE"), 2) FROM coorte) AS idade_media,
    (SELECT MEDIAN("IDADE") FROM coorte) AS idade_mediana,
    '{_sql_literal(denominator_label)}' AS denominador,
    (SELECT STRING_AGG(
        faixa_etaria || ':' || total_internacoes || ':' || total_denominador || ':' ||
        taxa_por_100k_denominador || ':' || percentual_casos,
        ' | ' ORDER BY ordem)
     FROM faixas_etarias) AS faixas_etarias,
    (SELECT STRING_AGG(
        CAST("IDADE" AS VARCHAR) || ':' || total_internacoes,
        ' | ' ORDER BY total_internacoes DESC, "IDADE" ASC)
     FROM top_idades) AS top_idades,
    (SELECT ROUND(
        (SELECT taxa FROM taxas_cortes WHERE corte = 'maior_igual_50') /
        NULLIF((SELECT taxa FROM taxas_cortes WHERE corte = 'menor_50'), 0), 2))
        AS rate_ratio_maior_igual_50_vs_menor_50,
    (SELECT ROUND(
        (SELECT taxa FROM taxas_cortes WHERE corte = 'maior_igual_60') /
        NULLIF((SELECT taxa FROM taxas_cortes WHERE corte = 'menor_60'), 0), 2))
        AS rate_ratio_maior_igual_60_vs_menor_60,
    (SELECT idade_zero_total FROM qualidade_idade) AS idade_zero_total,
    (SELECT idade_zero_inconsistente_nasc FROM qualidade_idade)
        AS idade_zero_inconsistente_nasc,
    (SELECT idade_zero_compativel_menor_1_ano FROM qualidade_idade)
        AS idade_zero_compativel_menor_1_ano,
    (SELECT
        CASE
            WHEN idade_zero_inconsistente_nasc > 0 THEN
                'data_quality: IDADE=0 contem ' ||
                CAST(idade_zero_inconsistente_nasc AS VARCHAR) ||
                ' registros com NASC/DT_INTER indicando 1 ano ou mais'
            ELSE NULL
        END
     FROM qualidade_idade) AS warnings FROM (SELECT 1) AS analytic_singleton;
""".strip()


def build_categorical_outcome_association_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    """Build a one-row package for category x mortality-rate association questions."""
    plan = _coerce_semantic_plan(semantic_plan)
    if plan is None or "categorical_outcome_association_required" not in plan.constraints:
        return None

    category = _categorical_factor_from_plan(plan)
    if category is None:
        return None
    (
        category_label,
        category_expr,
        category_order,
        valid_condition,
        denominator_label,
        category_join,
    ) = category
    dimension_alias = category_label
    scope_conditions = _scope_conditions_from_plan(plan, "i")
    coorte_conditions = [*scope_conditions]
    if valid_condition:
        coorte_conditions.append(valid_condition)
    where_clause = f"WHERE {' AND '.join(coorte_conditions)}" if coorte_conditions else ""
    invalid_condition = _categorical_invalid_condition(category_label)
    excluded_conditions = [*scope_conditions, invalid_condition]
    excluded_where_clause = f"WHERE {' AND '.join(excluded_conditions)}"
    target_sql, resolved_concept_sql = _diagnosis_target_sql_from_plan(plan)
    diagnosis_ctes = ""
    diagnosis_join = ""
    outcome_expr = "'mortalidade hospitalar (MORTE=true)'"
    if target_sql:
        diagnosis_ctes = f"""
diagnosticos_alvo("CID") AS (
    {target_sql}
), diagnosticos_resolvidos AS (
    SELECT d."CID", COALESCE(c."DESCRICAO", '') AS "DESCRICAO"
    FROM diagnosticos_alvo d
    LEFT JOIN cid c ON c."CID" = d."CID"
), """.lstrip()
        diagnosis_join = 'JOIN diagnosticos_alvo d ON i."DIAG_PRINC" = d."CID"'
        outcome_expr = (
            "'mortalidade hospitalar (MORTE=true) em ' || "
            f"COALESCE({resolved_concept_sql}, 'diagnostico informado')"
        )
        denominator_label = f"{denominator_label} no diagnostico resolvido"

    return f"""
WITH {diagnosis_ctes}coorte AS (
    SELECT
        {category_expr} AS grupo_label,
        {category_order} AS ordem,
        {category_order} AS {dimension_alias},
        i."MORTE"
    FROM internacoes i
    {category_join}
    {diagnosis_join}
    {where_clause}
), grupos AS (
    SELECT
        grupo_label AS grupo,
        ordem,
        COUNT(*) AS total_internacoes,
        SUM(CASE WHEN "MORTE" = true THEN 1 ELSE 0 END) AS total_mortes,
        ROUND(SUM(CASE WHEN "MORTE" = true THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2)
            AS taxa_mortalidade_percentual
    FROM coorte
    GROUP BY grupo_label, ordem, {dimension_alias}
), extremos AS (
    SELECT
        (SELECT grupo FROM grupos ORDER BY taxa_mortalidade_percentual DESC, total_internacoes DESC LIMIT 1)
            AS maior_grupo,
        (SELECT taxa_mortalidade_percentual FROM grupos ORDER BY taxa_mortalidade_percentual DESC, total_internacoes DESC LIMIT 1)
            AS maior_taxa,
        (SELECT grupo FROM grupos ORDER BY taxa_mortalidade_percentual ASC, total_internacoes DESC LIMIT 1)
            AS menor_grupo,
        (SELECT taxa_mortalidade_percentual FROM grupos ORDER BY taxa_mortalidade_percentual ASC, total_internacoes DESC LIMIT 1)
            AS menor_taxa
), excluidos AS (
    SELECT COUNT(*) AS total_excluidos
    FROM internacoes i
    {diagnosis_join}
    {excluded_where_clause}
)
SELECT
    'categorical_outcome_association' AS analysis_type,
    '{_sql_literal(category_label)}' AS factor_name,
    {outcome_expr} AS outcome,
    (SELECT COUNT(*) FROM coorte) AS total_internacoes,
    (SELECT SUM(CASE WHEN "MORTE" = true THEN 1 ELSE 0 END) FROM coorte) AS total_mortes,
    '{_sql_literal(denominator_label)}' AS denominador,
    (SELECT STRING_AGG(
        grupo || ':' || total_internacoes || ':' || total_mortes || ':' ||
        taxa_mortalidade_percentual,
        ' | ' ORDER BY ordem)
     FROM grupos) AS group_distribution,
    (SELECT maior_grupo FROM extremos) AS highest_group,
    (SELECT maior_taxa FROM extremos) AS highest_rate,
    (SELECT menor_grupo FROM extremos) AS lowest_group,
    (SELECT menor_taxa FROM extremos) AS lowest_rate,
    (SELECT ROUND(maior_taxa / NULLIF(menor_taxa, 0), 2) FROM extremos)
        AS rate_ratio_highest_vs_lowest,
    (SELECT CASE
        WHEN total_excluidos > 0 THEN
            'data_scope: ' || CAST(total_excluidos AS VARCHAR) ||
            ' registros ficaram fora do denominador por categoria ausente/invalida'
        ELSE NULL
     END FROM excluidos) AS warnings
FROM (SELECT 1) AS analytic_singleton;
""".strip()


def build_geographic_condition_rate_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    """Build a one-row package for condition rates by state of residence."""
    plan = _coerce_semantic_plan(semantic_plan)
    if plan is None:
        return None
    required_dimensions = set(plan.answer_shape.required_dimensions)
    if not (required_dimensions & {"estado", "SG_UF", "estado_hospital"}):
        return None

    target_sql, resolved_concept_sql = _diagnosis_target_sql_from_plan(plan)
    if not target_sql:
        return None

    scope_conditions = _scope_conditions_from_plan(plan, "i")
    scope_where = f" AND {' AND '.join(scope_conditions)}" if scope_conditions else ""

    return f"""
WITH diagnosticos_alvo("CID") AS (
    {target_sql}
), diagnosticos_resolvidos AS (
    SELECT d."CID", COALESCE(c."DESCRICAO", '') AS "DESCRICAO"
    FROM diagnosticos_alvo d
    LEFT JOIN cid c ON c."CID" = d."CID"
), denominador_estado AS (
    SELECT mu."SG_UF" AS estado, COUNT(*) AS total_denominador
    FROM internacoes i
    JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
    WHERE mu."SG_UF" IN ({_VALID_UF_VALUES}){scope_where}
    GROUP BY mu."SG_UF"
), casos_estado AS (
    SELECT mu."SG_UF" AS estado, COUNT(*) AS total_internacoes
    FROM internacoes i
    JOIN diagnosticos_alvo d ON i."DIAG_PRINC" = d."CID"
    JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
    WHERE mu."SG_UF" IN ({_VALID_UF_VALUES}){scope_where}
    GROUP BY mu."SG_UF"
), grupos AS (
    SELECT
        d.estado,
        COALESCE(c.total_internacoes, 0) AS total_internacoes,
        d.total_denominador,
        ROUND(COALESCE(c.total_internacoes, 0) * 100000.0 / NULLIF(d.total_denominador, 0), 2)
            AS taxa_por_100k_denominador,
        ROUND(COALESCE(c.total_internacoes, 0) * 100.0 /
            NULLIF(SUM(COALESCE(c.total_internacoes, 0)) OVER (), 0), 2)
            AS percentual_casos
    FROM denominador_estado d
    LEFT JOIN casos_estado c ON c.estado = d.estado
), extremos AS (
    SELECT
        (SELECT estado FROM grupos ORDER BY taxa_por_100k_denominador DESC, total_internacoes DESC LIMIT 1)
            AS maior_grupo,
        (SELECT taxa_por_100k_denominador FROM grupos ORDER BY taxa_por_100k_denominador DESC, total_internacoes DESC LIMIT 1)
            AS maior_taxa,
        (SELECT estado FROM grupos WHERE total_internacoes > 0 ORDER BY taxa_por_100k_denominador ASC, total_internacoes DESC LIMIT 1)
            AS menor_grupo,
        (SELECT taxa_por_100k_denominador FROM grupos WHERE total_internacoes > 0 ORDER BY taxa_por_100k_denominador ASC, total_internacoes DESC LIMIT 1)
            AS menor_taxa
)
SELECT
    'geographic_condition_rate' AS analysis_type,
    {resolved_concept_sql} AS resolved_concept,
    'estado de residencia' AS factor_name,
    (SELECT SUM(total_internacoes) FROM grupos) AS total_internacoes,
    'internacoes mapeadas por UF de residencia' AS denominador,
    (SELECT STRING_AGG(
        estado || ':' || total_internacoes || ':' || total_denominador || ':' ||
        taxa_por_100k_denominador || ':' || percentual_casos,
        ' | ' ORDER BY taxa_por_100k_denominador DESC, total_internacoes DESC)
     FROM grupos) AS group_distribution,
    (SELECT maior_grupo FROM extremos) AS highest_group,
    (SELECT maior_taxa FROM extremos) AS highest_rate,
    (SELECT menor_grupo FROM extremos) AS lowest_group,
    (SELECT menor_taxa FROM extremos) AS lowest_rate,
    (SELECT ROUND(maior_taxa / NULLIF(menor_taxa, 0), 2) FROM extremos)
        AS rate_ratio_highest_vs_lowest,
    'data_scope: considera apenas internacoes com municipio de residencia mapeado para UF valida'
        AS warnings
FROM (SELECT 1) AS analytic_singleton;
""".strip()


def build_temporal_condition_trend_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    """Build a one-row package for annual trends of a resolved diagnosis condition."""
    plan = _coerce_semantic_plan(semantic_plan)
    if plan is None or plan.answer_shape.row_grain != "time_series":
        return None
    if "ano" not in set(plan.answer_shape.required_dimensions):
        return None

    target_sql, resolved_concept_sql = _diagnosis_target_sql_from_plan(plan)
    if not target_sql:
        return None
    scope_conditions = _scope_conditions_from_plan(plan, "i")
    scope_where = f" AND {' AND '.join(scope_conditions)}" if scope_conditions else ""

    return f"""
WITH diagnosticos_alvo("CID") AS (
    {target_sql}
), diagnosticos_resolvidos AS (
    SELECT d."CID", COALESCE(c."DESCRICAO", '') AS "DESCRICAO"
    FROM diagnosticos_alvo d
    LEFT JOIN cid c ON c."CID" = d."CID"
), denominador_ano AS (
    SELECT EXTRACT(YEAR FROM i."DT_INTER") AS ano, COUNT(*) AS total_denominador
    FROM internacoes i
    WHERE i."DT_INTER" IS NOT NULL{scope_where}
    GROUP BY ano
), casos_ano AS (
    SELECT EXTRACT(YEAR FROM i."DT_INTER") AS ano, COUNT(*) AS total_internacoes
    FROM internacoes i
    JOIN diagnosticos_alvo d ON i."DIAG_PRINC" = d."CID"
    WHERE i."DT_INTER" IS NOT NULL{scope_where}
    GROUP BY ano
), serie AS (
    SELECT
        d.ano,
        COALESCE(c.total_internacoes, 0) AS total_internacoes,
        d.total_denominador,
        ROUND(COALESCE(c.total_internacoes, 0) * 100000.0 / NULLIF(d.total_denominador, 0), 2)
            AS taxa_por_100k_denominador
    FROM denominador_ano d
    LEFT JOIN casos_ano c ON c.ano = d.ano
), extremos AS (
    SELECT
        (SELECT ano FROM serie ORDER BY ano ASC LIMIT 1) AS primeiro_ano,
        (SELECT total_internacoes FROM serie ORDER BY ano ASC LIMIT 1) AS primeiro_total,
        (SELECT ano FROM serie ORDER BY ano DESC LIMIT 1) AS ultimo_ano,
        (SELECT total_internacoes FROM serie ORDER BY ano DESC LIMIT 1) AS ultimo_total,
        (SELECT ano FROM serie ORDER BY total_internacoes DESC, ano ASC LIMIT 1) AS ano_pico,
        (SELECT total_internacoes FROM serie ORDER BY total_internacoes DESC, ano ASC LIMIT 1)
            AS total_pico
)
SELECT
    'temporal_condition_trend' AS analysis_type,
    {resolved_concept_sql} AS resolved_concept,
    'ano de internacao' AS factor_name,
    (SELECT SUM(total_internacoes) FROM serie) AS total_internacoes,
    'internacoes por ano no mesmo escopo' AS denominador,
    (SELECT STRING_AGG(
        CAST(ano AS VARCHAR) || ':' || total_internacoes || ':' || total_denominador || ':' ||
        taxa_por_100k_denominador,
        ' | ' ORDER BY ano)
     FROM serie) AS time_series,
    (SELECT primeiro_ano FROM extremos) AS first_period,
    (SELECT primeiro_total FROM extremos) AS first_total,
    (SELECT ultimo_ano FROM extremos) AS last_period,
    (SELECT ultimo_total FROM extremos) AS last_total,
    (SELECT ultimo_total - primeiro_total FROM extremos) AS delta_absolute,
    (SELECT ROUND((ultimo_total - primeiro_total) * 100.0 / NULLIF(primeiro_total, 0), 2)
     FROM extremos) AS delta_percent,
    (SELECT ano_pico FROM extremos) AS peak_period,
    (SELECT total_pico FROM extremos) AS peak_total,
    NULL AS warnings
FROM (SELECT 1) AS analytic_singleton;
""".strip()


def _diagnosis_target_sql_from_plan(plan: SemanticPlan) -> tuple[str | None, str]:
    codes = _diagnosis_codes_from_plan(plan)
    if codes:
        code_values = ", ".join(f"('{_sql_literal(code)}')" for code in codes)
        return (
            f"VALUES {code_values}",
            (
                '(SELECT STRING_AGG("CID" || \' - \' || "DESCRICAO", \' | \' ORDER BY "CID") '
                "FROM diagnosticos_resolvidos)"
            ),
        )

    prefixes = _diagnosis_prefixes_from_plan(plan)
    if prefixes:
        prefix_conditions = " OR ".join(
            f'c."CID" LIKE \'{_sql_literal(prefix)}\'' for prefix in prefixes
        )
        label = _diagnosis_label_from_plan(plan) or "CID " + ", ".join(prefixes)
        return (
            f'SELECT c."CID" FROM cid c WHERE {prefix_conditions}',
            f"'{_sql_literal(label)}'",
        )

    description_terms = _diagnosis_description_terms_from_plan(plan)
    if description_terms:
        description_conditions = " OR ".join(
            f'c."DESCRICAO" ILIKE \'%{_sql_literal(term)}%\''
            for term in description_terms
        )
        return (
            f'SELECT c."CID" FROM cid c WHERE {description_conditions}',
            (
                '(SELECT STRING_AGG("CID" || \' - \' || "DESCRICAO", \' | \' ORDER BY "CID") '
                "FROM diagnosticos_resolvidos)"
            ),
        )

    return None, "NULL"


def _coerce_semantic_plan(semantic_plan: SemanticPlan | dict | None) -> SemanticPlan | None:
    if not semantic_plan:
        return None
    try:
        return (
            semantic_plan
            if isinstance(semantic_plan, SemanticPlan)
            else SemanticPlan.model_validate(semantic_plan)
        )
    except Exception:
        return None


def _categorical_factor_from_plan(
    plan: SemanticPlan,
) -> tuple[str, str, str, str, str, str] | None:
    required_dimensions = set(plan.answer_shape.required_dimensions)
    filter_fields = {semantic_filter.field for semantic_filter in plan.filters}
    if "sexo" in required_dimensions:
        return (
            "sexo",
            (
                "CASE "
                "WHEN i.\"SEXO\" = 1 THEN 'Masculino' "
                "WHEN i.\"SEXO\" = 3 THEN 'Feminino' "
                "ELSE 'Sexo ignorado/outro' END"
            ),
            "CASE i.\"SEXO\" WHEN 1 THEN 1 WHEN 3 THEN 2 ELSE 9 END",
            "",
            "internacoes agrupadas por sexo",
            "",
        )
    if "raca_cor" in required_dimensions:
        return (
            "raca_cor",
            'rc."DESCRICAO"',
            "CASE WHEN i.\"RACA_COR\" IN (1, 2, 3, 4, 5) THEN i.\"RACA_COR\" ELSE 9 END",
            'i."RACA_COR" IN (1, 2, 3, 4, 5)',
            "internacoes com raca/cor identificada",
            'JOIN raca_cor rc ON i."RACA_COR" = rc."RACA_COR"',
        )
    if "instrucao" in required_dimensions or "instrucao_valid" in filter_fields:
        return (
            "instrucao",
            'inst."DESCRICAO"',
            'CAST(i."INSTRU" AS INTEGER)',
            'i."INSTRU" IS NOT NULL AND i."INSTRU" != 0',
            "internacoes com instrucao valida",
            'JOIN instrucao inst ON i."INSTRU" = inst."INSTRU"',
        )
    return None


def _categorical_invalid_condition(category_label: str) -> str:
    if category_label == "raca_cor":
        return 'i."RACA_COR" IS NULL OR i."RACA_COR" NOT IN (1, 2, 3, 4, 5)'
    if category_label == "instrucao":
        return 'i."INSTRU" IS NULL OR i."INSTRU" = 0'
    if category_label == "sexo":
        return 'i."SEXO" IS NULL OR i."SEXO" NOT IN (1, 3)'
    return "false"


def _diagnosis_codes_from_plan(plan: SemanticPlan) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()
    for semantic_filter in plan.filters:
        if semantic_filter.field != "diagnostico_principal_codigo":
            continue
        for value in semantic_filter.values:
            code = str(value).strip().upper()
            if code and re.fullmatch(r"[A-Z]\d{2}[A-Z0-9]?", code) and code not in seen:
                seen.add(code)
                codes.append(code)
    return codes


def _diagnosis_prefixes_from_plan(plan: SemanticPlan) -> list[str]:
    prefixes: list[str] = []
    seen: set[str] = set()
    for semantic_filter in plan.filters:
        if semantic_filter.field != "diagnostico_principal_prefix":
            continue
        for value in semantic_filter.values:
            prefix = str(value).strip().upper()
            if prefix and re.fullmatch(r"[A-Z]\d{0,2}%", prefix) and prefix not in seen:
                seen.add(prefix)
                prefixes.append(prefix)
    return prefixes


def _diagnosis_label_from_plan(plan: SemanticPlan) -> str | None:
    labels = [
        str(value).strip()
        for semantic_filter in plan.filters
        if semantic_filter.field == "diagnostico_conceito_label"
        for value in semantic_filter.values
        if str(value).strip()
    ]
    return labels[0] if labels else None


def _diagnosis_description_terms_from_plan(plan: SemanticPlan) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for semantic_filter in plan.filters:
        if semantic_filter.field != "diagnostico_principal_descricao":
            continue
        for value in semantic_filter.values:
            term = str(value).strip()
            if term and term.lower() not in seen:
                seen.add(term.lower())
                terms.append(term)
    return terms


def _scope_conditions_from_plan(plan: SemanticPlan, alias: str) -> list[str]:
    conditions: list[str] = []
    for semantic_filter in plan.filters:
        values = [str(value).strip() for value in semantic_filter.values if str(value).strip()]
        if not values:
            continue
        if semantic_filter.field == "sexo":
            if len(values) == 1:
                conditions.append(f'{alias}."SEXO" = {values[0]}')
            else:
                conditions.append(f'{alias}."SEXO" IN ({", ".join(values)})')
        elif semantic_filter.field == "ano":
            if len(values) == 1:
                conditions.append(f'EXTRACT(YEAR FROM {alias}."DT_INTER") = {values[0]}')
            else:
                conditions.append(
                    f'EXTRACT(YEAR FROM {alias}."DT_INTER") IN ({", ".join(values)})'
                )
        elif semantic_filter.field == "ano_intervalo" and len(values) >= 2:
            conditions.append(
                f'EXTRACT(YEAR FROM {alias}."DT_INTER") BETWEEN {values[0]} AND {values[1]}'
            )
    return conditions


def _denominator_label_from_plan(plan: SemanticPlan) -> str:
    for semantic_filter in plan.filters:
        if semantic_filter.field == "sexo" and semantic_filter.values == ["1"]:
            return "internacoes de homens"
        if semantic_filter.field == "sexo" and semantic_filter.values == ["3"]:
            return "internacoes de mulheres"
    return "todas as internacoes"


def _sql_literal(value: str) -> str:
    return str(value).strip().replace("'", "''")
