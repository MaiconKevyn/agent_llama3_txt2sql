import logging

from src.agent.cli_session import InteractiveSession, WorkflowVisualizer


class DummyGraph:
    def draw_mermaid_png(self):
        return b"png-bytes"

    def draw_mermaid(self):
        return "graph TD;"


class DummyWorkflow:
    def get_graph(self, xray=True):
        self.last_xray = xray
        return DummyGraph()


class DummyLogger:
    def __init__(self):
        self.records = []

    def info(self, message, extra=None):
        self.records.append(("info", message, extra))

    def warning(self, message, extra=None):
        self.records.append(("warning", message, extra))

    def error(self, message, extra=None):
        self.records.append(("error", message, extra))


class DummyOrchestrator:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def process_query(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def test_workflow_visualizer_returns_png_bytes():
    workflow = DummyWorkflow()

    result = WorkflowVisualizer.get_workflow_visualization(workflow, xray=False)

    assert result == b"png-bytes"
    assert workflow.last_xray is False


def test_print_workflow_structure_prints_expected_header():
    logger = DummyLogger()
    workflow = DummyWorkflow()
    printed = []

    WorkflowVisualizer.print_workflow_structure(
        workflow,
        logger,
        print_fn=printed.append,
    )

    assert printed[0] == "LangGraph Text2SQL Workflow Structure:"
    assert "DATABASE Route" in printed[2]


def test_interactive_session_runs_single_query_and_exits():
    logger = DummyLogger()
    orchestrator = DummyOrchestrator(
        {"success": True, "response": "ok", "sql_query": "select 1", "execution_time": 1.25}
    )
    printed = []
    inputs = iter(["pergunta de teste", "sair"])

    InteractiveSession.start(
        orchestrator,
        logger,
        "testing",
        input_fn=lambda prompt: next(inputs),
        print_fn=printed.append,
    )

    assert len(orchestrator.calls) == 1
    assert orchestrator.calls[0]["metadata"]["environment"] == "testing"
    assert any("ok" in line for line in printed)
    assert any(level == "info" and message == "Interactive session ended by user" for level, message, _ in logger.records)


def test_interactive_session_reuses_session_id_for_followups():
    logger = DummyLogger()
    orchestrator = DummyOrchestrator(
        {"success": True, "response": "ok", "sql_query": "select 1", "execution_time": 1.25}
    )
    printed = []
    inputs = iter(["primeira pergunta", "gere um grafico disso", "sair"])

    InteractiveSession.start(
        orchestrator,
        logger,
        "testing",
        input_fn=lambda prompt: next(inputs),
        print_fn=printed.append,
    )

    assert len(orchestrator.calls) == 2
    assert orchestrator.calls[0]["session_id"] == orchestrator.calls[1]["session_id"]
