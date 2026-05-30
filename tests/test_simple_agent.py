from types import SimpleNamespace

from sqlalchemy import create_engine, text

from src.agent.simple_agent import SimpleSQLAgent, SQLDraft, _load_business_tables, clean_llm_sql


class _FakeDatabase:
    def __init__(self, engine):
        self._engine = engine


class _FakeManager:
    config = SimpleNamespace(llm_timeout=30, llm_max_retries=1)

    def __init__(self, engine):
        self._database = _FakeDatabase(engine)

    def get_database(self):
        return self._database

    def invoke_chat_structured(self, _messages, _schema):
        return SQLDraft(
            sql='SELECT COUNT(*) AS total_internacoes FROM internacoes WHERE "VAL_UTI" > 0;',
            reasoning="test",
        )

    def invoke_chat(self, _messages):
        return SimpleNamespace(content="Foram encontradas 2 internacoes com UTI.")


def test_clean_llm_sql_extracts_fenced_select():
    sql = clean_llm_sql("```sql\nSELECT COUNT(*) FROM internacoes\n```")

    assert sql == "SELECT COUNT(*) FROM internacoes;"


def test_business_tables_exclude_audit_and_staging_tables():
    tables = _load_business_tables()

    assert "internacoes" in tables
    assert "internacao_procedimento" in tables
    assert "stg_internacoes" not in tables
    assert "internacoes_val_uti_marca_uti" not in tables


def test_simple_agent_runs_sql_and_returns_evaluation_rows():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE internacoes ("VAL_UTI" FLOAT);'))
        conn.execute(text('INSERT INTO internacoes ("VAL_UTI") VALUES (0), (12), (4);'))

    agent = SimpleSQLAgent(_FakeManager(engine), schema_context="TABLE: internacoes")
    result = agent.run("Quantos registros de internacao em UTI existem?", session_id="s1")

    assert result["success"] is True
    assert result["sql_query"] == (
        'SELECT COUNT(*) AS total_internacoes FROM internacoes WHERE "VAL_UTI" > 0;'
    )
    assert result["final_result_rows"] == [(2,)]
    assert result["results"] == [{"total_internacoes": 2}]
    assert result["metadata"]["workflow_metrics"]["overall_success"] is True
