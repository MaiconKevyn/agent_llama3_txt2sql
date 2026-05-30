"""Tests for mlflow_tracker — uses a local file-store, no mock needed."""
import pytest


def _make_result(success: bool = True, execution_time: float = 1.5) -> dict:
    return {
        "success": success,
        "execution_time": execution_time,
        "row_count": 3,
        "metadata": {
            "workflow_metrics": {"retry_count": 0, "error_count": 0},
        },
    }


class TestLogQueryRunNoOp:
    """When MLFLOW_TRACKING_URI is unset, log_query_run must be a silent no-op."""

    def test_noop_when_tracking_uri_missing(self, monkeypatch):
        monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
        # Re-import so the module-level _TRACKING_URI is re-evaluated
        import src.agent.mlflow_tracker as tracker_mod
        monkeypatch.setattr(tracker_mod, "_TRACKING_URI", "")

        # Must not raise
        tracker_mod.log_query_run(
            result=_make_result(),
            session_id="s1",
            model="gpt-4o-mini",
            environment="testing",
            query="Quantas internações?",
        )


class TestLogQueryRunWithMLflow:
    """When MLflow is available and MLFLOW_TRACKING_URI is set, runs are logged."""

    def test_logs_metrics_to_local_store(self, tmp_path, monkeypatch):
        pytest.importorskip("mlflow")

        import mlflow

        import src.agent.mlflow_tracker as tracker_mod

        tracking_uri = (tmp_path / "mlruns").as_uri()
        monkeypatch.setattr(tracker_mod, "_TRACKING_URI", tracking_uri)
        monkeypatch.setattr(tracker_mod, "_mlflow_available", True)

        tracker_mod.log_query_run(
            result=_make_result(success=True, execution_time=2.3),
            session_id="test-session",
            model="gpt-4o-mini",
            environment="testing",
            query="Quantas internações em 2020?",
        )

        mlflow.set_tracking_uri(tracking_uri)
        client = mlflow.tracking.MlflowClient()
        experiments = client.search_experiments()
        assert experiments, "No experiments found"

        runs = client.search_runs(
            experiment_ids=[e.experiment_id for e in experiments],
        )
        assert runs, "No runs logged"
        run = runs[0]
        assert run.data.metrics["success"] == 1.0
        assert run.data.metrics["execution_time_s"] == pytest.approx(2.3, abs=0.01)
        assert run.data.metrics["row_count"] == 3.0


class TestLogAblationRun:
    def test_ablation_run_logs_ex_metrics(self, tmp_path, monkeypatch):
        pytest.importorskip("mlflow")

        import mlflow

        import src.agent.mlflow_tracker as tracker_mod

        tracking_uri = (tmp_path / "mlruns").as_uri()
        monkeypatch.setattr(tracker_mod, "_TRACKING_URI", tracking_uri)
        monkeypatch.setattr(tracker_mod, "_mlflow_available", True)

        tracker_mod.log_ablation_run(
            variant_id="V2",
            variant_name="no_cot_reasoning",
            flags={"disable_cot_reasoning": True},
            ex_overall=0.875,
            ex_by_tier={"easy": 1.0, "medium": 0.9, "hard": 0.75},
            delta_ex_pp=-5.8,
            mcnemar_chi2=2.5,
            mcnemar_p=0.114,
            n_queries=40,
            git_sha="abc1234",
            model_id="gpt-4o-mini",
            results_csv_path=None,
            total_tokens=12500,
            total_cost_usd=0.0023,
            avg_latency_s=7.5,
            p50_latency_s=7.0,
            p95_latency_s=12.5,
        )

        mlflow.set_tracking_uri(tracking_uri)
        client = mlflow.tracking.MlflowClient()
        runs = client.search_runs(
            experiment_ids=[e.experiment_id for e in client.search_experiments()],
        )
        assert runs
        run = runs[0]
        assert run.data.metrics["ex_overall"] == pytest.approx(0.875)
        assert run.data.metrics["delta_ex_pp"] == pytest.approx(-5.8)
        assert run.data.metrics["total_tokens"] == pytest.approx(12500)
        assert run.data.metrics["total_cost_usd"] == pytest.approx(0.0023)
        assert run.data.metrics["avg_latency_s"] == pytest.approx(7.5)
        assert run.data.metrics["p95_latency_s"] == pytest.approx(12.5)
        assert run.data.tags["variant_id"] == "V2"


class TestQueryCostTracker:
    def test_noop_when_cost_tracking_disabled(self, monkeypatch):
        from src.agent.cost_tracker import QueryCostTracker

        monkeypatch.delenv("ENABLE_LANGCHAIN_COST_TRACKING", raising=False)
        with QueryCostTracker() as tracker:
            pass
        d = tracker.as_dict()
        assert d["total_tokens"] == 0
        assert d["total_cost_usd"] == 0.0

    def test_returns_zeroed_dict_structure(self):
        from src.agent.cost_tracker import QueryCostTracker
        with QueryCostTracker() as tracker:
            pass
        d = tracker.as_dict()
        assert set(d.keys()) == {
            "prompt_tokens", "completion_tokens",
            "total_tokens", "total_cost_usd", "successful_requests",
        }
