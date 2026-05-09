from evaluation.audit_hard_failures import QueryExecution, _classify


def test_hard_failure_audit_classifies_zero_gold_ablation_as_evaluation_artifact():
    result = {
        "gold_row_count": 0,
        "predicted_row_count": 0,
        "generated_sql": "SELECT 1;",
    }

    classification, notes = _classify(
        result,
        QueryExecution(success=True, row_count=2, sample=[]),
        QueryExecution(success=True, row_count=2, sample=[]),
    )

    assert classification == "evaluation_artifact"
    assert "direct gold execution returned rows" in notes


def test_hard_failure_audit_preserves_agent_sql_error_when_gold_artifact_exists():
    result = {
        "gold_row_count": 0,
        "predicted_row_count": 0,
        "generated_sql": "SELECT missing_col FROM table;",
    }

    classification, notes = _classify(
        result,
        QueryExecution(success=True, row_count=10, sample=[]),
        QueryExecution(success=False, row_count=0, sample=[], error="missing column"),
    )

    assert classification == "evaluation_artifact_and_agent_sql_error"
    assert "generated SQL failed" in notes
