from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agent.llm_manager import OpenAILLMManager
from src.agent.runtime_budget import (
    RuntimeBudgetExceeded,
    RuntimeBudgetPolicy,
    record_llm_call,
    track_runtime_budget,
)
from src.application.config.simple_config import ApplicationConfig


class DummyLLM:
    def invoke(self, messages):
        return AIMessage(content="ok")

    def with_structured_output(self, output_schema):
        return self


def test_runtime_budget_policy_uses_existing_config_defaults():
    config = ApplicationConfig(llm_timeout=45, llm_max_retries=2)

    policy = RuntimeBudgetPolicy.from_config(config, max_retries=4)

    assert policy.request_timeout_seconds == 45
    assert policy.llm_timeout_seconds == 45
    assert policy.max_retries == 4
    assert policy.max_llm_calls == 12
    assert policy.sql_timeout_seconds is None


def test_runtime_budget_tracker_counts_and_blocks_llm_calls():
    policy = RuntimeBudgetPolicy(max_llm_calls=1)

    with pytest.raises(RuntimeBudgetExceeded):
        with track_runtime_budget(policy) as tracker:
            record_llm_call("chat")
            record_llm_call("structured_chat")

    snapshot = tracker.as_dict()
    assert snapshot["usage"]["llm_calls"] == 2
    assert snapshot["budget_exceeded"] is True


def test_llm_manager_invoke_chat_records_runtime_budget():
    manager = OpenAILLMManager.__new__(OpenAILLMManager)
    manager._llm = DummyLLM()

    with track_runtime_budget(RuntimeBudgetPolicy()) as tracker:
        response = OpenAILLMManager.invoke_chat(manager, [HumanMessage(content="oi")])

    assert response.content == "ok"
    assert tracker.as_dict()["usage"]["llm_call_kinds"] == ["chat"]


def test_llm_manager_structured_chat_records_runtime_budget():
    manager = OpenAILLMManager.__new__(OpenAILLMManager)
    manager._llm = DummyLLM()

    with track_runtime_budget(RuntimeBudgetPolicy()) as tracker:
        response = OpenAILLMManager.invoke_chat_structured(
            manager,
            [HumanMessage(content="oi")],
            object,
        )

    assert response.content == "ok"
    assert tracker.as_dict()["usage"]["llm_call_kinds"] == ["structured_chat"]


def test_frontend_proxy_uses_abort_controller_for_query_timeout():
    server_js = Path("frontend/server.js").read_text(encoding="utf-8")

    assert "new AbortController()" in server_js
    assert "controller.abort()" in server_js
    assert "signal: controller.signal" in server_js
    assert "timeout: API_CONFIG.TIMEOUTS.QUERY" not in server_js
