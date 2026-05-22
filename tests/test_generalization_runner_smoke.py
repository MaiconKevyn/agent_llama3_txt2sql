from types import SimpleNamespace

from evaluation.agent.run_generalization_exhaustion import (
    evaluate_response,
    run_items,
    select_questions,
    summarize_items,
)


def test_summarize_items_counts_statuses_and_root_causes():
    payload = [
        {"status": "passed", "root_cause": None, "severity": None},
        {"status": "failed", "root_cause": "denominator_error", "severity": "high"},
        {
            "status": "failed",
            "root_cause": "unsupported_schema_detection",
            "severity": "critical",
        },
    ]

    summary = summarize_items(payload)

    assert summary["status_counts"] == {"passed": 1, "failed": 2}
    assert summary["root_cause_counts"]["denominator_error"] == 1
    assert summary["severity_counts"]["critical"] == 1


def test_evaluate_response_compares_reference_and_agent_sql_rows():
    question = SimpleNamespace(
        expected_behavior="answer_with_sql",
        reference_sql="SELECT expected",
        judge={"required_columns": ["uf", "total"], "tolerance": 0.0},
    )

    def fake_executor(sql: str):
        if sql == "SELECT expected":
            return [{"uf": "MA", "total": 10}]
        if sql == "SELECT actual":
            return [{"uf": "MA", "total": 10}]
        raise AssertionError(sql)

    result = evaluate_response(
        question,
        {"success": True, "response": "ok", "sql_query": "SELECT actual"},
        sql_executor=fake_executor,
    )

    assert result["passed"] is True
    assert result["judge"]["type"] == "result_equivalence"


def test_evaluate_response_fails_when_agent_sql_is_missing():
    question = SimpleNamespace(
        expected_behavior="answer_with_sql",
        reference_sql="SELECT expected",
        judge={"required_columns": ["uf", "total"], "tolerance": 0.0},
    )

    result = evaluate_response(question, {"success": True, "response": "ok"}, sql_executor=lambda _: [])

    assert result["passed"] is False
    assert "missing_agent_sql" in result["judge"]["missing"]


def test_run_items_dry_run_uses_corpus_without_live_agent():
    items = run_items(run_id="test_run", limit=2, dry_run=True)

    assert [item["status"] for item in items] == ["dry_run", "dry_run"]
    assert items[0]["id"] == "GEN001"


def test_select_questions_supports_offset_category_behavior_and_ids():
    by_slice = select_questions(
        limit=2,
        offset=5,
        category="volume_temporal",
        behavior="answer_with_sql",
        ids=None,
    )
    by_ids = select_questions(
        limit=None,
        offset=0,
        category=None,
        behavior=None,
        ids=["GEN010", "GEN001"],
    )

    assert [item.id for item in by_slice] == ["GEN006", "GEN007"]
    assert [item.id for item in by_ids] == ["GEN001", "GEN010"]


def test_select_questions_rejects_unknown_ids():
    try:
        select_questions(
            limit=None,
            offset=0,
            category=None,
            behavior=None,
            ids=["GEN9999"],
        )
    except ValueError as exc:
        assert "GEN9999" in str(exc)
    else:
        raise AssertionError("Expected unknown id to raise")
