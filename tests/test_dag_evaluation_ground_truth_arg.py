import json
import sys
from types import SimpleNamespace

from evaluation.dag.tasks import (
    evaluate_questions,
    load_ground_truth,
    preflight_ground_truth,
    save_results,
)
from evaluation.runners.run_dag_evaluation import parse_arguments


def test_load_ground_truth_uses_custom_path(tmp_path):
    dataset = tmp_path / "custom_ground_truth.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "id": "GT_CUSTOM",
                    "difficulty": "hard",
                    "question": "Quantas internações existem?",
                    "query": "SELECT COUNT(*) FROM internacoes;",
                }
            ]
        ),
        encoding="utf-8",
    )

    result = load_ground_truth(ground_truth_path=str(dataset))

    assert result["ground_truth_path"] == str(dataset)
    assert result["total_count"] == 1
    assert result["difficulty_breakdown"] == {"hard": 1}
    assert result["questions"][0]["id"] == "GT_CUSTOM"


def test_load_ground_truth_normalizes_revised_schema(tmp_path):
    dataset = tmp_path / "revised_ground_truth.json"
    dataset.write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "question_id": "REV_001",
                        "difficulty": "L1",
                        "question_pt": "Quantas internações existem?",
                        "sql": "SELECT COUNT(*) FROM internacoes;",
                        "tables_used": ["internacoes"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = load_ground_truth(ground_truth_path=str(dataset))

    assert result["questions"][0]["id"] == "REV_001"
    assert result["questions"][0]["question"] == "Quantas internações existem?"
    assert result["questions"][0]["query"] == "SELECT COUNT(*) FROM internacoes;"
    assert result["questions"][0]["tables"] == ["internacoes"]


def test_run_dag_evaluation_parses_ground_truth_and_workers(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_dag_evaluation.py",
            "--ground-truth",
            "evaluation/ground_truth_v2.json",
            "--workers",
            "4",
            "--llamaindex-mode",
            "context",
            "--llamaindex-top-k-tables",
            "5",
            "--verify-llamaindex-schema-with-db",
        ],
    )

    args = parse_arguments()

    assert args.ground_truth_path == "evaluation/ground_truth_v2.json"
    assert args.max_workers == 4
    assert args.llamaindex_mode == "context"
    assert args.llamaindex_top_k_tables == 5
    assert args.verify_llamaindex_schema_with_db is True


def test_run_dag_evaluation_parses_resume_run_id(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_dag_evaluation.py",
            "--resume-run-id",
            "20260516_120000",
            "--force-rerun",
        ],
    )

    args = parse_arguments()

    assert args.resume_run_id == "20260516_120000"
    assert args.run_id is None
    assert args.resume is False
    assert args.force_rerun is True


def test_run_dag_evaluation_rejects_non_positive_workers(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_dag_evaluation.py", "--workers", "0"])

    try:
        parse_arguments()
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("parse_arguments should reject --workers 0")


class _FakeDatabase:
    def __init__(self, error=None):
        self.error = error
        self.queries = []

    def execute_query(self, sql):
        self.queries.append(sql)
        return [], self.error


def test_preflight_ground_truth_explains_gold_sql():
    db = _FakeDatabase()

    result = preflight_ground_truth(
        load_ground_truth={
            "questions": [
                {
                    "id": "GT_001",
                    "question": "Quantas internações existem?",
                    "query": "SELECT COUNT(*) FROM internacoes;",
                    "difficulty": "easy",
                }
            ]
        },
        initialize_database={"db_connection": db},
    )

    assert result["checked_count"] == 1
    assert db.queries == ["EXPLAIN SELECT COUNT(*) FROM internacoes"]


def test_preflight_ground_truth_fails_fast_on_invalid_gold_sql():
    db = _FakeDatabase(error="Catalog Error: Table internacao_procedimento does not exist")

    try:
        preflight_ground_truth(
            load_ground_truth={
                "questions": [
                    {
                        "id": "GT_BAD",
                        "question": "Pergunta",
                        "query": "SELECT COUNT(*) FROM internacao_procedimento;",
                        "difficulty": "easy",
                    }
                ]
            },
            initialize_database={"db_connection": db},
        )
    except ValueError as exc:
        assert "GT_BAD" in str(exc)
        assert "internacao_procedimento" in str(exc)
    else:
        raise AssertionError("preflight should fail on invalid gold SQL")


class _TraceDatabase:
    def execute_query_with_columns(self, sql):
        if "COUNT" in sql.upper():
            return [(42,)], ["total"], None
        return [], [], "unexpected sql"


class _FakeMetric:
    name = "Execution Accuracy (EX)"

    def evaluate(self, _context):
        return SimpleNamespace(
            score=1.0,
            is_correct=True,
            error_message=None,
            details={
                "ground_truth_rows": 1,
                "predicted_rows": 1,
                "results_match": True,
                "comparison_details": {"normalized_match": True},
            },
        )


class _FakeAgent:
    def __init__(self):
        self.calls = []

    def process_query(self, question):
        self.calls.append(question)
        return {
            "success": True,
            "sql_query": "SELECT COUNT(*) AS total FROM internacoes;",
            "results": [{"total": 42}],
            "row_count": 1,
            "response": "42",
            "metadata": {
                "phases_completed": ["query_classification", "sql_generation"],
                "latency_by_component": {
                    "query_classification": 0.1,
                    "sql_generation": 0.2,
                },
                "tool_calls": [
                    {
                        "name": "sql_db_query",
                        "success": True,
                        "execution_time": 0.01,
                    }
                ],
                "semantic_plan": {"intent": "count"},
                "semantic_validation": {"passed": True},
            },
        }


def test_evaluate_questions_writes_per_query_trace_checkpoint(tmp_path):
    output_dir = tmp_path / "dag_evaluation_test"
    agent = _FakeAgent()

    result = evaluate_questions(
        load_ground_truth={
            "questions": [
                {
                    "id": "GT_001",
                    "question": "Quantas internações existem?",
                    "query": "SELECT COUNT(*) AS total FROM internacoes;",
                    "difficulty": "easy",
                }
            ]
        },
        initialize_metrics={"metrics": [_FakeMetric()], "ex_metric": None},
        initialize_agent={"agent": agent},
        initialize_database={"db_connection": _TraceDatabase()},
        run_id="test",
        output_dir=str(output_dir),
    )

    trace_path = output_dir / "queries" / "GT_001" / "trace.json"
    assert trace_path.exists()
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["id"] == "GT_001"
    assert trace["status"] == "completed"
    assert trace["question_pt"] == "Quantas internações existem?"
    assert trace["detailed_result"]["question_id"] == "GT_001"
    assert [step["name"] for step in trace["steps"]] == [
        "evaluation_input",
        "agent.process_query",
        "workflow.query_classification",
        "workflow.sql_generation",
        "tool.sql_db_query",
        "metric.Execution Accuracy (EX)",
        "final_result",
    ]
    assert result["detailed_results"][0]["trace_path"] == str(trace_path)


def test_evaluate_questions_resume_reuses_completed_trace(tmp_path):
    output_dir = tmp_path / "dag_evaluation_test"
    agent = _FakeAgent()
    question = {
        "id": "GT_001",
        "question": "Quantas internações existem?",
        "query": "SELECT COUNT(*) AS total FROM internacoes;",
        "difficulty": "easy",
    }

    evaluate_questions(
        load_ground_truth={"questions": [question]},
        initialize_metrics={"metrics": [_FakeMetric()], "ex_metric": None},
        initialize_agent={"agent": agent},
        initialize_database={"db_connection": _TraceDatabase()},
        run_id="test",
        output_dir=str(output_dir),
    )

    resumed_agent = _FakeAgent()
    resumed = evaluate_questions(
        load_ground_truth={"questions": [question]},
        initialize_metrics={"metrics": [_FakeMetric()], "ex_metric": None},
        initialize_agent={"agent": resumed_agent},
        initialize_database={"db_connection": _TraceDatabase()},
        run_id="test",
        output_dir=str(output_dir),
        resume=True,
    )

    assert resumed_agent.calls == []
    assert resumed["resume"]["reused_count"] == 1
    assert resumed["resume"]["evaluated_count"] == 0
    assert resumed["detailed_results"][0]["question_id"] == "GT_001"
    assert resumed["metric_scores"]["Execution Accuracy (EX)"] == [1.0]


def test_save_results_writes_dag_run_folder(tmp_path):
    run_id = "20260509_123456"
    output_dir = tmp_path / f"dag_evaluation_{run_id}"

    result = save_results(
        evaluate_questions={
            "detailed_results": [
                {
                    "question_id": "GT_001",
                    "difficulty": "easy",
                    "question": "Quantas internações existem?",
                    "ground_truth_sql": "SELECT COUNT(*) AS total FROM internacoes;",
                    "predicted_sql": "SELECT COUNT(*) AS total FROM internacoes;",
                    "agent_success": True,
                    "agent_execution_time": 0.5,
                    "evaluation_source": "sql_query",
                    "stored_rows": None,
                    "agent_metadata": {
                        "tables_used": ["internacoes"],
                        "semantic_validation": {"passed": True},
                    },
                    "multi_query": {"is_multi_query": False},
                    "agent_error": None,
                    "metrics": {
                        "Execution Accuracy (EX)": {
                            "score": 1.0,
                            "is_correct": True,
                            "error": None,
                            "details": {
                                "ground_truth_rows": 1,
                                "predicted_rows": 1,
                                "results_match": True,
                                "comparison_details": {"normalized_match": True},
                            },
                        }
                    },
                }
            ],
            "agent_stats": {"success_count": 1, "failure_count": 0, "total_time": 0.5},
            "future_errors": [{"question_id": "GT_BAD", "error": "boom"}],
        },
        aggregate_results={
            "timestamp": "2026-05-09T12:34:56",
            "summary": {"total_questions": 1},
            "metrics": {
                "Execution Accuracy (EX)": {
                    "average_score": 1.0,
                    "accuracy": 1.0,
                    "perfect_matches": 1,
                    "total_evaluated": 1,
                }
            },
            "difficulty_breakdown": {"easy": {"total": 1}},
        },
        generate_report={"report_text": "report"},
        load_configuration={"llm_provider": "openai", "llm_model": "gpt-4o-mini"},
        initialize_agent={"agent_config": {"model": "gpt-4o-mini"}},
        initialize_database={"db_connection": _TraceDatabase()},
        load_ground_truth={
            "ground_truth_path": "/tmp/ground_truth.json",
            "total_count": 1,
            "difficulty_breakdown": {"hard": 1},
        },
        preflight_ground_truth={"checked_count": 1, "failed_count": 0},
        run_id=run_id,
        output_dir=str(output_dir),
        ground_truth_path="evaluation/ground_truth_v2.json",
        max_workers=4,
        llamaindex_mode="context",
        llamaindex_top_k_tables=5,
        llamaindex_index_dir=".llamaindex_schema",
        llamaindex_rebuild_index=True,
    )

    assert result["output_dir"] == str(output_dir)
    json_path = output_dir / f"dag_evaluation_{run_id}.json"
    assert json_path.exists()
    assert (output_dir / f"dag_evaluation_report_{run_id}.txt").exists()
    assert (output_dir / "trace.jsonl").exists()
    assert (output_dir / "analysis.md").exists()
    assert "outputs_path" not in result
    assert result["trace_path"] == str(output_dir / "trace.jsonl")
    assert result["analysis_path"] == str(output_dir / "analysis.md")

    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["run_context"]["ground_truth_path"] == "evaluation/ground_truth_v2.json"
    assert saved["run_context"]["max_workers"] == 4
    assert saved["run_context"]["llamaindex_mode"] == "context"
    assert saved["run_context"]["llamaindex_top_k_tables"] == 5
    assert saved["run_context"]["verify_llamaindex_schema_with_db"] is False
    assert saved["ground_truth"]["loaded_path"] == "/tmp/ground_truth.json"
    assert saved["preflight"]["checked_count"] == 1
    assert saved["evaluation_diagnostics"]["future_errors"] == [
        {"question_id": "GT_BAD", "error": "boom"}
    ]
    trace_records = [
        json.loads(line)
        for line in (output_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert trace_records[0]["id"] == "GT_001"
    assert trace_records[0]["expected_columns"] == ["total"]
    assert trace_records[0]["actual_preview_values"] == [[42]]
    assert trace_records[0]["result_match"] is True
    assert "# DAG Evaluation Analysis" in (output_dir / "analysis.md").read_text(encoding="utf-8")
