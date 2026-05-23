from src.agent.conversation_context import resolve_contextual_followup
from src.agent.orchestrator import LangGraphOrchestrator


class DummyLogger:
    def info(self, message, extra=None):
        self.last_info = (message, extra)

    def error(self, message, extra=None):
        self.last_error = (message, extra)

    def warning(self, message, extra=None):
        self.last_warning = (message, extra)


class DummyMetrics:
    total_queries = 0

    def begin_query(self):
        self.total_queries += 1
        return self.total_queries

    def record_result(self, *args, **kwargs):
        self.last_result = (args, kwargs)


class DummyModel:
    provider = "openai"
    model_name = "test-model"
    temperature = 0.0


def _orchestrator_without_runtime():
    orchestrator = object.__new__(LangGraphOrchestrator)
    orchestrator.logger = DummyLogger()
    orchestrator._metrics = DummyMetrics()
    orchestrator._current_model = DummyModel()
    orchestrator._last_result_by_session = {}
    orchestrator._workflow = object()
    orchestrator.orchestrator_config = None
    orchestrator.environment = "testing"
    return orchestrator


def test_year_followup_rewrites_previous_question_year():
    result = resolve_contextual_followup(
        user_query="E em 2022?",
        cached_result={"user_query": "Quantas internacoes ocorreram em 2021?"},
    )

    assert result.is_followup is True
    assert result.resolved_query == "Quantas internacoes ocorreram em 2022?"
    assert result.metadata["type"] == "year_filter"


def test_dimension_followup_adds_grouping_to_previous_question():
    result = resolve_contextual_followup(
        user_query="Agora por sexo",
        cached_result={"user_query": "Quantas internacoes ocorreram em 2021?"},
    )

    assert result.is_followup is True
    assert result.resolved_query == "Quantas internacoes ocorreram em 2021 por sexo?"
    assert result.metadata["applied"] == {"dimension": "sexo"}


def test_uf_filter_followup_adds_state_scope_to_previous_question():
    result = resolve_contextual_followup(
        user_query="Agora so no RS",
        cached_result={"user_query": "Mostre internacoes por mes em 2021."},
    )

    assert result.is_followup is True
    assert result.resolved_query == "Mostre internacoes por mes em 2021 no estado RS?"
    assert result.metadata["applied"] == {"uf": "RS"}


def test_orchestrator_executes_resolved_followup_query(monkeypatch):
    orchestrator = _orchestrator_without_runtime()
    orchestrator._last_result_by_session["s1"] = {
        "user_query": "Quantas internacoes ocorreram em 2021?",
        "sql_query": "SELECT COUNT(*) FROM internacoes WHERE ano = 2021",
        "results": [{"total": 10}],
        "metadata": {},
    }
    captured = {}

    def fake_execute_sql_workflow(**kwargs):
        captured["user_query"] = kwargs["user_query"]
        return {
            "success": True,
            "response": "Foram 12 internacoes.",
            "sql_query": "SELECT COUNT(*) FROM internacoes WHERE ano = 2022",
            "results": [{"total": 12}],
            "row_count": 1,
            "metadata": {},
        }

    monkeypatch.setattr("src.agent.orchestrator.execute_sql_workflow", fake_execute_sql_workflow)

    result = orchestrator.process_query("E em 2022?", session_id="s1")

    assert captured["user_query"] == "Quantas internacoes ocorreram em 2022?"
    assert result["metadata"]["conversation_followup"]["previous_query"] == (
        "Quantas internacoes ocorreram em 2021?"
    )
    assert orchestrator._last_result_by_session["s1"]["canonical_query"] == (
        "Quantas internacoes ocorreram em 2022?"
    )
