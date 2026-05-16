from src.application.config.simple_config import OrchestratorConfig


def test_llamaindex_flags_default_to_context_pipeline():
    cfg = OrchestratorConfig()

    assert cfg.enable_llamaindex_context is True
    assert cfg.enable_llamaindex_sql_draft is False
    assert cfg.llamaindex_mode == "context"
    assert cfg.llamaindex_top_k_tables == 6
    assert cfg.llamaindex_rebuild_index is False
    assert cfg.verify_llamaindex_schema_with_db is False


def test_llamaindex_env_config_enables_api_factory_mode(monkeypatch):
    from src.agent.orchestrator import _orchestrator_config_from_env

    monkeypatch.setenv("LLAMAINDEX_MODE", "context")
    monkeypatch.setenv("LLAMAINDEX_TOP_K_TABLES", "4")
    monkeypatch.setenv("LLAMAINDEX_INDEX_DIR", "/tmp/li-index")
    monkeypatch.setenv("LLAMAINDEX_REBUILD_INDEX", "true")
    monkeypatch.setenv("VERIFY_LLAMAINDEX_SCHEMA_WITH_DB", "true")

    cfg = _orchestrator_config_from_env()

    assert cfg.enable_llamaindex_context is True
    assert cfg.enable_llamaindex_sql_draft is False
    assert cfg.llamaindex_mode == "context"
    assert cfg.llamaindex_top_k_tables == 4
    assert cfg.llamaindex_index_dir == "/tmp/li-index"
    assert cfg.llamaindex_rebuild_index is True
    assert cfg.verify_llamaindex_schema_with_db is True
