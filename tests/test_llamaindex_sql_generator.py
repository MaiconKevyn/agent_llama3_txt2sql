import pytest

from src.agent import sql_generation
from src.agent.llamaindex_sql_generator import LlamaIndexSQLDraft, generate_llamaindex_sql_draft
from src.agent.state_helpers import create_initial_messages_state


def test_llamaindex_sql_draft_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        generate_llamaindex_sql_draft(
            user_query="Quantas mortes foram registradas?",
            schema_context="TABLE internacoes: MORTE boolean",
            selected_tables=["internacoes"],
            semantic_plan=None,
            chart_plan=None,
            model="gpt-4o-mini",
            temperature=0.0,
        )


class _FakeConfig:
    llm_model = "gpt-4o-mini"
    llm_temperature = 0.0


class _FakeLLMManager:
    config = _FakeConfig()

    def _clean_sql_query(self, sql_query: str) -> str:
        return sql_query.strip().rstrip(";") + ";"

    def invoke_chat_structured(self, *_args, **_kwargs):
        raise AssertionError("current generator should not run when LlamaIndex draft succeeds")


def test_generate_sql_node_accepts_llamaindex_sql_draft(monkeypatch):
    monkeypatch.setattr(sql_generation, "get_llm_manager", lambda: _FakeLLMManager())

    def fake_draft(**_kwargs):
        return LlamaIndexSQLDraft(
            sql='SELECT COUNT(*) AS total_mortes FROM internacoes WHERE "MORTE" = true',
            reasoning="Counts death rows in internacoes.",
            confidence=0.9,
        )

    import src.agent.llamaindex_sql_generator as llama_sql

    monkeypatch.setattr(llama_sql, "generate_llamaindex_sql_draft", fake_draft)
    state = create_initial_messages_state(
        "Quantas mortes foram registradas?",
        session_id="test",
        ablation_flags={"llamaindex_mode": "sql_draft"},
    )
    state["schema_context"] = 'TABLE internacoes: "MORTE" BOOLEAN'
    state["selected_tables"] = ["internacoes"]

    new_state = sql_generation.generate_sql_node(state)

    assert new_state["generated_sql"] == 'SELECT COUNT(*) AS total_mortes FROM internacoes WHERE "MORTE" = true;'
    assert new_state["response_metadata"]["sql_generation_source"] == "llamaindex_sql_draft"
    assert new_state["response_metadata"]["sql_generation_confidence"] == 0.9
