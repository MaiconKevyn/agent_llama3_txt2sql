"""Per-request runtime budget policy and lightweight instrumentation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any


class RuntimeBudgetExceeded(RuntimeError):
    """Raised when a request exceeds a configured runtime budget."""


@dataclass(frozen=True)
class RuntimeBudgetPolicy:
    request_timeout_seconds: int | None = 120
    llm_timeout_seconds: int | None = 120
    sql_timeout_seconds: int | None = None
    max_llm_calls: int | None = 12
    max_retries: int | None = 3
    max_total_tokens: int | None = None
    max_estimated_cost_usd: float | None = None
    frontend_timeout_seconds: int | None = 120

    @classmethod
    def from_config(
        cls,
        config: Any | None = None,
        *,
        max_retries: int | None = None,
    ) -> RuntimeBudgetPolicy:
        return cls(
            request_timeout_seconds=getattr(config, "llm_timeout", 120) if config else 120,
            llm_timeout_seconds=getattr(config, "llm_timeout", 120) if config else 120,
            sql_timeout_seconds=None,
            max_retries=max_retries
            if max_retries is not None
            else getattr(config, "llm_max_retries", 3),
            frontend_timeout_seconds=120,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RuntimeBudgetTracker:
    policy: RuntimeBudgetPolicy
    llm_calls: int = 0
    llm_call_kinds: list[str] = field(default_factory=list)
    budget_exceeded: bool = False
    sql_timeout_supported: bool = False
    sql_timeout_note: str = "current SQL toolkit path does not expose a hard per-query timeout"

    def record_llm_call(self, kind: str) -> None:
        self.llm_calls += 1
        self.llm_call_kinds.append(kind)
        if self.policy.max_llm_calls is not None and self.llm_calls > self.policy.max_llm_calls:
            self.budget_exceeded = True
            raise RuntimeBudgetExceeded(
                f"Runtime budget exceeded: max_llm_calls={self.policy.max_llm_calls}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy.as_dict(),
            "usage": {
                "llm_calls": self.llm_calls,
                "llm_call_kinds": list(self.llm_call_kinds),
            },
            "budget_exceeded": self.budget_exceeded,
            "sql_timeout": {
                "supported": self.sql_timeout_supported,
                "timeout_seconds": self.policy.sql_timeout_seconds,
                "note": self.sql_timeout_note,
            },
        }


_CURRENT_TRACKER: ContextVar[RuntimeBudgetTracker | None] = ContextVar(
    "runtime_budget_tracker",
    default=None,
)


@contextmanager
def track_runtime_budget(policy: RuntimeBudgetPolicy) -> Iterator[RuntimeBudgetTracker]:
    tracker = RuntimeBudgetTracker(policy=policy)
    token = _CURRENT_TRACKER.set(tracker)
    try:
        yield tracker
    finally:
        _CURRENT_TRACKER.reset(token)


def current_runtime_budget_tracker() -> RuntimeBudgetTracker | None:
    return _CURRENT_TRACKER.get()


def record_llm_call(kind: str) -> None:
    tracker = current_runtime_budget_tracker()
    if tracker is not None:
        tracker.record_llm_call(kind)
