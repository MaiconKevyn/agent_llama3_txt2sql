from src.semantic.catalog import SemanticCatalog, load_semantic_catalog
from src.semantic.catalog_schema import assert_valid_semantic_catalog, validate_semantic_catalog


def test_current_semantic_catalog_satisfies_contract_schema():
    errors = validate_semantic_catalog(load_semantic_catalog())

    assert errors == []


def test_catalog_schema_rejects_derived_metric_without_denominator_scope():
    catalog = SemanticCatalog.model_validate(
        {
            "version": 1,
            "description": "invalid catalog",
            "metrics": {
                "bad_rate": {
                    "label": "Bad rate",
                    "grain": "internacao",
                    "expression_type": "rate",
                    "numerator": "SUM(x)",
                    "denominator": "COUNT(*)",
                }
            },
            "dimensions": {},
            "macros": {},
            "rules": {},
        }
    )

    errors = validate_semantic_catalog(catalog)

    assert "metric.bad_rate: denominator_scope is required for derived metrics" in errors


def test_catalog_schema_rejects_dimension_join_without_join_path():
    catalog = SemanticCatalog.model_validate(
        {
            "version": 1,
            "description": "invalid catalog",
            "metrics": {},
            "dimensions": {
                "estado": {
                    "label": "Estado",
                    "source": "municipios.estado",
                    "grain": "internacao",
                    "joins": ["internacoes.MUNIC_RES -> municipios.CO_MUNICIPIO_6D"],
                }
            },
            "macros": {},
            "rules": {},
        }
    )

    errors = validate_semantic_catalog(catalog)

    assert "dimension.estado: join_path is required when joins are declared" in errors


def test_assert_valid_semantic_catalog_raises_on_invalid_catalog():
    catalog = SemanticCatalog.model_validate(
        {
            "version": 1,
            "description": "invalid catalog",
            "metrics": {},
            "dimensions": {},
            "macros": {},
            "rules": {"bad": {"severity": "fatal", "description": "bad"}},
        }
    )

    try:
        assert_valid_semantic_catalog(catalog)
    except ValueError as exc:
        assert "rule.bad: unsupported severity" in str(exc)
    else:
        raise AssertionError("Expected invalid catalog to raise")
