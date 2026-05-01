from src.agent.metrics import MetricsCollector


def test_metrics_collector_tracks_success_failure_and_recent_stats():
    collector = MetricsCollector(max_history=5)

    assert collector.begin_query() == 1
    collector.record_result(
        "pergunta 1",
        {"success": True, "results": [1]},
        2.0,
        model_id="openai/gpt-4o-mini",
    )

    assert collector.begin_query() == 2
    collector.record_result(
        "pergunta 2",
        {"success": False, "error_message": "falhou"},
        4.0,
        model_id="openai/gpt-4o-mini",
    )

    snapshot = collector.build_snapshot(
        environment="testing",
        current_model={
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "temperature": 0.0,
        },
        llm_health={"status": "healthy"},
    )

    assert snapshot["total_statistics"]["total_queries"] == 2
    assert snapshot["total_statistics"]["successful_queries"] == 1
    assert snapshot["total_statistics"]["failed_queries"] == 1
    assert snapshot["total_statistics"]["average_execution_time"] == 3.0
    assert snapshot["recent_performance"]["recent_queries_count"] == 2
    assert snapshot["recent_performance"]["recent_success_rate"] == 0.5
    assert snapshot["model_performance"]["openai/gpt-4o-mini"]["queries"] == 2
    assert snapshot["llm_manager_health"]["status"] == "healthy"


def test_metrics_collector_respects_history_limit():
    collector = MetricsCollector(max_history=2)

    for index in range(3):
        collector.begin_query()
        collector.record_result(
            f"pergunta {index}",
            {"success": True},
            float(index + 1),
            model_id="openai/gpt-4o-mini",
        )

    snapshot = collector.build_snapshot(
        environment="testing",
        current_model={
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "temperature": 0.0,
        },
        llm_health={"status": "healthy"},
    )

    assert snapshot["total_statistics"]["total_queries"] == 3
    assert snapshot["recent_performance"]["recent_queries_count"] == 2
    assert snapshot["model_performance"]["openai/gpt-4o-mini"]["queries"] == 2
