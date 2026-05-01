from datetime import datetime
from typing import Any, Dict, List


class MetricsCollector:
    """Tracks orchestrator counters and recent query history."""

    def __init__(self, max_history: int = 1000):
        self._max_history = max_history
        self.reset()

    @property
    def total_queries(self) -> int:
        return self._total_queries

    @property
    def successful_queries(self) -> int:
        return self._successful_queries

    @property
    def failed_queries(self) -> int:
        return self._failed_queries

    @property
    def total_execution_time(self) -> float:
        return self._total_execution_time

    def begin_query(self) -> int:
        self._total_queries += 1
        return self._total_queries

    def record_streaming_success(self, execution_time: float) -> None:
        self._total_execution_time += execution_time
        self._successful_queries += 1

    def record_result(
        self,
        query: str,
        result: Dict[str, Any],
        execution_time: float,
        *,
        model_id: str,
    ) -> None:
        self._total_execution_time += execution_time

        success = result.get("success", False)
        if success:
            self._successful_queries += 1
        else:
            self._failed_queries += 1

        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "query": query[:100],
            "success": success,
            "execution_time": execution_time,
            "model": model_id,
            "error": result.get("error_message") if not success else None,
        }
        self._query_history.append(history_entry)

        if len(self._query_history) > self._max_history:
            self._query_history = self._query_history[-self._max_history :]

    def record_exception(self, execution_time: float) -> None:
        self._total_execution_time += execution_time
        self._failed_queries += 1

    def reset(self) -> None:
        self._total_queries = 0
        self._successful_queries = 0
        self._failed_queries = 0
        self._total_execution_time = 0.0
        self._query_history: List[Dict[str, Any]] = []

    def get_model_performance(self) -> Dict[str, Any]:
        model_stats: Dict[str, Dict[str, Any]] = {}

        for entry in self._query_history:
            model = entry["model"]
            stats = model_stats.setdefault(
                model,
                {"queries": 0, "successes": 0, "total_time": 0.0},
            )
            stats["queries"] += 1
            if entry["success"]:
                stats["successes"] += 1
            stats["total_time"] += entry["execution_time"]

        for stats in model_stats.values():
            queries = stats["queries"]
            stats["success_rate"] = stats["successes"] / queries if queries else 0
            stats["average_time"] = stats["total_time"] / queries if queries else 0

        return model_stats

    def build_snapshot(
        self,
        *,
        environment: str,
        current_model: Dict[str, Any],
        llm_health: Dict[str, Any],
        version: str = "3.0",
    ) -> Dict[str, Any]:
        recent_queries = self._query_history[-10:] if self._query_history else []
        avg_execution_time = (
            self._total_execution_time / self._total_queries
            if self._total_queries > 0
            else 0
        )
        success_rate = (
            self._successful_queries / self._total_queries
            if self._total_queries > 0
            else 0
        )
        recent_success_rate = (
            sum(1 for q in recent_queries if q["success"]) / len(recent_queries)
            if recent_queries
            else 0
        )
        recent_avg_time = (
            sum(q["execution_time"] for q in recent_queries) / len(recent_queries)
            if recent_queries
            else 0
        )

        return {
            "orchestrator_info": {
                "version": version,
                "environment": environment,
                "current_model": current_model,
            },
            "total_statistics": {
                "total_queries": self._total_queries,
                "successful_queries": self._successful_queries,
                "failed_queries": self._failed_queries,
                "success_rate": success_rate,
                "average_execution_time": avg_execution_time,
                "total_execution_time": self._total_execution_time,
            },
            "recent_performance": {
                "recent_queries_count": len(recent_queries),
                "recent_success_rate": recent_success_rate,
                "recent_average_time": recent_avg_time,
            },
            "model_performance": self.get_model_performance(),
            "llm_manager_health": llm_health,
        }
