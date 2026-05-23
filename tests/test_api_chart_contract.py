import time

from src.interfaces.api.main import _build_query_response


def test_query_response_includes_optional_chart_payload():
    chart = {
        "requested": True,
        "source": "explicit_current_query",
        "uses_last_result": False,
        "chart_hint": "bar",
        "spec": {"chartable": True, "chart_type": "bar", "x": "municipio", "y": "total"},
    }

    response = _build_query_response(
        {
            "success": True,
            "response": "ok",
            "sql_query": "SELECT 1",
            "chart": chart,
            "metadata": {"session_id": "s1"},
        },
        started_at=time.time(),
        session_id=None,
    )

    assert response.chart == chart
    assert response.session_id == "s1"


def test_query_response_hides_raw_internal_planning_error():
    response = _build_query_response(
        {
            "success": False,
            "response": (
                "Não foi possível processar sua consulta: SEMANTIC PLAN ERROR: "
                "internal validator details"
            ),
            "metadata": {"session_id": "s1"},
        },
        started_at=time.time(),
        session_id=None,
    )

    assert response.success is False
    assert "SEMANTIC PLAN ERROR" not in response.answer
    assert "internal validator details" not in response.answer
    assert "segurança" in response.answer


def test_query_request_accepts_cached_result_chart_flag() -> None:
    from src.interfaces.api.main import QueryRequest

    request = QueryRequest(
        query="Gere um grafico dessa resposta usando os dados ja retornados.",
        session_id="s1",
        chart_from_last_result=True,
    )

    assert request.chart_from_last_result is True
