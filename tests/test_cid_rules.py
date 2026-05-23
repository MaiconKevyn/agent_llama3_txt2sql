from src.semantic.cid_rules import (
    CID_CATALOG_DIMENSION_SOURCES,
    cid_catalog_dimension_from_query,
    extract_cid_catalog_search_terms,
    extract_explicit_cid_prefix_filters,
    has_cid_catalog_lookup_context,
    has_cid_chapter_context,
    has_missing_cid_lookup_request,
    is_cid_duplicate_description_query,
)


def test_cid_catalog_dimension_sources_cover_catalog_hierarchy():
    assert CID_CATALOG_DIMENSION_SOURCES["cid_codigo"] == "cid.CID"
    assert CID_CATALOG_DIMENSION_SOURCES["cid_descricao"] == "cid.DESCRICAO"
    assert CID_CATALOG_DIMENSION_SOURCES["cid_categoria"] == "cid.DS_CATEGORIA"
    assert CID_CATALOG_DIMENSION_SOURCES["cid_grupo"] == "cid.DS_GRUPO"
    assert CID_CATALOG_DIMENSION_SOURCES["cid_capitulo"] == "cid.DS_CAPITULO"
    assert CID_CATALOG_DIMENSION_SOURCES["cid_restrsexo"] == "cid.RESTRSEXO"


def test_has_missing_cid_lookup_request_requires_primary_diagnosis_and_catalog_gap():
    assert has_missing_cid_lookup_request(
        "quantos diagnosticos principais estao fora do catalogo cid?"
    )
    assert not has_missing_cid_lookup_request("quantos codigos existem no catalogo cid?")


def test_cid_catalog_lookup_context_excludes_internacao_frequency_questions():
    assert has_cid_catalog_lookup_context("quais codigos cid relacionados a pneumonia existem?")
    assert not has_cid_catalog_lookup_context(
        "quais categorias cid foram mais frequentes em internacoes?"
    )
    assert not has_cid_catalog_lookup_context(
        "quais sao os 10 procedimentos mais comuns nas cidades do rs?"
    )


def test_cid_chapter_and_dimension_detection():
    assert has_cid_chapter_context("quais capitulos do cid existem?")
    assert has_cid_chapter_context("cid-10 capitulos")
    assert cid_catalog_dimension_from_query("quais restricoes de sexo aparecem no cid?") == (
        "cid_restrsexo"
    )
    assert cid_catalog_dimension_from_query("quais grupos do cid existem?") == "cid_grupo"
    assert cid_catalog_dimension_from_query("quais categorias do cid existem?") == ("cid_categoria")
    assert cid_catalog_dimension_from_query("quais capitulos do cid existem?") == "cid_capitulo"
    assert cid_catalog_dimension_from_query("quais descricoes do cid existem?") == ("cid_descricao")
    assert cid_catalog_dimension_from_query("quais codigos cid existem?") == "cid_codigo"


def test_explicit_cid_prefix_filter_normalizes_to_like_pattern():
    filters = extract_explicit_cid_prefix_filters("liste cids cujo codigo comeca com j18")

    assert len(filters) == 1
    assert filters[0].field == "diagnostico_principal_prefix"
    assert filters[0].operator == "LIKE"
    assert filters[0].values == ["J18%"]


def test_cid_catalog_search_terms_are_cleaned_and_deduplicated():
    assert extract_cid_catalog_search_terms(
        "quais codigos cid relacionados a pneumonia e covid?"
    ) == ["pneumonia", "covid"]


def test_duplicate_description_detection_requires_description_and_duplicate_language():
    assert is_cid_duplicate_description_query("existem descricoes cid repetidas?")
    assert not is_cid_duplicate_description_query("existem descricoes cid?")
