import pytest

from src.semantic.domain_resolvers import resolve_clinical_domain, resolve_population_group


@pytest.mark.parametrize(
    "question",
    [
        "mortes de crianca por causas respiratorias",
        "obitos pediatricos por doencas respiratorias",
        "internacoes pediatricas",
        "quantas criancas foram internadas",
    ],
)
def test_population_resolver_maps_child_terms_to_under_18_policy(question):
    filters = resolve_population_group(question)

    assert any(
        filter_.field == "idade" and filter_.operator == "<" and filter_.values == ["18"]
        for filter_ in filters
    )


def test_population_resolver_preserves_explicit_child_age_threshold():
    filters = resolve_population_group("grafico de respiratorias em menores de 5 anos")

    assert any(
        filter_.field == "idade" and filter_.operator == "<" and filter_.values == ["5"]
        for filter_ in filters
    )
    assert not any(
        filter_.field == "idade" and filter_.operator == "<" and filter_.values == ["18"]
        for filter_ in filters
    )


@pytest.mark.parametrize(
    "question",
    [
        "causas respiratorias",
        "doencas respiratorias",
        "problemas respiratorios",
        "condicoes respiratorias",
    ],
)
def test_clinical_resolver_maps_respiratory_variants_to_cid_j(question):
    filters = resolve_clinical_domain(question)

    assert any(
        filter_.field == "diagnostico_principal_prefix" and filter_.values == ["J%"]
        for filter_ in filters
    )


def test_clinical_resolver_does_not_map_external_causes_to_respiratory():
    filters = resolve_clinical_domain("mortes por causas externas em criancas")

    assert not any(
        filter_.field == "diagnostico_principal_prefix" and filter_.values == ["J%"]
        for filter_ in filters
    )
