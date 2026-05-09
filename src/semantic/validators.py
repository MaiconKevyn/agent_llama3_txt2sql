"""Generic semantic SQL validators.

Validators operate on a SemanticPlan, not on benchmark question IDs. They catch
common semantic failures that still produce syntactically valid SQL.
"""

from __future__ import annotations

import re

from .contract_validator import validate_sql_contract
from .plan_schema import SemanticPlan
from .sql_inspector import SQLInspector


def _has_group_by_dimension(inspector: SQLInspector, dimension: str) -> bool:
    group_by_lower = inspector.clause_lower("GROUP BY")
    search_space = group_by_lower
    if inspector.has_window_partition():
        search_space = f"{group_by_lower} {inspector.text_lower}"
    patterns = {
        "estado": [r"\bestado\b", r"\bmu\.estado\b", r"\bm\.estado\b"],
        "estado_hospital": [r"\bestado\b", r"\bmu\.estado\b", r"\bm\.estado\b"],
        "municipio": [r"\b(?:nome|municipio|município)\b"],
        "municipio_hospital": [r"\b(?:nome|municipio|município)\b"],
        "hospital": [r"\b(?:cnes|\"cnes\")\b"],
        "especialidade": [r"\bespecialidade\b", r"\bdescri[cç][aã]o\b", r"\bespec\b"],
        "diagnostico": [r"\b(?:cd_descricao|\"cd_descricao\"|diag_princ|cid)\b"],
        "procedimento": [r"\b(?:nome_proc|\"nome_proc\"|proc_rea)\b"],
        "contraceptivo": [r"\b(?:contraceptivo|contracep1|descricao|descri[cç][aã]o)\b"],
        "sexo": [r"\bsexo\b"],
        "raca_cor": [r"\b(?:raca_cor|ra[cç]a|cor|descri[cç][aã]o)\b"],
        "instrucao": [r"\b(?:instru|instrucao|instru[cç][aã]o|descri[cç][aã]o)\b"],
        "idade": [r"\bidade\b"],
        "ano": [r"\b(?:extract\s*\(\s*year|ano)\b"],
        "trimestre": [r"\b(?:extract\s*\(\s*quarter|trimestre)\b"],
        "dia_semana": [r"\b(?:dia_semana|dow|isodow|dayofweek|to_char)\b"],
        "quartil": [r"\b(?:ntile|quartil|ntile_grupo)\b"],
    }
    return any(re.search(pattern, search_space, re.I) for pattern in patterns.get(dimension, []))


def validate_sql_against_semantic_plan(
    plan: SemanticPlan | dict | None,
    sql: str,
    *,
    enable_contract_validation: bool = True,
) -> tuple[bool, str | None]:
    """Return whether SQL satisfies the generic semantic plan constraints."""
    if not plan or not sql:
        return True, None

    if isinstance(plan, dict):
        plan = SemanticPlan.model_validate(plan)

    inspector = SQLInspector.from_sql(sql)
    sql_lower = inspector.text_lower
    answer_shape = plan.answer_shape

    if answer_shape.top_n_scope == "per_group":
        if not re.search(
            r"\b(?:row_number|rank|dense_rank)\s*\(\s*\)\s+over\s*\(", sql_lower, re.I
        ):
            return False, (
                "SEMANTIC PLAN ERROR: The plan requires top-N per group, but SQL does not use "
                "ROW_NUMBER()/RANK() OVER (...). Use a window function partitioned by the group dimension."
            )
        if not inspector.has_window_partition():
            return False, (
                "SEMANTIC PLAN ERROR: The plan requires top-N per group, but SQL has no PARTITION BY."
            )
        if not inspector.constrains_rank(answer_shape.top_n):
            return False, (
                "SEMANTIC PLAN ERROR: SQL uses a per-group window but does not constrain the "
                f"rank to the requested top_n={answer_shape.top_n}."
            )
        output_order_passed, output_order_message = _validate_top_n_per_group_output_order(
            plan,
            inspector,
        )
        if not output_order_passed:
            return False, output_order_message
    elif answer_shape.top_n_scope == "global":
        if answer_shape.top_n is not None and not re.search(
            rf"\blimit\s+{answer_shape.top_n}\b", sql_lower, re.I
        ):
            return False, (
                "SEMANTIC PLAN ERROR: The plan requires a global top-N answer, but SQL does not "
                f"limit the result to top_n={answer_shape.top_n}."
            )
        if answer_shape.top_n is not None and "order by" not in sql_lower:
            return False, (
                "SEMANTIC PLAN ERROR: The plan requires a ranked top-N answer, but SQL has no ORDER BY."
            )

    if answer_shape.requires_group_by:
        absence_antijoin = (
            "absence_condition_requires_antijoin_or_aggregate_zero" in plan.constraints
            and inspector.has_absence_pattern()
            and not inspector.has_group_by()
        )
        if not absence_antijoin:
            for dim in answer_shape.required_dimensions:
                if dim in {"faixa_etaria", "mes"}:
                    continue
                if dim in {
                    "estado",
                    "estado_hospital",
                    "municipio",
                    "municipio_hospital",
                    "hospital",
                    "especialidade",
                    "diagnostico",
                    "procedimento",
                    "contraceptivo",
                    "sexo",
                    "raca_cor",
                    "instrucao",
                    "idade",
                    "ano",
                    "trimestre",
                    "dia_semana",
                    "quartil",
                }:
                    if not inspector.has_group_by():
                        return False, (
                            f"SEMANTIC PLAN ERROR: The plan requires grouping by {dim}, but SQL has no GROUP BY."
                        )
                    if not _has_group_by_dimension(inspector, dim):
                        return False, (
                            f"SEMANTIC PLAN ERROR: The plan requires grouping by {dim}, but SQL GROUP BY does not include that dimension."
                        )

    filter_passed, filter_message = _validate_required_filters(plan, inspector)
    if not filter_passed:
        return False, filter_message

    if (
        answer_shape.row_grain == "single_scalar"
        and answer_shape.top_n_scope == "none"
        and inspector.has_group_by()
    ):
        return False, (
            "SEMANTIC PLAN ERROR: The plan requires a single scalar answer, but SQL has GROUP BY. "
            "Remove grouping and return one aggregate value."
        )

    if "rate_denominator_must_preserve_full_scope" in plan.constraints:
        mortality_metric = any(metric.name == "taxa_mortalidade" for metric in plan.metrics)
        if mortality_metric and inspector.where_filters_outcome("morte", "true"):
            return False, (
                "SEMANTIC PLAN ERROR: Mortality-rate SQL filters MORTE=true in WHERE, which removes "
                "non-death rows from the denominator. Use conditional aggregation for the numerator."
            )
        if mortality_metric and not inspector.has_conditional_aggregation_for("morte"):
            return False, (
                "SEMANTIC PLAN ERROR: Mortality-rate SQL should compute deaths with conditional "
                "aggregation in the numerator."
            )

    if "absence_condition_requires_antijoin_or_aggregate_zero" in plan.constraints:
        if not inspector.has_absence_pattern():
            return False, (
                "SEMANTIC PLAN ERROR: The question asks for absence/non-occurrence, but SQL does not "
                "use NOT EXISTS, LEFT JOIN ... IS NULL, or an aggregate-zero HAVING condition."
            )

    if "include_unknown_bucket_with_left_join_or_coalesce" in plan.null_policy:
        if not inspector.has_unknown_bucket_expression():
            return False, (
                "SEMANTIC PLAN ERROR: The plan requires an explicit unknown/no-information bucket, "
                "but SQL does not use COALESCE or CASE for null/unmatched labels."
            )
        if not inspector.joins_preserve_unknowns():
            return False, (
                "SEMANTIC PLAN ERROR: The plan requires preserving unknown/unmatched rows, but SQL "
                "does not use LEFT JOIN for the lookup."
            )

    constraint_passed, constraint_message = _validate_additional_semantic_constraints(
        plan, inspector
    )
    if not constraint_passed:
        return False, constraint_message

    if answer_shape.row_grain == "time_series":
        if not any(dim in answer_shape.required_dimensions for dim in ["ano", "mes"]):
            return False, "SEMANTIC PLAN ERROR: Time-series plan lacks a temporal output dimension."
        if not inspector.has_group_by():
            return False, "SEMANTIC PLAN ERROR: Time-series SQL must group by a temporal dimension."
        if answer_shape.top_n_scope == "none" and re.search(
            r"\b(?:row_number|rank|dense_rank)\s*\(\s*\)\s+over\s*\(",
            sql_lower,
            re.I,
        ):
            return False, (
                "SEMANTIC PLAN ERROR: Time-series evolution queries must return every requested "
                "period. Do not rank periods or filter to rn=1 unless the question explicitly asks "
                "for top-N periods."
            )
        if _has_unrequested_nonzero_metric_filter(inspector):
            return False, (
                "SEMANTIC PLAN ERROR: Time-series SQL filters metric values to non-zero rows, "
                "but the plan does not request dropping zero-valued periods or groups."
            )

    if enable_contract_validation:
        contract_result = validate_sql_contract(plan, sql)
        if not contract_result.passed:
            return False, contract_result.errors[0]

    return True, None


def _validate_additional_semantic_constraints(
    plan: SemanticPlan,
    inspector: SQLInspector,
) -> tuple[bool, str | None]:
    text = inspector.text_lower
    if "join_path_hospital_location_required" in plan.constraints:
        if not (
            re.search(r"\bhospital\b", text)
            and re.search(r"\bmunic_mov\b", text)
            and re.search(r"\bcnes\b", text)
        ):
            return False, (
                "SEMANTIC PLAN ERROR: The question refers to municipality/state of care or hospital location, "
                "but SQL does not use internacoes.CNES -> hospital.CNES -> hospital.MUNIC_MOV -> municipios.codigo_6d."
            )
        if re.search(r"\bmunic_res\b", text) and not re.search(r"\bmunic_mov\b", text):
            return False, (
                "SEMANTIC PLAN ERROR: SQL uses patient residence municipality (MUNIC_RES), but the question asks for care/hospital location."
            )

    if "geographic_filter_dimension_not_output" in plan.constraints:
        group_by = inspector.clause_lower("GROUP BY")
        required_dimensions = set(plan.answer_shape.required_dimensions)
        if not (required_dimensions & {"municipio", "municipio_hospital"}):
            if re.search(
                r"\b(?:mu|m)\s*\.\s*\"?nome\"?\b|\bmunicipio\b|\bmunic[ií]pio\b",
                group_by,
                re.I,
            ):
                return False, (
                    "SEMANTIC PLAN ERROR: The geography mention is a filter/location scope, "
                    "not an output grouping dimension. Do not GROUP BY municipality/city unless "
                    "the question explicitly asks for municipalities/cities as rows."
                )
        if not (required_dimensions & {"estado", "estado_hospital"}):
            if re.search(r"\bestado\b", group_by, re.I):
                return False, (
                    "SEMANTIC PLAN ERROR: The state mention is a filter, not an output grouping dimension."
                )

    if "diagnosis_filter_dimension_not_output" in plan.constraints:
        group_by = inspector.clause_lower("GROUP BY")
        if re.search(r"\bdiag_princ\b|\bcd_descricao\b|\bcid\b", group_by, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: The diagnosis/category mention is a filter, "
                "not an output grouping dimension. Do not GROUP BY diagnosis/CID unless "
                "the question asks for a diagnosis breakdown."
            )

    metric_names = {metric.name for metric in plan.metrics}
    if "proporcao" in metric_names:
        if re.search(
            r"\bavg\s*\(\s*case\s+when[\s\S]{0,240}then\s+1\s+else\s+0\s+end\s*\)"
            r"\s*\*\s*100(?:\.0+)?\s*/\s*count\s*\(",
            text,
            re.I,
        ):
            return False, (
                "SEMANTIC PLAN ERROR: Rate SQL double-divides AVG(CASE...) by COUNT(*). "
                "Use SUM(CASE WHEN condition THEN 1 ELSE 0 END) * 100.0 / COUNT(*)."
            )
        if (
            any(semantic_filter.field == "uti" for semantic_filter in plan.filters)
            and "filtered_cohort_percentage_distribution" not in plan.constraints
        ):
            where = inspector.clause_lower("WHERE")
            if re.search(r"\bval_uti\b\"?\s*>\s*0\b", where, re.I):
                return False, (
                    "SEMANTIC PLAN ERROR: UTI rate SQL filters VAL_UTI > 0 in WHERE, "
                    "which removes non-UTI rows from the denominator. Use conditional "
                    "aggregation for the numerator."
                )

    if "percentage_denominator_matches_filtered_category" in plan.constraints:
        if "sum(count(" not in text and re.search(
            r"\bwith\s+total[\w_]*\s+as\s*\((?![\s\S]{0,320}\bdiag_princ\b[\s\S]{0,80}\blike\s+['\"]j%)",
            text,
            re.I,
        ):
            return False, (
                "SEMANTIC PLAN ERROR: Percentage denominator must match the filtered disease "
                "category scope. Use the CID J% filtered rows as the percentage base, not all admissions."
            )

    if "reference_rate_comparison_required" in plan.constraints:
        if not re.search(r"\b(?:2\s*\*|>\s*2\s*\*)", text, re.I) and "duas vezes" not in text:
            return False, (
                "SEMANTIC PLAN ERROR: The SQL does not apply the requested ratio threshold "
                "against the reference average."
            )

    if "contraceptive_obstetric_filter_required" in plan.constraints:
        if "contraceptivos" not in text or "contracep1" not in text:
            return False, (
                "SEMANTIC PLAN ERROR: Contraceptive-method questions must use the contraceptivos "
                "lookup joined from internacoes.CONTRACEP1."
            )
        if not re.search(r"\bespec\b\"?\s*=\s*2\b", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Contraceptive-method distributions must be scoped to "
                "obstetric admissions with ESPEC = 2."
            )

    if "sex_label_output_required" in plan.constraints:
        has_case_labels = bool(
            re.search(r"\bcase\s+when[\s\S]{0,240}masculino[\s\S]{0,240}feminino", text, re.I)
        )
        has_lookup_label = bool(
            re.search(r"\bjoin\s+sexo\b[\s\S]{0,240}\bdescri[cç][aã]o\b", text, re.I)
        )
        if not (has_case_labels or has_lookup_label):
            return False, (
                "SEMANTIC PLAN ERROR: Sex-grouped output must return human-readable labels "
                "('Masculino'/'Feminino') via CASE or the sexo lookup, not raw SEXO codes."
            )

    if "death_cause_cid_requires_cid_morte_antijoin" in plan.constraints:
        if "cid_morte" not in text:
            return False, (
                "SEMANTIC PLAN ERROR: Death-cause CID questions must use internacoes.CID_MORTE, "
                "not DIAG_PRINC, as the observed death-cause code."
            )
        if not re.search(r"\bmorte\b\"?\s*=\s*true\b", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Death-cause CID questions must filter registered deaths "
                "with MORTE = true."
            )
        if not re.search(r"\bnot\s+exists\b[\s\S]{0,400}\bdiag_princ\b", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: The anti-condition must use NOT EXISTS against "
                "internacoes.DIAG_PRINC for the same CID code."
            )
        if not re.search(r"\bcount\s*\(", text, re.I) or not inspector.has_group_by():
            return False, (
                "SEMANTIC PLAN ERROR: Death-cause anti-condition lists should include support "
                "counts per CID, grouped by CID/description, so the result is auditable and ranked."
            )
        if not re.search(r"\border\s+by[\s\S]{0,120}\bcount\s*\(|\border\s+by[\s\S]{0,120}total", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Death-cause anti-condition lists should be ordered by "
                "support count descending."
            )
        if not re.search(r"\blimit\s+\d+\b", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: High-cardinality anti-condition entity lists should be "
                "bounded with LIMIT for a reliable final answer."
            )

    if "death_cause_description_requires_cid_morte" in plan.constraints:
        if "cid_morte" not in text:
            return False, (
                "SEMANTIC PLAN ERROR: Disease death-cause questions must join/filter cid through "
                "internacoes.CID_MORTE, not DIAG_PRINC."
            )
        if not re.search(r"\bmorte\b\"?\s*=\s*true\b", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Disease death-cause questions must filter registered deaths "
                "with MORTE = true."
            )
        if re.search(r"\bjoin\s+cid\b[\s\S]{0,160}\bdiag_princ\b", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Disease death-cause questions should not join cid through "
                "DIAG_PRINC when the wording asks what caused/occasioned death."
            )

    if "categorical_lookup_label_required" in plan.constraints:
        if "raca_cor" in plan.answer_shape.required_dimensions:
            if "raca_cor" not in text:
                return False, (
                    "SEMANTIC PLAN ERROR: Race/color distributions must use the raca_cor lookup "
                    "table so output rows are descriptive labels, not only raw codes."
                )
            if not re.search(r"\bdescri[cç][aã]o\b", text, re.I):
                return False, (
                    "SEMANTIC PLAN ERROR: Race/color distributions must project/group the lookup "
                    "description column."
                )

    if "filtered_cohort_percentage_distribution" in plan.constraints:
        if "dia_semana" in plan.answer_shape.required_dimensions and not (
            "tempo" in text and "dia_semana" in text
        ):
            return False, (
                "SEMANTIC PLAN ERROR: Weekday distributions must use the canonical tempo.dia_semana "
                "dimension instead of ad-hoc date extraction."
            )
        where = inspector.clause_lower("WHERE")
        if not re.search(r"\bval_uti\b\"?\s*>\s*0\b", where, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: UTI distribution percentages must filter to UTI admissions "
                "with VAL_UTI > 0 before computing the distribution."
            )
        if "sum(count(" not in text and not re.search(
            r"\bcount\s*\(\s*\*\s*\)\s*\*\s*100(?:\.0+)?\s*/\s*sum\s*\(\s*count\s*\(",
            text,
            re.I,
        ):
            return False, (
                "SEMANTIC PLAN ERROR: Distribution percentages over a filtered cohort must divide "
                "each group count by SUM(COUNT(*)) OVER () for that filtered cohort."
            )

    if "side_by_side_state_pivot_required" in plan.constraints:
        group_by = inspector.clause_lower("GROUP BY")
        if re.search(r"\bestado\b", group_by, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Side-by-side state comparisons must pivot states into "
                "separate columns, not return long-format rows grouped by state."
            )
        if not re.search(r"\bcase\s+when[\s\S]{0,220}\bestado\b", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Side-by-side state comparisons require conditional "
                "aggregates with CASE WHEN estado = ... for each compared state."
            )
        state_values = [
            str(value).lower()
            for semantic_filter in plan.filters
            if semantic_filter.field in {"estado", "estado_residencia"}
            for value in semantic_filter.values
        ]
        for state in state_values:
            if state not in text:
                return False, (
                    f"SEMANTIC PLAN ERROR: Side-by-side pivot is missing state column/filter for {state.upper()}."
                )
            if not re.search(
                rf"\bcount\s*\(\s*case\s+when[\s\S]{{0,160}}\bestado\b[\s\S]{{0,80}}{re.escape(state)}",
                text,
                re.I,
            ):
                return False, (
                    "SEMANTIC PLAN ERROR: Side-by-side state comparisons must output support "
                    f"counts for {state.upper()} so averages are auditable."
                )
        having = inspector.clause_lower("HAVING")
        if state_values and not having:
            return False, (
                "SEMANTIC PLAN ERROR: Side-by-side state comparisons must require support on each "
                "compared side to avoid rows with one side missing."
            )
        for state in state_values:
            if not re.search(
                rf"\bcount\s*\(\s*case\s+when[\s\S]{{0,160}}\bestado\b[\s\S]{{0,80}}{re.escape(state)}[\s\S]{{0,120}}\)\s*(?:>|>=)\s*(?:0|1|100)\b",
                having,
                re.I,
            ):
                return False, (
                    "SEMANTIC PLAN ERROR: Side-by-side state comparisons must apply a per-state "
                    f"support threshold for {state.upper()} in HAVING."
                )

    if any(metric.name == "media_dias_permanencia" for metric in plan.metrics):
        if "dias_perm" not in text:
            return False, (
                "SEMANTIC PLAN ERROR: Average length-of-stay questions must aggregate "
                "internacoes.DIAS_PERM."
            )

    if "temporal_comparison_requires_separate_period_aggregates" in plan.constraints:
        passed, message = _validate_temporal_period_comparison(plan, inspector)
        if not passed:
            return False, message

    if "moving_average_requires_preaggregated_time_series" in plan.constraints:
        passed, message = _validate_moving_average(plan, inspector)
        if not passed:
            return False, message

    if "quartile_distribution_requires_ntile_interval" in plan.constraints:
        passed, message = _validate_quartile_distribution(plan, inspector)
        if not passed:
            return False, message

    if "domain_instrucao_valid_required" in plan.constraints:
        if "instrucao" not in text:
            return False, (
                "SEMANTIC PLAN ERROR: The plan requires education-level labels, but SQL does not join/use instrucao."
            )
        if not re.search(r"\binstru\b[\s\S]{0,80}\bis\s+not\s+null\b", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Education-level analysis must exclude NULL INSTRU values."
            )
        if not re.search(r"\binstru\b\"?\s*(?:!=|<>)\s*0\b", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Education-level analysis must exclude INSTRU=0 unless unknown bucket is requested."
            )

    if "socioeconomico_metric_filter_required" in plan.constraints:
        expected_metrics = [
            value
            for semantic_filter in plan.filters
            if semantic_filter.field == "metrica"
            for value in semantic_filter.values
        ]
        if "socioeconomico" not in text:
            return False, (
                "SEMANTIC PLAN ERROR: The requested metric belongs to socioeconomico, but SQL does not use socioeconomico."
            )
        for expected_metric in expected_metrics:
            if expected_metric.lower() not in text:
                return False, (
                    f"SEMANTIC PLAN ERROR: SQL does not filter socioeconomico.metrica='{expected_metric}'."
                )
        sum_value_metrics = {"bolsa_familia_total", "esgotamento_sanitario_domicilio"}
        if (
            "socioeconomico_multi_metric_requires_conditional_pivot" not in plan.constraints
            and metric_names & sum_value_metrics
            and not re.search(
            r"\bsum\s*\(\s*(?:[a-z_][\w]*\.)?\"?valor\"?\s*\)",
            text,
            re.I,
            )
        ):
            return False, (
                "SEMANTIC PLAN ERROR: Socioeconomic total metrics must aggregate "
                "socioeconomico.valor with SUM(valor), not COUNT(*)."
            )

    if "socioeconomico_multi_metric_requires_conditional_pivot" in plan.constraints:
        expected_metrics = [
            value
            for semantic_filter in plan.filters
            if semantic_filter.field == "metrica"
            for value in semantic_filter.values
        ]
        if "socioeconomico" not in text or "municipios" not in text:
            return False, (
                "SEMANTIC PLAN ERROR: Multi-metric socioeconomic questions must join "
                "socioeconomico to municipios."
            )
        if not re.search(r"\bcase\s+when[\s\S]{0,200}\bmetrica\b", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Multi-metric socioeconomic questions require conditional "
                "pivot expressions over socioeconomico.metrica."
            )
        if re.search(r"\bsum\s*\(\s*case\s+when[\s\S]{0,120}\bmetrica\b", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Multi-year socioeconomic indicator pivots should not SUM "
                "conditional metric values unless the question asks for a time-total. Use MAX/AVG "
                "per municipality metric to avoid accumulating the long-format time series."
            )
        for expected_metric in expected_metrics:
            if expected_metric.lower() not in text:
                return False, (
                    f"SEMANTIC PLAN ERROR: SQL does not pivot socioeconomico.metrica='{expected_metric}'."
                )

    if "idhm_mortality_cohort_requires_state_rate_split" in plan.constraints:
        select_clause = inspector.clause_lower("SELECT")
        if not all(token in text for token in ["internacoes", "municipios", "socioeconomico"]):
            return False, (
                "SEMANTIC PLAN ERROR: IDHM mortality cohort questions must combine internacoes "
                "for hospital mortality with socioeconomico for IDHM through municipios.codigo_6d."
            )
        if re.search(r"\bselect\s+avg\s*\(\s*taxa\w*\s*\)\s+from\s+taxa_mortalidade\b", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: IDHM mortality cohort must compare each municipality rate "
                "against the state-level mortality rate over all admissions, not AVG(taxa) across "
                "municipalities."
            )
        if not re.search(r"\bcount\s*\(", select_clause, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: IDHM mortality cohort output must include the municipality "
                "support count per above/below group."
            )
        if not re.search(r"\bavg\s*\(\s*(?:[a-z_][\w]*\.)?\"?valor\"?\s*\)", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: IDHM mortality cohort output must aggregate IDHM with "
                "AVG(socioeconomico.valor) after filtering metrica='idhm'."
            )

    if "catalog_cardinality_must_use_reference_table" in plan.constraints:
        metric_names = {metric.name for metric in plan.metrics}
        catalog_requirements = {
            "cid_catalog_count": {
                "table": "cid",
                "label": "CID catalog",
                "forbidden": [r"\binternacoes\b", r"\bdiag_princ\b", r"\bdiag_secun\b", r"\bcid_morte\b"],
            },
            "vincprev_catalog_count": {
                "table": "vincprev",
                "label": "vinculo previdenciario catalog",
                "forbidden": [r"\binternacoes\b"],
            },
            "municipio_catalog_count": {
                "table": "municipios",
                "label": "municipality reference coverage",
                "forbidden": [r"\binternacoes\b"],
            },
            "estado_coverage_count": {
                "table": "municipios",
                "label": "state coverage reference",
                "forbidden": [r"\binternacoes\b"],
            },
        }
        for metric_name, requirement in catalog_requirements.items():
            if metric_name not in metric_names:
                continue
            table = requirement["table"]
            if not re.search(rf"\bfrom\s+\"?{re.escape(table)}\"?\b", text, re.I):
                return False, (
                    f"SEMANTIC PLAN ERROR: {requirement['label']} cardinality questions must count "
                    f"the {table} reference table, not observed fact-table values."
                )
            if any(re.search(pattern, text, re.I) for pattern in requirement["forbidden"]):
                return False, (
                    "SEMANTIC PLAN ERROR: The question asks for reference/catalog coverage. "
                    "Do not join or count fact-table observed values unless the question explicitly "
                    "asks for observed/used/registered values in admissions."
                )

    min_counts = [
        int(value)
        for semantic_filter in plan.filters
        if semantic_filter.field == "minimum_group_count"
        for value in semantic_filter.values
        if str(value).isdigit()
    ]
    if min_counts:
        min_count = min_counts[0]
        having = inspector.clause_lower("HAVING") or text
        if not re.search(
            rf"\bcount\s*\([^)]*\)\s*(?:>|>=)\s*{min_count}\b", having, re.I
        ):
            return False, (
                "SEMANTIC PLAN ERROR: SQL must apply the requested minimum group support "
                f"with HAVING COUNT(*) > {min_count} or an equivalent threshold."
            )

    if "top_n_average_high_cardinality_requires_minimum_group_size" in plan.constraints:
        min_count = min_counts[0] if min_counts else 100
        having = inspector.clause_lower("HAVING") or text
        if not re.search(
            rf"\bcount\s*\([^)]*\)\s*(?:>|>=)\s*{min_count}\b", having, re.I
        ):
            return False, (
                "SEMANTIC PLAN ERROR: Top-N ranking by average/rate over high-cardinality entities "
                f"must apply HAVING COUNT(*) > {min_count} or an equivalent group-support threshold."
            )

    return True, None


def _validate_temporal_period_comparison(
    plan: SemanticPlan,
    inspector: SQLInspector,
) -> tuple[bool, str | None]:
    text = inspector.text_lower
    period_filters = [
        semantic_filter
        for semantic_filter in plan.filters
        if semantic_filter.field.startswith("period_") and len(semantic_filter.values) >= 2
    ]
    if len(period_filters) < 2:
        return True, None

    for semantic_filter in period_filters[:2]:
        start_year, end_year = str(semantic_filter.values[0]), str(semantic_filter.values[1])
        if start_year not in text or end_year not in text:
            return False, (
                "SEMANTIC PLAN ERROR: Temporal comparison SQL does not apply both requested "
                "period boundaries."
            )

    if re.search(r"\bfull\s+outer\s+join\b", text, re.I):
        return False, (
            "SEMANTIC PLAN ERROR: Temporal growth/decline comparisons should compare matched "
            "entities present in both periods. Use an INNER JOIN between period aggregates unless "
            "the question explicitly asks for appeared/disappeared entities."
        )

    if "temporal_comparison_outputs_period_counts_and_delta" in plan.constraints:
        has_initial_period_output = re.search(
            r"\b(?:periodo|period|antes|before|inicial|base)[\w_]*\b", text, re.I
        ) or _has_period_alias(text, period_filters[0])
        has_final_period_output = re.search(
            r"\b(?:periodo|period|depois|after|final|atual)[\w_]*\b", text, re.I
        ) or _has_period_alias(text, period_filters[1])
        has_delta_output = re.search(
            r"\b(?:crescimento|queda|delta|diferen[cç]a|variacao|varia[cç][aã]o)[\w_]*\b",
            text,
            re.I,
        )
        if not (has_initial_period_output and has_final_period_output and has_delta_output):
            return False, (
                "SEMANTIC PLAN ERROR: Temporal comparison SQL must output both period counts "
                "and the derived growth/decline delta, not only the delta."
            )

    if "temporal_decline_uses_before_minus_after" in plan.constraints:
        if not re.search(
            r"(?:p1|periodo_?1|before|antes|base)[\w.\"\s]*-\s*(?:p2|periodo_?2|after|depois|final)",
            text,
            re.I,
        ) and not re.search(r"\bqueda\b", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Decline comparisons must compute a positive drop as "
                "period_1_count - period_2_count and sort that drop descending."
            )

    if "temporal_growth_uses_after_minus_before" in plan.constraints:
        if not re.search(
            r"(?:p2|periodo_?2|after|depois|final)[\w.\"\s]*-\s*(?:p1|periodo_?1|before|antes|base)",
            text,
            re.I,
        ) and not re.search(r"\bcrescimento\b", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Growth comparisons must compute growth as "
                "period_2_count - period_1_count and sort that growth descending."
            )

    return True, None


def _has_period_alias(text: str, semantic_filter: object) -> bool:
    values = getattr(semantic_filter, "values", [])
    if len(values) < 2:
        return False
    start_year, end_year = str(values[0]), str(values[1])
    return bool(
        re.search(
            rf"\b(?:periodo|period)[\w_]*{re.escape(start_year)}[\w_]*{re.escape(end_year)}\b",
            text,
            re.I,
        )
    )


def _validate_moving_average(
    plan: SemanticPlan,
    inspector: SQLInspector,
) -> tuple[bool, str | None]:
    text = inspector.text_lower
    if not re.search(r"\bcount\s*\(", text, re.I):
        return False, (
            "SEMANTIC PLAN ERROR: Moving average of admissions must aggregate annual "
            "admission counts first with COUNT(*)."
        )
    if not re.search(
        r"\bavg\s*\(\s*(?:total_internacoes|total|count_[\w]+)[\w.\"\s]*\)\s+over\s*\(",
        text,
        re.I,
    ):
        return False, (
            "SEMANTIC PLAN ERROR: Moving average must apply AVG(...) OVER (...) to the "
            "pre-aggregated yearly count, not AVG() over raw admission values."
        )
    if not re.search(r"\brows\s+between\s+2\s+preceding\s+and\s+current\s+row\b", text, re.I):
        return False, (
            "SEMANTIC PLAN ERROR: A 3-period moving average must use ROWS BETWEEN 2 "
            "PRECEDING AND CURRENT ROW over the ordered yearly aggregate."
        )
    if not re.search(r"\bround\s*\(\s*avg\s*\(", text, re.I):
        return False, (
            "SEMANTIC PLAN ERROR: Moving average output should include a rounded moving-average "
            "value together with the yearly count for stable analytical reporting."
        )
    if "ano" in plan.answer_shape.required_dimensions and not re.search(
        r"\bextract\s*\(\s*year|\bano\b",
        text,
        re.I,
    ):
        return False, (
            "SEMANTIC PLAN ERROR: Moving average by year must preserve the year output dimension."
        )
    return True, None


def _validate_quartile_distribution(
    plan: SemanticPlan,
    inspector: SQLInspector,
) -> tuple[bool, str | None]:
    text = inspector.text_lower
    if not re.search(r"\bntile\s*\(\s*4\s*\)\s+over\s*\(", text, re.I):
        return False, (
            "SEMANTIC PLAN ERROR: Quartile distributions must use NTILE(4) over entity volumes."
        )
    if not re.search(r"\bcount\s*\(", text, re.I):
        return False, (
            "SEMANTIC PLAN ERROR: Quartile distribution must count entities per quartile."
        )
    if not re.search(r"\bmin\s*\(", text, re.I) or not re.search(r"\bmax\s*\(", text, re.I):
        return False, (
            "SEMANTIC PLAN ERROR: Quartile distribution must return the interval of volumes "
            "with MIN(total) and MAX(total)."
        )
    if not re.search(r"\bcnes\b", text, re.I):
        return False, (
            "SEMANTIC PLAN ERROR: Hospital-volume quartiles must compute volume per hospital/CNES first."
        )
    return True, None


def _validate_top_n_per_group_output_order(
    plan: SemanticPlan,
    inspector: SQLInspector,
) -> tuple[bool, str | None]:
    partition_dimensions = plan.answer_shape.partition_dimensions
    ranked_dimensions = plan.answer_shape.ranked_dimensions
    if not partition_dimensions or not ranked_dimensions:
        return True, None

    select_items = _split_select_items(inspector.clause_text("SELECT"))
    if not select_items:
        return True, None

    partition_positions = [
        position
        for dimension in partition_dimensions
        if (position := _first_dimension_select_position(select_items, dimension)) is not None
    ]
    ranked_positions = [
        position
        for dimension in ranked_dimensions
        if (position := _first_dimension_select_position(select_items, dimension)) is not None
    ]
    if not partition_positions or not ranked_positions:
        return True, None
    if min(ranked_positions) < min(partition_positions):
        return False, (
            "SEMANTIC PLAN ERROR: Top-N-per-group output should project the group/partition "
            "dimension before the ranked entity, so result rows are shaped as group, entity, metric."
        )
    return True, None


def _split_select_items(select_clause: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    depth = 0
    for char in select_clause:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(depth - 1, 0)
        if char == "," and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item.lower())
            current = []
        else:
            current.append(char)
    item = "".join(current).strip()
    if item:
        items.append(item.lower())
    return items


def _first_dimension_select_position(select_items: list[str], dimension: str) -> int | None:
    patterns = {
        "estado": [r"\bestado\b"],
        "estado_hospital": [r"\bestado\b"],
        "municipio": [r"\bnome\b", r"\bmunicipio\b", r"\bmunic[ií]pio\b"],
        "municipio_hospital": [r"\bnome\b", r"\bmunicipio\b", r"\bmunic[ií]pio\b"],
        "hospital": [r"\bcnes\b"],
        "especialidade": [r"\bespecialidade\b", r"\bdescri[cç][aã]o\b", r"\bespec\b"],
        "diagnostico": [r"\bcd_descricao\b", r"\bdiag_princ\b", r"\bcid\b"],
        "procedimento": [r"\bnome_proc\b", r"\bproc_rea\b", r"\bprocedimento\b"],
        "contraceptivo": [r"\bcontraceptivo\b", r"\bcontracep1\b", r"\bdescri[cç][aã]o\b"],
        "sexo": [r"\bsexo\b"],
        "raca_cor": [r"\braca_cor\b", r"\bra[cç]a\b", r"\bcor\b"],
        "instrucao": [r"\binstru\b", r"\binstrucao\b", r"\binstru[cç][aã]o\b"],
        "idade": [r"\bidade\b"],
        "faixa_etaria": [r"\bfaixa\b", r"\bidade\b"],
        "ano": [r"\bano\b", r"\bextract\s*\(\s*year\b"],
        "mes": [r"\bmes\b", r"\bm[eê]s\b", r"\bextract\s*\(\s*month\b"],
        "dia_semana": [r"\bdia_semana\b", r"\bdia\s+da\s+semana\b"],
        "quartil": [r"\bntile\b", r"\bquartil\b", r"\bntile_grupo\b"],
    }
    for index, item in enumerate(select_items):
        if any(re.search(pattern, item, re.I) for pattern in patterns.get(dimension, [])):
            return index
    return None


def _validate_required_filters(
    plan: SemanticPlan,
    inspector: SQLInspector,
) -> tuple[bool, str | None]:
    text = inspector.text_lower
    for semantic_filter in plan.filters:
        field = semantic_filter.field.lower()
        values = [str(value).lower() for value in semantic_filter.values]
        if field in {"estado", "estado_residencia"} and values:
            if not all(
                re.search(rf"['\"]?{re.escape(value.lower())}['\"]?", text) for value in values
            ):
                return False, (
                    "SEMANTIC PLAN ERROR: SQL does not apply the requested estado filter."
                )
        elif field in {"ano", "ano_internacao"} and values:
            if not all(value in text for value in values):
                return False, "SEMANTIC PLAN ERROR: SQL does not apply the requested year filter."
        elif field == "ano_intervalo" and len(values) >= 2:
            start_year, end_year = values[0], values[1]
            exclusive_end_year = str(int(end_year) + 1) if end_year.isdigit() else ""
            has_start = start_year in text
            has_end = end_year in text or (exclusive_end_year and exclusive_end_year in text)
            has_temporal_expression = any(
                token in text for token in ["extract(year", "dt_inter", "between"]
            )
            if not (has_start and has_end and has_temporal_expression):
                return False, "SEMANTIC PLAN ERROR: SQL does not apply the requested year range filter."
        elif field == "sexo" and values:
            if "sexo" not in text or not any(value in text for value in values):
                return False, "SEMANTIC PLAN ERROR: SQL does not apply the requested sex filter."
        elif field == "idade" and values:
            expected = values[0]
            if not re.search(rf"\bidade\b\"?\s*{re.escape(semantic_filter.operator)}\s*{re.escape(expected)}\b", text, re.I):
                return False, "SEMANTIC PLAN ERROR: SQL does not apply the requested age filter."
        elif field == "uti":
            if "val_uti" not in text:
                return False, "SEMANTIC PLAN ERROR: SQL does not apply the requested UTI filter."
        elif field == "obstetrico":
            if not re.search(r"\bespec\b\"?\s*=\s*2\b", text, re.I):
                return False, (
                    "SEMANTIC PLAN ERROR: SQL does not apply the requested obstetric filter ESPEC = 2."
                )
        elif field == "mes_internacao" and values:
            month_values_present = all(
                re.search(rf"(?<!\d){re.escape(value)}(?!\d)", text) for value in values
            )
            has_between = re.search(r"\bbetween\s+6\s+and\s+8\b", text, re.I)
            if "month" not in text or not (month_values_present or has_between):
                return False, "SEMANTIC PLAN ERROR: SQL does not apply the requested month/season filter."
        elif field == "diagnostico_principal_prefix" and values:
            expected_prefix = values[0].replace("%", "").lower()
            has_diag_column = re.search(r"\bdiag_princ\b|\bcid\b", text, re.I)
            has_prefix = re.search(
                rf"\blike\s+['\"]{re.escape(expected_prefix)}%['\"]",
                text,
                re.I,
            )
            if not has_diag_column or not has_prefix:
                return False, (
                    "SEMANTIC PLAN ERROR: SQL does not apply the requested diagnosis prefix filter."
                )
        elif field == "diagnostico_principal_required":
            if not re.search(r"\bdiag_princ\b[\s\S]{0,80}\bis\s+not\s+null\b", text, re.I):
                return False, "SEMANTIC PLAN ERROR: SQL does not require DIAG_PRINC IS NOT NULL."
        elif field == "diagnostico_secundario_required":
            if not re.search(r"\bdiag_secun\b[\s\S]{0,80}\bis\s+not\s+null\b", text, re.I):
                return False, "SEMANTIC PLAN ERROR: SQL does not require DIAG_SECUN IS NOT NULL."
        elif field == "desfecho" and any("morte" in value for value in values):
            if not re.search(r"\bmorte\b", text, re.I):
                return False, "SEMANTIC PLAN ERROR: SQL does not apply the requested death filter."
        elif field == "cid_morte_descricao" and values:
            if "cid_morte" not in text:
                return False, (
                    "SEMANTIC PLAN ERROR: SQL does not apply the requested death-cause description "
                    "filter through CID_MORTE."
                )
            if not any(value in text for value in values):
                return False, (
                    "SEMANTIC PLAN ERROR: SQL does not apply the requested death-cause description term."
                )
        elif field == "metrica" and values:
            if "metrica" not in text or not all(value in text for value in values):
                expected = ", ".join(values)
                return False, (
                    "SEMANTIC PLAN ERROR: SQL does not apply the requested metrica "
                    f"filter ({expected})."
                )
        elif field == "instrucao_valid":
            if not re.search(r"\binstru\b[\s\S]{0,80}\bis\s+not\s+null\b", text, re.I):
                return False, "SEMANTIC PLAN ERROR: SQL does not exclude NULL INSTRU values."
            if not re.search(r"\binstru\b\"?\s*(?:!=|<>)\s*0\b", text, re.I):
                return False, "SEMANTIC PLAN ERROR: SQL does not exclude INSTRU=0."
    return True, None


def _has_unrequested_nonzero_metric_filter(inspector: SQLInspector) -> bool:
    predicate_text = " ".join(
        [
            inspector.clause_lower("WHERE"),
            inspector.clause_lower("HAVING"),
            inspector.clause_lower("QUALIFY"),
        ]
    )
    if not predicate_text:
        return False
    return bool(
        re.search(
            r"\b(?:[a-z_][\w]*\.)?(?:taxa|taxa_mortalidade|metric_value)\b\s*(?:>|>=)\s*0(?:\.0+)?\b",
            predicate_text,
            re.I,
        )
    )
