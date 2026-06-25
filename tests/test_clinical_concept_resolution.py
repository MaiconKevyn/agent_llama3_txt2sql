from src.agent.sql_generation import _build_deterministic_scalar_sql
from src.semantic.concept_resolver import resolve_clinical_concept
from src.semantic.planner import build_semantic_plan


def _filter_values(plan, field: str) -> list[str]:
    values: list[str] = []
    for semantic_filter in plan.filters:
        if semantic_filter.field == field:
            values.extend(str(value) for value in semantic_filter.values)
    return values


def test_resolves_respiratory_phrase_variants_to_cid_j_prefix():
    variants = [
        "causa respiratorias",
        "causas respiratorias",
        "causa respiratória",
        "causas pulmonares",
        "problema respiratorio",
        "doencas respiratorias",
    ]

    for variant in variants:
        concept = resolve_clinical_concept(variant)

        assert concept is not None, variant
        assert concept.canonical_name == "doencas respiratorias"
        assert concept.resolved_prefixes == ["J%"]


def test_resolves_generic_cancer_to_malignant_neoplasm_prefix():
    concept = resolve_clinical_concept("cancer")

    assert concept is not None
    assert concept.canonical_name == "neoplasias malignas"
    assert concept.resolved_prefixes == ["C%"]


def test_non_respiratory_clinical_phrases_do_not_resolve_to_respiratory_concept():
    for phrase in [
        "causa externa",
        "causa obstetrica",
        "doenca renal",
        "problema cardiaco",
        "causa mal definida",
    ]:
        assert resolve_clinical_concept(phrase) is None


def test_unknown_clinical_phrase_remains_description_lookup():
    plan = build_semantic_plan("quantas internacoes por doenca renal em 2021")

    assert _filter_values(plan, "diagnostico_principal_prefix") == []
    assert _filter_values(plan, "diagnostico_principal_descricao") == ["doenca renal"]


def test_respiratory_death_cause_uses_prefix_filter_instead_of_description_lookup():
    plan = build_semantic_plan(
        "me mostre o numero total de mortes por causa respiratorias em 2021"
    )

    assert _filter_values(plan, "diagnostico_principal_prefix") == ["J%"]
    assert _filter_values(plan, "diagnostico_principal_descricao") == []


def test_deterministic_sql_for_known_respiratory_concept_does_not_use_raw_description():
    plan = build_semantic_plan("quantas internacoes por causa respiratorias em 2021")

    sql = _build_deterministic_scalar_sql(plan)

    assert sql is not None
    assert "LIKE 'J%'" in sql
    assert "respiratorias" not in sql.lower()
