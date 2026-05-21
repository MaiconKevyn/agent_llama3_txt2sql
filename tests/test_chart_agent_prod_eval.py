import json
from pathlib import Path


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
