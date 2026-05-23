"""Per-query cost tracking via LangChain's OpenAI callback.

Usage
-----
    with QueryCostTracker() as tracker:
        result = workflow.invoke(state, config)
    print(tracker.as_dict())   # {"prompt_tokens": ..., "total_cost_usd": ...}

Falls back to zeroed dict if langchain_community is unavailable.
"""

from __future__ import annotations

from typing import Any

_EMPTY = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "total_cost_usd": 0.0,
    "successful_requests": 0,
}

try:
    from langchain_community.callbacks import get_openai_callback as _get_cb

    _CB_AVAILABLE = True
except ImportError:
    _CB_AVAILABLE = False


class QueryCostTracker:
    """Context manager that captures OpenAI token usage for a block of code."""

    def __init__(self):
        self._ctx = None  # the generator context manager from get_openai_callback()
        self._handler = None  # the OpenAICallbackHandler returned by __enter__
        self._data: dict[str, Any] = dict(_EMPTY)

    def __enter__(self) -> QueryCostTracker:
        if _CB_AVAILABLE:
            self._ctx = _get_cb()
            self._handler = self._ctx.__enter__()
        return self

    def __exit__(self, *args):
        if self._ctx is not None:
            self._ctx.__exit__(*args)
            h = self._handler
            self._data = {
                "prompt_tokens": h.prompt_tokens,
                "completion_tokens": h.completion_tokens,
                "total_tokens": h.total_tokens,
                "total_cost_usd": round(h.total_cost, 6),
                "successful_requests": h.successful_requests,
            }

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)


__all__ = ["QueryCostTracker"]
