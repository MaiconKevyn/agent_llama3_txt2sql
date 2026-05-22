import json
from pathlib import Path


def test_intent_generalization_corpus_has_required_fields_and_minimum_size():
    path = Path("evaluation/agent/intent_generalization_questions.jsonl")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    assert len(rows) >= 80
    required = {
        "id",
        "persona",
        "question",
        "family",
        "expected_intent",
        "expected_concepts",
        "expected_tables",
        "judge",
        "anti_overfit_family",
    }
    assert all(required.issubset(row) for row in rows)
    assert any(row["expected_intent"]["presentation"] == "chart" for row in rows)
    assert any(row["judge"] == "safe_refusal" for row in rows)
    assert any(row["family"] == "respiratory_child_deaths_last_n_years" for row in rows)
