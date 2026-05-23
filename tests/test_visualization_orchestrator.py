from src.agent.orchestrator import LangGraphOrchestrator
from src.visualization.intent import detect_visualization_intent


class DummyLogger:
    def info(self, message, extra=None):
        self.last_info = (message, extra)

    def error(self, message, extra=None):
        self.last_error = (message, extra)

    def warning(self, message, extra=None):
        self.last_warning = (message, extra)


class DummyMetrics:
    def begin_query(self):
        return 1


class DummyModel:
    provider = "openai"
    model_name = "test-model"


def _orchestrator_without_runtime():
    orchestrator = object.__new__(LangGraphOrchestrator)
    orchestrator.logger = DummyLogger()
    orchestrator._metrics = DummyMetrics()
    orchestrator._current_model = DummyModel()
    orchestrator._last_result_by_session = {}
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
            'SELECT mu."NO_MUNICIPIO" AS municipio, COUNT(*) AS total_internacoes '
            'FROM internacoes i GROUP BY mu."NO_MUNICIPIO"'
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


def test_attach_visualization_appends_unfilled_category_notice_to_response():
    orchestrator = _orchestrator_without_runtime()
    result = {
        "success": True,
        "response": "1. Nao preenchido: 488.330\n2. Insuf respirat aguda: 24.784",
        "sql_query": (
            'SELECT c."DESCRICAO" AS causa_morte, COUNT(*) AS total_mortes '
            'FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" GROUP BY causa_morte'
        ),
        "results": [
            {"result": ("Nao preenchido", 488330)},
            {"result": ("Insuf respirat aguda", 24784)},
        ],
        "row_count": 2,
        "metadata": {},
    }

    updated = orchestrator._attach_visualization_if_requested(
        result=result,
        user_query="gere um gráfico de pizza com as 6 principais causas de morte",
        visualization_intent=detect_visualization_intent(
            "gere um gráfico de pizza com as 6 principais causas de morte"
        ),
    )

    assert updated["chart"]["spec"]["data"] == [
        {"causa_morte": "Insuf respirat aguda", "total_mortes": 24784}
    ]
    assert "desconsidera registros sem causa" in updated["response"].lower()
    assert "nao preenchido" not in updated["response"].lower()


def test_attach_visualization_preserves_coherent_response_when_adding_unfilled_notice():
    orchestrator = _orchestrator_without_runtime()
    result = {
        "success": True,
        "response": "1. Insuf respirat aguda: 24.784\n2. Septicemia NE: 17.904",
        "sql_query": (
            'SELECT c."DESCRICAO" AS causa_morte, COUNT(*) AS total_mortes '
            'FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" '
            "WHERE c.\"DESCRICAO\" <> 'Nao preenchido' GROUP BY causa_morte"
        ),
        "results": [
            {"result": ("Insuf respirat aguda", 24784)},
            {"result": ("Septicemia NE", 17904)},
        ],
        "row_count": 2,
        "metadata": {},
    }

    updated = orchestrator._attach_visualization_if_requested(
        result=result,
        user_query="gere um gráfico de pizza com as 6 principais causas de morte",
        visualization_intent=detect_visualization_intent(
            "gere um gráfico de pizza com as 6 principais causas de morte"
        ),
    )

    assert updated["response"].startswith("1. Insuf respirat aguda")
    assert "desconsidera registros sem causa" in updated["response"].lower()


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


def test_process_query_can_force_chart_from_cached_session_result():
    orchestrator = _orchestrator_without_runtime()
    orchestrator._last_result_by_session["s1"] = {
        "user_query": "Compare os municipios com maior mortalidade e destaque o lider.",
        "sql_query": (
            "SELECT municipio, total_internacoes, total_mortes, taxa "
            "FROM internacoes_ranked LIMIT 10"
        ),
        "results": [
            {
                "municipio": "Nova Friburgo",
                "total_internacoes": 136883,
                "total_mortes": 12582,
                "taxa": 9.19,
            },
            {
                "municipio": "Saquarema",
                "total_internacoes": 57003,
                "total_mortes": 5223,
                "taxa": 9.16,
            },
        ],
        "row_count": 2,
        "metadata": {},
    }

    result = orchestrator.process_query(
        "Gere um grafico dessa resposta usando os dados ja retornados.",
        session_id="s1",
        chart_from_last_result=True,
    )

    assert result["success"] is True
    assert result["chart"]["requested"] is True
    assert result["chart"]["uses_last_result"] is True
    assert result["chart"]["spec"]["chartable"] is True
    assert result["chart"]["spec"]["x"] == "municipio"
    assert result["chart"]["spec"]["y"] == "taxa"
