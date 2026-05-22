import json
from pathlib import Path


def _load_jsonl(path: str):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def test_cid_investigation_files_exist():
    root = Path("evaluation/cid_investigation")
    assert (root / "README.md").exists()
    assert (root / "build_cid_baseline.py").exists()
    assert (root / "results" / ".gitkeep").exists()


def test_cid_baseline_script_documents_required_sql_contracts():
    source = Path("evaluation/cid_investigation/build_cid_baseline.py").read_text()
    assert "COUNT(DISTINCT CID)" in source
    assert "DS_CAPITULO" in source
    assert "DS_GRUPO" in source
    assert "DS_CATEGORIA" in source
    assert "DIAG_PRINC = c.CID" in source


def test_cid_probe_cases_have_required_coverage():
    cases = _load_jsonl("evaluation/cid_investigation/cid_probe_cases.jsonl")
    assert len(cases) >= 80
    focuses = {case["focus"] for case in cases}
    assert "cid_structure" in focuses
    assert "cid_lookup" in focuses
    assert "disease_resolution" in focuses
    assert "cid_join_aggregation" in focuses
    assert "cid_join_disease_family" in focuses
    assert "ambiguity" in focuses


def test_cid_probe_cases_never_target_dbt_audit_tables():
    cases = _load_jsonl("evaluation/cid_investigation/cid_probe_cases.jsonl")
    for case in cases:
        required = case.get("required_tables", [])
        forbidden = case.get("forbidden_tables", [])
        assert all("dbt" not in table for table in required)
        assert "main_dbt_test__audit" in forbidden or case["focus"] != "cid_structure"


def test_cid_gold_sql_uses_only_allowed_cid_join_for_business_questions():
    gold = _load_jsonl("evaluation/cid_investigation/cid_gold_sql.jsonl")
    business_join_cases = [item for item in gold if "internacoes" in item.get("required_tables", [])]
    assert business_join_cases
    for item in business_join_cases:
        sql = item["sql"]
        assert "DIAG_PRINC" in sql
        assert "DIAG_SECUN" not in sql
        assert "CID_MORTE" not in sql


def test_cid_agent_eval_runner_has_required_outputs():
    source = Path("evaluation/cid_investigation/run_cid_agent_eval.py").read_text()
    assert "cid_probe_cases.jsonl" in source
    assert "selected_tables" in source
    assert "generated_sql" in source
    assert "response_text" in source
    assert "failure_category" in source


def test_cid_failure_taxonomy_contains_required_categories():
    taxonomy = Path("evaluation/cid_investigation/failure_taxonomy.yml").read_text()
    for category in [
        "wrong_table_selection",
        "wrong_column_selection",
        "disease_resolution_error",
        "under_aggregation",
        "over_aggregation",
        "unsafe_join",
        "missing_join",
        "wrong_metric_grain",
        "lexical_normalization_gap",
        "sql_runtime_error",
        "response_grounding_gap",
    ]:
        assert category in taxonomy


def test_cid_scorer_checks_join_and_table_requirements():
    source = Path("evaluation/cid_investigation/score_cid_agent_eval.py").read_text()
    assert "required_tables" in source
    assert "required_join" in source
    assert "DIAG_PRINC" in source
    assert "DIAG_SECUN" in source
    assert "CID_MORTE" in source
