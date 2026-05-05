from src.semantic.data_profile import ColumnProfile, SemanticProfile
from src.semantic.planner import build_semantic_plan
from src.semantic.profile_store import SemanticProfileStore


def _profile_store() -> SemanticProfileStore:
    profile = SemanticProfile(generated_at="2026-05-05T00:00:00+00:00", catalog_version=1)
    profile.add_column(
        ColumnProfile(
            table="internacoes",
            column="DT_INTER",
            kind="temporal",
            row_count=100,
            null_count=0,
            distinct_count=30,
            min_value="2020-01-01",
            max_value="2022-12-31",
        )
    )
    profile.add_column(
        ColumnProfile(
            table="internacoes",
            column="CNES",
            kind="identifier",
            row_count=100,
            null_count=0,
            distinct_count=100,
        )
    )
    profile.add_column(
        ColumnProfile(
            table="internacoes",
            column="SEXO",
            kind="categorical",
            row_count=100,
            null_count=5,
            distinct_count=3,
            top_values=[
                {"value": "M", "frequency": 45},
                {"value": "F", "frequency": 50},
            ],
        )
    )
    return SemanticProfileStore(profile)


def test_profile_aware_planner_warns_about_temporal_filter_outside_coverage():
    plan = build_semantic_plan(
        "Qual a evolução anual da taxa de mortalidade em 2018 por estado?",
        profile_store=_profile_store(),
    )

    assert any("profile_temporal_coverage" in item for item in plan.ambiguities)
    assert any("profile_temporal_filter_out_of_range" in item for item in plan.ambiguities)


def test_profile_aware_planner_marks_high_cardinality_identifiers():
    plan = build_semantic_plan(
        "Quais são os 5 hospitais com maior custo médio de UTI por estado?",
        profile_store=_profile_store(),
    )

    assert any("profile_cardinality: hospital" in item for item in plan.ambiguities)


def test_profile_aware_planner_adds_domain_and_null_hints_for_categorical_dimension():
    plan = build_semantic_plan("Conte internações por sexo.", profile_store=_profile_store())

    assert any("profile_nulls: internacoes.SEXO" in item for item in plan.ambiguities)
    assert any("profile_domain_values: internacoes.SEXO" in item for item in plan.ambiguities)
