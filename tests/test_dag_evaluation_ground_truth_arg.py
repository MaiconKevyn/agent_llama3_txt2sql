import json
import sys

from evaluation.dag.tasks import load_ground_truth
from evaluation.dag.tasks import save_results
import evaluation.dag.tasks as dag_tasks
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
        ],
    )

    args = parse_arguments()

    assert args.ground_truth_path == "evaluation/ground_truth_v2.json"
    assert args.max_workers == 4


def test_run_dag_evaluation_rejects_non_positive_workers(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_dag_evaluation.py", "--workers", "0"])

    try:
        parse_arguments()
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("parse_arguments should reject --workers 0")


def test_save_results_writes_dag_run_folder(monkeypatch, tmp_path):
    run_id = "20260509_123456"
    output_dir = tmp_path / f"dag_evaluation_{run_id}"

    def fake_outputs_file(*, output_path, **_kwargs):
        output_path.write_text("outputs", encoding="utf-8")

    monkeypatch.setattr(dag_tasks, "_generate_execution_outputs_file", fake_outputs_file)

    result = save_results(
        evaluate_questions={"detailed_results": []},
        aggregate_results={
            "timestamp": "2026-05-09T12:34:56",
            "summary": {"total_questions": 0},
            "metrics": {},
            "difficulty_breakdown": {},
        },
        generate_report={"report_text": "report"},
        load_configuration={"llm_provider": "openai", "llm_model": "gpt-4o-mini"},
        initialize_agent={"agent_config": {"model": "gpt-4o-mini"}},
        initialize_database={"db_connection": object()},
        run_id=run_id,
        output_dir=str(output_dir),
    )

    assert result["output_dir"] == str(output_dir)
    assert (output_dir / f"dag_evaluation_{run_id}.json").exists()
    assert (output_dir / f"dag_evaluation_report_{run_id}.txt").exists()
    assert (output_dir / f"dag_execution_outputs_{run_id}.txt").exists()
