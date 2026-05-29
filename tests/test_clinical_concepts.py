from src.semantic.concept_resolver import resolve_clinical_concept
from src.semantic.concepts.clinical_concepts import (
    CLINICAL_CONCEPTS_VERSION,
    load_clinical_concepts,
)


def test_resolve_covid_returns_versioned_codes():
    concept = resolve_clinical_concept("covid")

    assert concept is not None
    assert concept.version == CLINICAL_CONCEPTS_VERSION
    assert concept.source == CLINICAL_CONCEPTS_VERSION
    assert concept.resolved_codes == ["B342", "B972"]
    assert concept.caveats


def test_versioned_catalog_covers_required_clinical_concepts():
    concepts = {concept.concept_id: concept for concept in load_clinical_concepts()}

    assert {
        "covid",
        "pneumonia",
        "dengue",
        "diabetes",
        "neoplasias",
        "doencas_cardiovasculares",
        "infarto_agudo_miocardio",
        "hipertensao",
    } <= set(concepts)


def test_resolve_pneumonia_and_hypertension_from_catalog():
    pneumonia = resolve_clinical_concept("internacoes por pneumonia")
    hypertension = resolve_clinical_concept("internacoes por hipertensao")

    assert pneumonia is not None
    assert pneumonia.resolved_prefixes == ["J12%", "J13%", "J14%", "J15%", "J16%", "J17%", "J18%"]
    assert hypertension is not None
    assert hypertension.resolved_prefixes == ["I10%", "I11%", "I12%", "I13%", "I15%"]


def test_resolve_infarction_and_unspecified_stroke_from_catalog():
    infarction = resolve_clinical_concept("internacoes por infarto agudo do miocardio")
    unspecified_stroke = resolve_clinical_concept(
        "internacoes por acidente vascular cerebral inespecifico"
    )

    assert infarction is not None
    assert infarction.resolved_prefixes == ["I21%"]
    assert unspecified_stroke is not None
    assert unspecified_stroke.resolved_prefixes == ["I64%"]


def test_unknown_clinical_concept_does_not_invent_cid_filters():
    concept = resolve_clinical_concept("doenca inventada sem catalogo")

    assert concept is None
