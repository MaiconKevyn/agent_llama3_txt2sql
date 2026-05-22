import json
from pathlib import Path

from evaluation.runners.run_chart_agent_prod_eval import evaluate_cases, load_cases, select_cases


def _load_prod_cases() -> list[dict]:
    path = Path("evaluation/visualization/chart_agent_prod_cases.jsonl")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_chart_agent_prod_cases_are_valid_jsonl():
    rows = _load_prod_cases()

    assert len(rows) >= 80
    assert rows[0]["id"] == "PROD_MORT_LOC_001"
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))
    assert "PROD_MORT_LOC_001" in ids

    for row in rows:
        assert row["query"].strip()
        assert row["expected"]["requested"] is True
        assert row["expected"]["chart_types"]
        assert row["tags"]


def test_chart_agent_prod_cases_cover_required_families():
    ids = {row["id"] for row in _load_prod_cases()}

    for family in [
        "PROD_MORT_LOC",
        "PROD_TIME",
        "PROD_DEMO",
        "PROD_CID",
        "PROD_PROC",
        "PROD_FIN",
        "PROD_SOCIO",
        "PROD_AUTO",
    ]:
        family_ids = [case_id for case_id in ids if case_id.startswith(family)]
        assert len(family_ids) >= 10, family


def test_chart_agent_prod_eval_runner_scores_static_cases():
    rows = select_cases(load_cases(), only="PROD_MORT_LOC", limit=3)

    report = evaluate_cases(rows)

    assert set(report["metrics"]) == {
        "success_rate",
        "no_raw_internal_error",
        "chart_contract_validity",
        "sql_invariant_validity",
        "semantic_dimension_validity",
    }
    assert report["metrics"]["no_raw_internal_error"] == 1.0
    assert report["metrics"]["sql_invariant_validity"] == 1.0
    assert report["metrics"]["semantic_dimension_validity"] == 1.0
    assert len(report["details"]) == 3


def test_chart_agent_prod_eval_selection_supports_shuffle_seed():
    rows = load_cases()

    first = [row["id"] for row in select_cases(rows, only="PROD_TIME", limit=4, shuffle=True, seed=123)]
    second = [row["id"] for row in select_cases(rows, only="PROD_TIME", limit=4, shuffle=True, seed=123)]
    unshuffled = [row["id"] for row in select_cases(rows, only="PROD_TIME", limit=4)]

    assert first == second
    assert first != unshuffled
