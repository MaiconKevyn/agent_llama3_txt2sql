from src.semantic.data_profile import ColumnProfileSpec
from src.semantic.profile_runner import redact_database_url, run_profile_specs
from src.semantic.profile_store import (
    load_profile_store,
    load_semantic_profile,
    save_semantic_profile,
)


def test_profile_runner_builds_persistent_profile_from_executor(tmp_path):
    specs = [
        ColumnProfileSpec(table="internacoes", column="MORTE", kind="categorical", top_k=2),
        ColumnProfileSpec(table="internacoes", column="DT_INTER", kind="temporal"),
    ]

    def execute_sql(sql: str):
        if 'FROM "internacoes"' in sql and 'GROUP BY "MORTE"' in sql:
            return [{"value": True, "frequency": 7}, {"value": False, "frequency": 3}]
        if 'MIN("DT_INTER")' in sql:
            return [
                {
                    "row_count": 10,
                    "null_count": 0,
                    "distinct_count": 9,
                    "min_value": "2020-01-01",
                    "max_value": "2022-12-31",
                }
            ]
        return [{"row_count": 10, "null_count": 1, "distinct_count": 2}]

    profile = run_profile_specs(
        specs,
        execute_sql,
        generated_at="2026-05-05T00:00:00+00:00",
        source="postgresql://user:***@localhost/db",
        catalog_version=1,
    )
    output_path = save_semantic_profile(profile, tmp_path / "profile.json")
    loaded = load_semantic_profile(output_path)

    assert loaded is not None
    assert loaded.catalog_version == 1
    assert loaded.tables["internacoes"].row_count == 10
    mortality = loaded.tables["internacoes"].columns["MORTE"]
    assert mortality.null_count == 1
    assert mortality.top_values[0] == {"value": True, "frequency": 7}
    temporal = loaded.tables["internacoes"].columns["DT_INTER"]
    assert temporal.min_value == "2020-01-01"
    assert temporal.max_value == "2022-12-31"


def test_redact_database_url_removes_password():
    redacted = redact_database_url("postgresql://user:secret@localhost:5432/sus")

    assert redacted == "postgresql://user:***@localhost:5432/sus"
    assert "secret" not in redacted


def test_profile_store_loads_empty_when_profile_file_is_missing(tmp_path):
    store = load_profile_store(tmp_path / "missing.json")

    assert store.profile.tables == {}
