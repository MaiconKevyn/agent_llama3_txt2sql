import time
from datetime import datetime

from src.interfaces.api.main import _build_query_response


def test_query_response_includes_optional_debug_payload():
    debug = {
        "enabled": True,
        "steps": [
            {
                "index": 1,
                "node": "generate_sql",
                "title": "SQL Generation",
                "status": "completed",
                "data": {"generated_sql": "SELECT 1"},
            }
        ],
        "summary": {"nodes_executed": 1},
    }

    response = _build_query_response(
        {
            "success": True,
            "response": "ok",
            "sql_query": "SELECT 1",
            "debug": debug,
            "metadata": {"session_id": "s1"},
        },
        started_at=time.time(),
        session_id=None,
    )

    assert response.debug == debug


def test_build_debug_payload_extracts_ordered_node_steps():
    from src.interfaces.api.main import _build_debug_payload_from_updates

    debug = _build_debug_payload_from_updates(
        [
            {
                "classify_query": {
                    "query_route": "database",
                    "classification": {
                        "route": "database",
                        "confidence_score": 0.9,
                        "requires_tools": True,
                    },
                }
            },
            {
                "generate_sql": {
                    "generated_sql": "SELECT COUNT(*) AS total FROM internacoes;",
                    "selected_tables": ["internacoes"],
                }
            },
            {
                "execute_sql": {
                    "sql_execution_result": {
                        "success": True,
                        "row_count": 1,
                        "results": [{"total": 10}],
                    }
                }
            },
            {
                "generate_response": {
                    "final_response": "Foram encontradas 10 internações.",
                    "success": True,
                }
            },
        ]
    )

    assert debug["enabled"] is True
    assert [step["node"] for step in debug["steps"]] == [
        "classify_query",
        "generate_sql",
        "execute_sql",
        "generate_response",
    ]
    assert debug["steps"][1]["data"]["generated_sql"] == (
        "SELECT COUNT(*) AS total FROM internacoes;"
    )
    assert debug["steps"][2]["data"]["row_count"] == 1
    assert debug["summary"]["nodes_executed"] == 4


def test_build_debug_payload_marks_stream_error_as_error_step():
    from src.interfaces.api.main import _build_debug_payload_from_updates

    debug = _build_debug_payload_from_updates(
        [
            {"classify_query": {"query_route": "database", "success": False}},
            {"error": "Workflow streaming failed: boom"},
        ]
    )

    assert debug["steps"][0]["status"] == "completed"
    assert debug["steps"][-1]["node"] == "error"
    assert debug["steps"][-1]["status"] == "error"
    assert debug["steps"][-1]["data"]["current_error"] == "Workflow streaming failed: boom"


def test_build_debug_result_preserves_trace_when_streaming_fails_before_final_state():
    from src.interfaces.api.main import _build_debug_result_from_updates

    result = _build_debug_result_from_updates(
        "pergunta com erro",
        [{"classify_query": {"query_route": "database"}}, {"error": "boom"}],
    )

    assert result["success"] is False
    assert result["question"] == "pergunta com erro"
    assert result["error_message"] == "boom"
    assert result["response"] == "Não foi possível processar sua consulta: boom"
    assert result["debug"]["steps"][-1]["status"] == "error"


def test_debug_query_response_keeps_chart_payload(monkeypatch):
    import asyncio

    from src.agent.state_helpers import create_initial_messages_state
    from src.interfaces.api import main as api_main
    from src.visualization.schema import ChartPlan, VisualizationIntent

    state = create_initial_messages_state(
        user_query="gere um grafico da evolucao de mortes totais nos ultimos 5 anos",
        session_id="debug-chart",
        visualization_intent={
            "requested": True,
            "source": "explicit_current_query",
            "uses_last_result": False,
            "chart_hint": "auto",
            "reason": "Usuario pediu explicitamente visualizacao em grafico",
        },
        chart_plan={
            "requested": True,
            "chart_type": "line",
            "metric": "total_mortes",
            "x_dimension": "ano",
            "y_column": "total_mortes",
            "expected_result_shape": "time_metric",
            "required_columns": ["ano", "total_mortes"],
        },
    )
    state["success"] = True
    state["timestamp"] = datetime.now()
    state["validated_sql"] = "SELECT 2023 AS ano, 10 AS total_mortes"
    state["final_response"] = "ok"
    state["final_result_rows"] = [{"ano": 2023, "total_mortes": 10}]

    class FakeOrchestrator:
        def process_query(self, query, session_id=None, streaming=False):
            assert streaming is True
            return [{"generate_response": state}]

        def _attach_visualization_if_requested(
            self,
            *,
            result,
            user_query,
            visualization_intent,
            chart_plan=None,
        ):
            assert isinstance(visualization_intent, VisualizationIntent)
            assert isinstance(chart_plan, ChartPlan)
            result["chart"] = {
                "requested": True,
                "source": "explicit_current_query",
                "uses_last_result": False,
                "chart_hint": "auto",
                "spec": {
                    "chartable": True,
                    "chart_type": "line",
                    "x": "ano",
                    "y": "total_mortes",
                    "data": [{"ano": 2023, "total_mortes": 10}],
                },
                "echarts": {"series": [{"type": "line"}]},
                "reason": "Usuario pediu explicitamente visualizacao em grafico",
            }
            return result

    monkeypatch.setattr(api_main, "_orchestrator", FakeOrchestrator())

    response = asyncio.run(
        api_main.process_query(
            api_main.QueryRequest(
                query="gere um grafico da evolucao de mortes totais nos ultimos 5 anos",
                session_id="debug-chart",
                debug=True,
            )
        )
    )

    assert response.success is True
    assert response.debug is not None
    assert response.chart["requested"] is True
    assert response.chart["spec"]["chart_type"] == "line"


def test_process_query_exception_hides_raw_internal_error(monkeypatch):
    import asyncio

    from src.interfaces.api import main as api_main

    class BrokenOrchestrator:
        def process_query(self, *args, **kwargs):
            raise RuntimeError("SEMANTIC PLAN ERROR: raw internal detail")

    monkeypatch.setattr(api_main, "_orchestrator", BrokenOrchestrator())

    response = asyncio.run(
        api_main.process_query(api_main.QueryRequest(query="gere um grafico", session_id="s1"))
    )

    assert response.success is False
    assert "SEMANTIC PLAN ERROR" not in response.answer
    assert "raw internal detail" not in response.answer
    assert response.metadata["error_type"] == "RuntimeError"
