"""Execution-time SQL safety contract for the simple agent."""

from __future__ import annotations

from dataclasses import dataclass

from ..utils.sql_safety import is_select_only


@dataclass(frozen=True)
class SQLExecutionContractResult:
    allowed: bool
    reason: str = ""

    @property
    def error_message(self) -> str:
        if self.allowed:
            return ""
        return f"SQL execution blocked: {self.reason}"


def validate_sql_execution_contract(sql_query: str) -> SQLExecutionContractResult:
    ok, reason = is_select_only(sql_query)
    return SQLExecutionContractResult(allowed=ok, reason=reason)
