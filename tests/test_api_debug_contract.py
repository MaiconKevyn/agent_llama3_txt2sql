import asyncio
import time

from src.interfaces.api.main import _build_query_response


def test_query_response_includes_optional_debug_payload():
    debug = {
        "enabled": True,
        "steps": [
            {
                "index": 1,
                "node": "simple_agent",
                "title": "Simple Agent",
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


def test_build_debug_result_uses_simple_agent_stream_update():
    from src.interfaces.api.main import _build_debug_result_from_updates

    result = _build_debug_result_from_updates(
        "quantas internacoes?",
        [
            {
                "simple_agent": {
                    "user_query": "quantas internacoes?",
                    "simple_result": {
                        "success": True,
                        "question": "quantas internacoes?",
                        "sql_query": "SELECT COUNT(*) FROM internacoes;",
                        "results": [{"count": 10}],
                        "row_count": 1,
                        "response": "Foram encontradas 10 internacoes.",
                        "metadata": {"session_id": "s1"},
                    },
                    "current_error": None,
                }
            }
        ],
    )

    assert result["success"] is True
    assert result["sql_query"] == "SELECT COUNT(*) FROM internacoes;"
    assert result["debug"]["steps"][0]["node"] == "simple_agent"


def test_build_debug_result_preserves_trace_when_streaming_fails():
    from src.interfaces.api.main import _build_debug_result_from_updates

    result = _build_debug_result_from_updates("pergunta com erro", [{"error": "boom"}])

    assert result["success"] is False
    assert result["question"] == "pergunta com erro"
    assert result["error_message"] == "boom"
    assert result["response"] == "Nao foi possivel processar sua consulta: boom"
    assert result["debug"]["steps"][-1]["status"] == "error"


def test_process_query_exception_hides_raw_internal_error(monkeypatch):
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
