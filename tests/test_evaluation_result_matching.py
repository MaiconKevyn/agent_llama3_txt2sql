from evaluation.runners.result_matching import compare_results, results_match
from evaluation.runners.run_ablation import (
    VariantSpec,
    _collect_item_results,
    _gold_cache_key,
    _write_item_result,
    run_variant,
)


def test_results_match_accepts_tuple_values_from_agent_rows():
    agent_rows = [{"result": (963254,)}]
    gold_raw = "[(963254,)]"

    assert results_match(agent_rows, gold_raw)


def test_results_match_accepts_final_result_rows_directly():
    agent_rows = [(2020, 10), (2021, 15)]
    gold_raw = "[(2021, 15), (2020, 10)]"

    assert results_match(agent_rows, gold_raw)


def test_results_match_accepts_list_row_values_from_agent_rows():
    agent_rows = [{"result": ["porto alegre", 123]}]
    gold_raw = "[('Porto Alegre', 123)]"

    assert results_match(agent_rows, gold_raw)


def test_results_match_reuses_projected_ex_semantics():
    agent_rows = [("RS", 100, 8.5)]
    gold_raw = "[(100, 8.5)]"

    assert results_match(agent_rows, gold_raw)


def test_compare_results_returns_audit_details():
    comparison = compare_results([("RS", 100, 8.5)], "[(100, 8.5)]")

    assert comparison["match"] is True
    assert comparison["gold_row_count"] == 1
    assert comparison["predicted_row_count"] == 1
    assert comparison["gold_rows_sample"] == [[100, 8.5]]
    assert comparison["predicted_rows_sample"] == [["RS", 100, 8.5]]
    assert comparison["details"]["projected_match"] is True


def test_ablation_variant_uses_run_id_in_session_and_records_comparison_details():
    class FakeQueryTool:
        name = "sql_db_query"

        def invoke(self, _sql):
            return "[(1,)]"

    class FakeDbManager:
        def get_sql_tools(self):
            return [FakeQueryTool()]

    class FakeOrchestrator:
        def __init__(self):
            self.session_ids = []

        def process_query(self, _question, session_id, force_single_query):
            self.session_ids.append(session_id)
            assert force_single_query is True
            return {
                "success": True,
                "sql_query": "SELECT 1;",
                "final_result_rows": [(1,)],
                "cost": {"total_tokens": 10, "total_cost_usd": 0.01},
            }

    orchestrator = FakeOrchestrator()
    rows = run_variant(
        VariantSpec("VT", "test_variant", "Test variant"),
        [{"id": "GT001", "question": "q", "query": "SELECT 1;", "difficulty": "easy"}],
        orchestrator,
        FakeDbManager(),
        run_id="run123",
        verbose=False,
    )

    assert orchestrator.session_ids == ["ablation_run123_VT_GT001"]
    assert rows[0]["ex"] is True
    assert rows[0]["session_id"] == "ablation_run123_VT_GT001"
    assert rows[0]["agent_result_source"] == "final_result_rows"
    assert rows[0]["gold_row_count"] == 1
    assert rows[0]["predicted_row_count"] == 1


def test_ablation_variant_can_reuse_gold_cache_without_db_gold_execution():
    class FakeQueryTool:
        name = "sql_db_query"

        def invoke(self, _sql):
            raise AssertionError("gold SQL should come from cache")

    class FakeDbManager:
        def get_sql_tools(self):
            return [FakeQueryTool()]

    class FakeOrchestrator:
        def process_query(self, _question, session_id, force_single_query):
            assert session_id == "ablation_run123_VT_GT001"
            assert force_single_query is True
            return {
                "success": True,
                "sql_query": "SELECT 1;",
                "final_result_rows": [(1,)],
                "cost": {"total_tokens": 10, "total_cost_usd": 0.01},
            }

    query = {"id": "GT001", "question": "q", "query": "SELECT 1;", "difficulty": "easy"}
    gold_cache = {_gold_cache_key(query): {"raw": "[(1,)]"}}

    rows = run_variant(
        VariantSpec("VT", "test_variant", "Test variant"),
        [query],
        FakeOrchestrator(),
        FakeDbManager(),
        run_id="run123",
        verbose=False,
        gold_cache=gold_cache,
    )

    assert rows[0]["ex"] is True


def test_ablation_item_checkpoint_round_trip(tmp_path):
    spec = VariantSpec("VT", "test_variant", "Test variant")
    result = {
        "variant_id": "VT",
        "variant_name": "test_variant",
        "id": "GT001",
        "difficulty": "easy",
        "question": "q",
        "gold_sql": "SELECT 1;",
        "generated_sql": "SELECT 1;",
        "ex": True,
        "elapsed_s": 0.1,
        "error": "",
        "session_id": "ablation_run_VT_GT001",
        "agent_result_source": "final_result_rows",
        "gold_row_count": 1,
        "predicted_row_count": 1,
        "gold_rows_sample": "[]",
        "predicted_rows_sample": "[]",
        "comparison_details": "{}",
        "critical_rule": None,
        "prompt_tokens": 1,
        "completion_tokens": 1,
        "total_tokens": 2,
        "total_cost_usd": 0.001,
    }

    _write_item_result(
        tmp_path / "items" / "VT_GT001.json",
        result,
        run_ts="2026-01-01T00:00:00Z",
        run_id="run",
        git_sha="abc",
        model_id="model",
    )

    collected = _collect_item_results(
        [spec],
        [{"id": "GT001", "question": "q", "query": "SELECT 1;", "difficulty": "easy"}],
        tmp_path / "items",
    )

    assert collected["VT"] == [result]
