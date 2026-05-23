"""Deterministic SQL templates for CID catalog questions."""

from __future__ import annotations

from ..semantic.plan_schema import SemanticPlan

CID_CATALOG_DIMENSION_COLUMNS = {
    "cid_codigo": ('"CID"', "cid"),
    "cid_descricao": ('"DESCRICAO"', "descricao"),
    "cid_categoria": ('"DS_CATEGORIA"', "categoria_cid"),
    "cid_grupo": ('"DS_GRUPO"', "grupo_cid"),
    "cid_capitulo": ('"DS_CAPITULO"', "capitulo_cid"),
    "cid_restrsexo": ('"RESTRSEXO"', "restricao_sexo"),
}


def build_deterministic_cid_catalog_sql(plan: SemanticPlan) -> str | None:
    if plan.base_grain != "cid_catalog":
        return None

    metric_names = {metric.name for metric in plan.metrics}
    scalar_counts = {
        "cid_catalog_count": ('COUNT(DISTINCT "CID")', "total_codigos_cid"),
        "cid_group_catalog_count": ('COUNT(DISTINCT "DS_GRUPO")', "total_grupos_cid"),
        "cid_category_catalog_count": (
            'COUNT(DISTINCT "DS_CATEGORIA")',
            "total_categorias_cid",
        ),
        "cid_chapter_catalog_count": (
            'COUNT(DISTINCT "DS_CAPITULO")',
            "total_capitulos_cid",
        ),
        "cid_restrsexo_catalog_count": (
            'COUNT(DISTINCT "RESTRSEXO")',
            "total_restricoes_sexo",
        ),
    }
    where_conditions = cid_catalog_filter_conditions(plan)
    where_clause = (
        f" WHERE {' AND '.join(dict.fromkeys(where_conditions))}" if where_conditions else ""
    )
    if "cid_duplicate_description_lookup_required" in plan.constraints:
        return (
            'SELECT "DESCRICAO" AS descricao, COUNT(*) AS total_codigos'
            " FROM cid"
            ' WHERE "DESCRICAO" IS NOT NULL AND TRIM("DESCRICAO") <> \'\''
            ' GROUP BY "DESCRICAO"'
            " HAVING COUNT(*) > 1"
            " ORDER BY total_codigos DESC, descricao ASC"
            " LIMIT 50;"
        )
    if plan.answer_shape.row_grain == "single_scalar":
        for metric_name, (expression, alias) in scalar_counts.items():
            if metric_name in metric_names:
                return f"SELECT {expression} AS {alias} FROM cid{where_clause};"

    dimensions = list(plan.answer_shape.required_dimensions)
    dimension = dimensions[0] if dimensions else "cid_codigo"
    if dimension in {"cid_codigo", "cid_descricao"}:
        return (
            'SELECT "CID" AS cid,'
            ' "DESCRICAO" AS descricao,'
            ' "DS_CATEGORIA" AS categoria_cid,'
            ' "DS_GRUPO" AS grupo_cid,'
            ' "DS_CAPITULO" AS capitulo_cid'
            f" FROM cid{where_clause}"
            ' ORDER BY "CID"'
            " LIMIT 50;"
        )

    column_alias = CID_CATALOG_DIMENSION_COLUMNS.get(dimension)
    if column_alias is None:
        return None
    column, alias = column_alias
    nonempty = f"{column} IS NOT NULL AND TRIM({column}) <> ''"
    full_where_conditions = [*where_conditions, nonempty]
    full_where = " WHERE " + " AND ".join(dict.fromkeys(full_where_conditions))
    return (
        f"SELECT {column} AS {alias}, COUNT(*) AS total_codigos"
        f" FROM cid{full_where}"
        f" GROUP BY {column}"
        " ORDER BY total_codigos DESC, "
        f"{alias} ASC"
        " LIMIT 50;"
    )


def cid_catalog_filter_conditions(plan: SemanticPlan) -> list[str]:
    conditions: list[str] = []
    text_columns = ['"DESCRICAO"', '"DS_CATEGORIA"', '"DS_GRUPO"', '"DS_CAPITULO"']
    has_code_or_prefix = any(
        semantic_filter.field.lower()
        in {"diagnostico_principal_codigo", "diagnostico_principal_prefix"}
        and any(str(value).strip() for value in semantic_filter.values)
        for semantic_filter in plan.filters
    )
    for semantic_filter in plan.filters:
        field = semantic_filter.field.lower()
        values = [str(value).strip() for value in semantic_filter.values if str(value).strip()]
        if not values:
            continue
        if field == "diagnostico_principal_codigo":
            quoted = ", ".join(_sql_string_literal(value.upper()) for value in values)
            conditions.append(f'"CID" IN ({quoted})')
        elif field == "diagnostico_principal_prefix":
            values = [
                value.upper() if value.endswith("%") else f"{value.upper()}%" for value in values
            ]
            prefix_conditions = " OR ".join(
                f'"CID" LIKE {_sql_string_literal(value.upper())}' for value in values
            )
            conditions.append(f"({prefix_conditions})")
        elif field == "diagnostico_conceito_termo_expandido" and has_code_or_prefix:
            continue
        elif field in {"diagnostico_principal_descricao", "diagnostico_conceito_termo_expandido"}:
            term_conditions = []
            for value in values:
                term_conditions.extend(
                    f"{column} ILIKE {_sql_string_literal(f'%{value}%')}" for column in text_columns
                )
            conditions.append("(" + " OR ".join(dict.fromkeys(term_conditions)) + ")")
        elif field == "diagnostico_conceito_label":
            continue
    return conditions


def _sql_string_literal(value: str) -> str:
    return "'" + str(value).strip().replace("'", "''") + "'"
