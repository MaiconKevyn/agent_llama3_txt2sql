from types import SimpleNamespace

from src.agent.orchestrator import _orchestrator_config_from_env
from src.interfaces.cli.agent import create_orchestrator_config


def _cli_args(**overrides):
    defaults = {
        "llamaindex_mode": "context",
        "llamaindex_top_k_tables": 6,
        "llamaindex_index_dir": ".llamaindex_schema",
        "llamaindex_rebuild_index": False,
        "verify_llamaindex_schema_with_db": False,
        "disable_analytic_response_templates": False,
        "disable_semantic_plan": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _assert_semantic_plan_disabled(config):
    assert config.disable_semantic_planner is True
    assert config.disable_semantic_plan_validation is True
    assert config.disable_semantic_contract_validation is True
    assert config.disable_semantic_repair_guidance is True


def _assert_semantic_plan_enabled(config):
    assert config.disable_semantic_planner is False
    assert config.disable_semantic_plan_validation is False
    assert config.disable_semantic_contract_validation is False
    assert config.disable_semantic_repair_guidance is False


def test_cli_disable_semantic_plan_sets_all_semantic_guard_flags():
    config = create_orchestrator_config(_cli_args(disable_semantic_plan=True))

    _assert_semantic_plan_disabled(config)


def test_cli_keeps_semantic_plan_enabled_by_default():
    config = create_orchestrator_config(_cli_args())

    _assert_semantic_plan_enabled(config)


def test_env_disable_semantic_plan_sets_all_semantic_guard_flags(monkeypatch):
    monkeypatch.setenv("DISABLE_SEMANTIC_PLAN", "true")

    config = _orchestrator_config_from_env()

    _assert_semantic_plan_disabled(config)


def test_env_keeps_semantic_plan_enabled_by_default(monkeypatch):
    monkeypatch.delenv("DISABLE_SEMANTIC_PLAN", raising=False)

    config = _orchestrator_config_from_env()

    _assert_semantic_plan_enabled(config)
