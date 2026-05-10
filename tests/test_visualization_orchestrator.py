from src.agent.orchestrator import LangGraphOrchestrator
from src.visualization.intent import detect_visualization_intent


class DummyLogger:
    def warning(self, message, extra=None):
        self.last_warning = (message, extra)


def _orchestrator_without_runtime():
    orchestrator = object.__new__(LangGraphOrchestrator)
    orchestrator.logger = DummyLogger()
    return orchestrator


def test_attach_visualization_skips_when_not_requested():
    orchestrator = _orchestrator_without_runtime()
    result = {
        "success": True,
        "sql_query": "SELECT 1 AS total",
        "results": [{"result": (1,)}],
        "row_count": 1,
        "metadata": {},
    }

    updated = orchestrator._attach_visualization_if_requested(
        result=result,
        user_query="Quantas internacoes existem?",
        visualization_intent=detect_visualization_intent("Quantas internacoes existem?"),
    )

    assert updated["chart"] is None
    assert updated["metadata"]["visualization_intent"]["requested"] is False


def test_attach_visualization_builds_chart_when_requested():
    orchestrator = _orchestrator_without_runtime()
    result = {
        "success": True,
        "sql_query": (
            'SELECT mu."nome" AS municipio, COUNT(*) AS total_internacoes '
            'FROM internacoes i GROUP BY mu."nome"'
        ),
        "results": [{"result": ("Porto Alegre", 10)}],
        "row_count": 1,
        "metadata": {},
    }

    updated = orchestrator._attach_visualization_if_requested(
        result=result,
        user_query="Gere um grafico de barras",
        visualization_intent=detect_visualization_intent("Gere um grafico de barras"),
    )

    assert updated["chart"]["requested"] is True
    assert updated["chart"]["spec"]["chart_type"] == "bar"
    assert updated["chart"]["spec"]["x"] == "municipio"
    assert updated["chart"]["spec"]["y"] == "total_internacoes"
    assert updated["chart"]["echarts"]["series"][0]["type"] == "bar"


def test_followup_chart_result_uses_cached_session_result():
    orchestrator = _orchestrator_without_runtime()
    cached = {
        "sql_query": "SELECT ano, COUNT(*) AS total FROM internacoes GROUP BY ano",
        "results": [{"result": (2022, 10)}, {"result": (2023, 12)}],
        "row_count": 2,
        "metadata": {},
    }

    result = orchestrator._build_followup_chart_result(
        user_query="gere um grafico disso",
        session_id="s1",
        visualization_intent=detect_visualization_intent("gere um grafico disso"),
        cached_result=cached,
        started_at=0,
    )

    assert result["success"] is True
    assert result["chart"]["requested"] is True
    assert result["chart"]["uses_last_result"] is True
    assert result["results"] == cached["results"]
