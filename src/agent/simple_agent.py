"""Simple text-to-SQL agent.

This module is the new runtime path for the chatbot.  It intentionally avoids
LangGraph, semantic planner loops, deterministic macro routers, LlamaIndex
retrieval, and post-execution semantic contracts.  The flow is:

question -> database context prompt -> SQL -> execute -> conversational answer
"""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlalchemy import text

from src.application.schema.paths import GENERATED_SCHEMA_DIR
from src.utils.sql_safety import is_select_only, sanitize_sql_for_execution

from .cost_tracker import QueryCostTracker
from .execution_contracts import validate_sql_execution_contract
from .runtime_budget import RuntimeBudgetPolicy, track_runtime_budget

DEFAULT_MAX_RESULT_ROWS = 1000
MAX_CONTEXT_COLUMNS_PER_TABLE = 80
MAX_TOP_VALUE_COLUMNS_PER_TABLE = 8
MAX_TOP_VALUES_PER_COLUMN = 5


class SQLDraft(BaseModel):
    """Structured LLM output for SQL generation."""

    sql: str = Field(description="A single DuckDB-compatible SELECT/WITH SQL statement.")
    reasoning: str = Field(default="", description="Brief private rationale for debugging.")


@dataclass(frozen=True)
class QueryExecution:
    success: bool
    sql: str
    rows: list[tuple[Any, ...]]
    columns: list[str]
    elapsed_s: float
    error: str | None = None
    truncated: bool = False


class SimpleSQLAgent:
    """Minimal database-question agent with one LLM SQL step and one answer step."""

    def __init__(
        self,
        llm_manager: Any,
        *,
        max_result_rows: int = DEFAULT_MAX_RESULT_ROWS,
        schema_context: str | None = None,
    ) -> None:
        self.llm_manager = llm_manager
        self.max_result_rows = max_result_rows
        self._schema_context = schema_context

    def run(self, question: str, *, session_id: str | None = None) -> dict[str, Any]:
        started_at = time.time()
        latency: dict[str, float] = {}
        metadata: dict[str, Any] = {
            "simple_agent": True,
            "langgraph_v3": False,
            "messages_state": False,
            "session_id": session_id,
            "sql_generation_source": "simple_llm",
            "semantic_plan": {},
            "semantic_validation": {},
            "semantic_error": {},
            "semantic_repair": {},
            "repair_attempts": [],
            "llamaindex_mode": None,
            "llamaindex_retrieval_mode": None,
            "llamaindex_selected_tables": [],
        }

        budget_policy = RuntimeBudgetPolicy.from_config(self.llm_manager.config, max_retries=1)
        with QueryCostTracker() as cost, track_runtime_budget(budget_policy) as runtime_budget:
            try:
                t0 = time.time()
                schema_context = self._get_schema_context()
                latency["schema_context"] = time.time() - t0

                t0 = time.time()
                sql, reasoning = self._generate_sql(question, schema_context)
                latency["sql_generation"] = time.time() - t0

                execution = self._validate_and_execute(sql)
                latency["sql_execution"] = execution.elapsed_s

                if not execution.success:
                    t0 = time.time()
                    repaired_sql, repair_reasoning = self._generate_sql(
                        question,
                        schema_context,
                        previous_sql=sql,
                        previous_error=execution.error,
                    )
                    latency["sql_repair"] = time.time() - t0
                    repair_execution = self._validate_and_execute(repaired_sql)
                    latency["sql_execution_repair"] = repair_execution.elapsed_s
                    metadata["repair_attempts"] = [
                        {
                            "previous_sql": sql,
                            "previous_error": execution.error,
                            "repair_reasoning": repair_reasoning,
                        }
                    ]
                    sql = repaired_sql
                    reasoning = repair_reasoning or reasoning
                    execution = repair_execution

                if not execution.success:
                    return self._build_result(
                        question=question,
                        sql=sql,
                        execution=execution,
                        answer=f"Nao foi possivel executar a consulta SQL: {execution.error}",
                        started_at=started_at,
                        metadata=metadata,
                        latency=latency,
                        cost=cost.as_dict(),
                        runtime_budget=runtime_budget.as_dict(),
                        reasoning=reasoning,
                    )

                t0 = time.time()
                answer = self._generate_answer(question, execution)
                latency["response_generation"] = time.time() - t0

                return self._build_result(
                    question=question,
                    sql=sql,
                    execution=execution,
                    answer=answer,
                    started_at=started_at,
                    metadata=metadata,
                    latency=latency,
                    cost=cost.as_dict(),
                    runtime_budget=runtime_budget.as_dict(),
                    reasoning=reasoning,
                )
            except Exception as exc:
                failed_execution = QueryExecution(
                    success=False,
                    sql="",
                    rows=[],
                    columns=[],
                    elapsed_s=0.0,
                    error=str(exc),
                )
                return self._build_result(
                    question=question,
                    sql="",
                    execution=failed_execution,
                    answer=f"Erro ao processar a pergunta: {exc}",
                    started_at=started_at,
                    metadata=metadata,
                    latency=latency,
                    cost=cost.as_dict(),
                    runtime_budget=runtime_budget.as_dict(),
                    reasoning="",
                )

    def _build_result(
        self,
        *,
        question: str,
        sql: str,
        execution: QueryExecution,
        answer: str,
        started_at: float,
        metadata: dict[str, Any],
        latency: dict[str, float],
        cost: dict[str, Any],
        runtime_budget: dict[str, Any],
        reasoning: str,
    ) -> dict[str, Any]:
        results = [dict(zip(execution.columns, row, strict=False)) for row in execution.rows]
        success = execution.success
        metadata = {
            **metadata,
            "workflow_metrics": {
                "overall_success": success,
                "retry_count": len(metadata.get("repair_attempts") or []),
                "error_count": 0 if success else 1,
            },
            "latency_by_component": latency,
            "runtime_budget": runtime_budget,
            "sql_reasoning": reasoning,
            "result_truncated": execution.truncated,
            "tables_used": _guess_tables_used(sql),
        }
        return {
            "success": success,
            "technical_success": success,
            "answerability": "answerable" if success else "technical_error",
            "question": question,
            "sql_query": sql or None,
            "results": results,
            "row_count": len(results),
            "execution_time": round(time.time() - started_at, 4),
            "error_message": execution.error,
            "response": answer,
            "timestamp": datetime.now().isoformat(),
            "final_result_rows": execution.rows,
            "chart": None,
            "metadata": metadata,
            "cost": cost,
        }

    def _get_schema_context(self) -> str:
        if self._schema_context is None:
            self._schema_context = build_simple_schema_context()
        return self._schema_context

    def _generate_sql(
        self,
        question: str,
        schema_context: str,
        *,
        previous_sql: str | None = None,
        previous_error: str | None = None,
    ) -> tuple[str, str]:
        repair_block = ""
        if previous_sql or previous_error:
            repair_block = (
                "\nPrevious SQL failed. Fix it and return a new valid SQL only.\n"
                f"PREVIOUS_SQL:\n{previous_sql or ''}\n"
                f"ERROR:\n{previous_error or ''}\n"
            )

        messages = [
            SystemMessage(content=build_sql_system_prompt(schema_context)),
            HumanMessage(content=f"QUESTION:\n{question}\n{repair_block}"),
        ]

        try:
            draft = self.llm_manager.invoke_chat_structured(messages, SQLDraft)
            sql = getattr(draft, "sql", "") or ""
            reasoning = getattr(draft, "reasoning", "") or ""
        except Exception:
            response = self.llm_manager.invoke_chat(messages)
            sql = getattr(response, "content", str(response))
            reasoning = "raw_text_fallback"

        return clean_llm_sql(sql), reasoning

    def _validate_and_execute(self, sql: str) -> QueryExecution:
        t0 = time.time()
        cleaned_sql = clean_llm_sql(sql)
        execution_contract = validate_sql_execution_contract(cleaned_sql)
        if not execution_contract.allowed:
            return QueryExecution(
                success=False,
                sql=cleaned_sql,
                rows=[],
                columns=[],
                elapsed_s=time.time() - t0,
                error=execution_contract.error_message,
            )

        try:
            engine = self.llm_manager.get_database()._engine
            with engine.connect() as conn:
                conn.execute(text(f"EXPLAIN {cleaned_sql}"))
                result = conn.execute(text(cleaned_sql))
                columns = list(result.keys())
                fetched = result.fetchmany(self.max_result_rows + 1)
            truncated = len(fetched) > self.max_result_rows
            rows = [tuple(row) for row in fetched[: self.max_result_rows]]
            return QueryExecution(
                success=True,
                sql=cleaned_sql,
                rows=rows,
                columns=columns,
                elapsed_s=time.time() - t0,
                truncated=truncated,
            )
        except Exception as exc:
            return QueryExecution(
                success=False,
                sql=cleaned_sql,
                rows=[],
                columns=[],
                elapsed_s=time.time() - t0,
                error=str(exc),
            )

    def _generate_answer(self, question: str, execution: QueryExecution) -> str:
        if not execution.rows:
            return "A consulta foi executada, mas nao retornou linhas."

        sample_rows = [dict(zip(execution.columns, row, strict=False)) for row in execution.rows[:20]]
        messages = [
            SystemMessage(
                content=(
                    "Voce responde perguntas sobre o banco DATASUS/SIH em portugues. "
                    "Use somente os resultados SQL fornecidos. Seja direto e nao invente dados."
                )
            ),
            HumanMessage(
                content=(
                    f"Pergunta: {question}\n"
                    f"SQL: {execution.sql}\n"
                    f"Colunas: {execution.columns}\n"
                    f"Amostra/resultado: {sample_rows}\n"
                    f"Linhas retornadas: {len(execution.rows)}\n"
                    "Responda de forma conversacional e concisa."
                )
            ),
        ]
        try:
            response = self.llm_manager.invoke_chat(messages)
            answer = getattr(response, "content", "") or ""
            return answer.strip() or _fallback_answer(execution)
        except Exception:
            return _fallback_answer(execution)


def build_sql_system_prompt(schema_context: str) -> str:
    return f"""You are a senior DuckDB SQL engineer for a Brazilian DATASUS/SIH database.

Return exactly one read-only SQL query. Prefer SELECT/WITH. Never use INSERT,
UPDATE, DELETE, CREATE, DROP, COPY, PRAGMA, ATTACH, or multiple statements.

Use only the user-facing business tables in the context. Never use dbt audit
tables, `main_dbt_test__audit`, `stg_*`, `source_*`, `not_null_*`,
`accepted_values_*`, or generated validation tables.

Core domain rules:
- Admissions live in `internacoes`; one row per admission (`N_AIH`).
- Procedures live in `internacao_procedimento`; join to `internacoes` by `N_AIH`
  and to `procedimentos` by `PROC_REA`.
- Diagnosis descriptions live in `cid`; join `internacoes.DIAG_PRINC = cid.CID`
  for principal diagnosis questions.
- Death means `internacoes.MORTE = true`. Mortality rates must use conditional
  aggregation in the numerator and keep the denominator unfiltered by death.
- Admission character codes: urgency is `CAR_INT = 2`; elective is `CAR_INT = 1`.
- Complexity codes: high complexity is `COMPLEX = '03'`; medium complexity is
  `COMPLEX = '02'`; basic care is `COMPLEX = '01'`.
- UTI admission/use/cost means `internacoes.VAL_UTI > 0`, unless the question
  explicitly asks for UTI type, then use `MARCA_UTI` with the `marca_uti` lookup.
- VDRL positive means `internacoes.IND_VDRL = true`.
- Obstetric admissions mean `internacoes.ESPEC = 2`.
- COVID/coronavirus principal diagnosis means `DIAG_PRINC IN ('B342', 'B972')`.
- Respiratory diseases are CID codes starting with `J`; pneumonia as a principal
  diagnosis is usually `DIAG_PRINC LIKE 'J18%'` unless the question explicitly
  asks for the full pneumonia CID block.
- Month names without a year refer to all years, e.g. January is
  `EXTRACT(MONTH FROM DT_INTER) = 1`.
- For categorical dimensions, join the lookup table and return human-readable
  labels: `sexo`, `raca_cor`, `car_int`, `complexidade`, `especialidade`,
  `marca_uti`, `nacionalidade`, `vincprev`, `contraceptivos`, `municipios`.
- For top-N within each group, use `ROW_NUMBER() OVER (PARTITION BY ...)`.
- For population rates, aggregate admissions first, then join one
  `socioeconomico` row per municipality/year. Do not sum population after a
  fact-table join.
- Use DuckDB functions such as `EXTRACT`, `NTILE`, `MEDIAN`, `regexp_full_match`.
- Do not round averages unless the question explicitly asks for rounded values.
- For "valor total gasto em internacoes", use `ROUND(SUM(VAL_TOT), 0)`.
- For UTI cost/spending, use `SUM(VAL_UTI)` and filter `VAL_UTI > 0`; do not use
  `VAL_TOT` for UTI spending.
- "CID de morte preenchido" follows the benchmark contract:
  `CID_MORTE IS NOT NULL AND CID_MORTE <> '0'`.
- Common diagnosis shortcuts: diabetes is `DIAG_PRINC LIKE 'E10%' OR
  DIAG_PRINC LIKE 'E11%' OR DIAG_PRINC LIKE 'E12%' OR DIAG_PRINC LIKE 'E13%' OR
  DIAG_PRINC LIKE 'E14%'`; acute myocardial infarction is `DIAG_PRINC LIKE 'I21%'`.
- When matching CID categories, use prefix `LIKE 'XNN%'` instead of equality to
  the three-character category code, unless the user asks for the exact code.

DATABASE CONTEXT:
{schema_context}
"""


def build_simple_schema_context() -> str:
    tables = _load_business_tables()
    table_inventory = _load_table_inventory()
    table_metadata = _load_table_metadata()
    columns_by_table = _load_columns_by_table()
    profiles_by_table = _load_column_profiles_by_table()
    top_values_by_table = _load_top_values_by_table()

    rendered: list[str] = []
    for table in tables:
        inventory = table_inventory.get(table, {})
        metadata = table_metadata.get(table, {})
        lines = [
            f"TABLE: {table}",
            "SCHEMA: main",
            f"ROLE: {inventory.get('classificacao') or 'business'}",
        ]
        if inventory.get("row_count"):
            lines.append(f"ROW_COUNT_ESTIMATE: {inventory['row_count']}")
        if metadata.get("sql"):
            lines.append(f"DDL: {metadata['sql']}")

        columns = columns_by_table.get(table, [])
        if columns:
            lines.append("COLUMNS:")
            lines.extend(_format_context_column(column, profiles_by_table.get(table, {})) for column in columns[:MAX_CONTEXT_COLUMNS_PER_TABLE])
            if len(columns) > MAX_CONTEXT_COLUMNS_PER_TABLE:
                lines.append(f"- ... {len(columns) - MAX_CONTEXT_COLUMNS_PER_TABLE} additional columns omitted")

        top_values = _format_top_values(top_values_by_table.get(table, {}))
        if top_values:
            lines.append("TOP_VALUES:")
            lines.extend(top_values)

        notes = DOMAIN_TABLE_NOTES.get(table)
        if notes:
            lines.append("DOMAIN_NOTES:")
            lines.extend(f"- {note}" for note in notes)

        rendered.append("\n".join(lines))

    return "\n\n".join(rendered) if rendered else "\n".join(tables)


def clean_llm_sql(sql: str) -> str:
    value = (sql or "").strip()
    if not value:
        return ""
    value = value.replace("```sql", "```").replace("```SQL", "```")
    if "```" in value:
        parts = [part.strip() for part in value.split("```") if part.strip()]
        value = next((part for part in parts if _looks_like_sql(part)), parts[0] if parts else "")
    for prefix in ("SQL:", "sql:", "Query:", "query:"):
        if value.startswith(prefix):
            value = value[len(prefix) :].strip()
    value = sanitize_sql_for_execution(value)
    if value and not value.endswith(";"):
        value += ";"
    return value


def _load_business_tables() -> list[str]:
    path = GENERATED_SCHEMA_DIR / "table_inventory.csv"
    if not path.exists():
        return [
            "internacoes",
            "internacao_procedimento",
            "cid",
            "procedimentos",
            "hospital",
            "municipios",
            "socioeconomico",
        ]

    tables: list[str] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            schema = (row.get("table_schema") or "").lower()
            table = (row.get("table_name") or "").strip()
            role = (row.get("classificacao") or "").lower()
            if schema != "main":
                continue
            if not table or table.startswith("stg_"):
                continue
            if role in {"dbt audit", "outro"}:
                continue
            tables.append(table)

    priority = [
        "internacoes",
        "internacao_procedimento",
        "cid",
        "procedimentos",
        "hospital",
        "municipios",
        "socioeconomico",
        "tempo",
    ]
    return sorted(set(tables), key=lambda table: (table not in priority, priority.index(table) if table in priority else table))


def _load_table_inventory() -> dict[str, dict[str, str]]:
    return _load_csv_by_table("table_inventory.csv")


def _load_table_metadata() -> dict[str, dict[str, str]]:
    return _load_csv_by_table("table_metadata.csv")


def _load_csv_by_table(filename: str) -> dict[str, dict[str, str]]:
    path = GENERATED_SCHEMA_DIR / filename
    if not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            table = (row.get("table_name") or "").strip()
            schema = (row.get("table_schema") or "main").lower()
            if schema == "main" and table:
                rows[table] = {key: value for key, value in row.items() if key}
    return rows


def _load_columns_by_table() -> dict[str, list[dict[str, str]]]:
    path = GENERATED_SCHEMA_DIR / "column_catalog.csv"
    if not path.exists():
        return {}
    columns_by_table: dict[str, list[dict[str, str]]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("table_schema") or "main").lower() != "main":
                continue
            table = (row.get("table_name") or "").strip()
            if not table:
                continue
            columns_by_table.setdefault(table, []).append(
                {
                    "name": row.get("column_name") or "",
                    "type": row.get("data_type") or "",
                    "nullable": row.get("is_nullable") or "",
                    "position": row.get("ordinal_position") or "",
                }
            )
    for columns in columns_by_table.values():
        columns.sort(key=lambda column: int(column["position"] or 0))
    return columns_by_table


def _load_column_profiles_by_table() -> dict[str, dict[str, dict[str, str]]]:
    path = GENERATED_SCHEMA_DIR / "column_profiles.csv"
    if not path.exists():
        return {}
    profiles: dict[str, dict[str, dict[str, str]]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("table_schema") or "main").lower() != "main":
                continue
            table = (row.get("table_name") or "").strip()
            column = (row.get("column_name") or "").strip()
            if table and column:
                profiles.setdefault(table, {})[column] = row
    return profiles


def _load_top_values_by_table() -> dict[str, dict[str, list[dict[str, str]]]]:
    path = GENERATED_SCHEMA_DIR / "top_frequent_values.csv"
    if not path.exists():
        return {}
    top_values: dict[str, dict[str, list[dict[str, str]]]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            table = (row.get("table_name") or "").strip()
            column = (row.get("column_name") or "").strip()
            if table and column:
                top_values.setdefault(table, {}).setdefault(column, []).append(row)
    return top_values


def _format_context_column(column: dict[str, str], profiles: dict[str, dict[str, str]]) -> str:
    name = column["name"]
    profile = profiles.get(name, {})
    extras: list[str] = []
    if profile.get("distinct_count_for_catalog"):
        extras.append(f"distinct={profile['distinct_count_for_catalog']}")
    if profile.get("null_rate"):
        extras.append(f"null_rate={profile['null_rate']}")
    if profile.get("min_value") or profile.get("max_value"):
        extras.append(f"range={profile.get('min_value', '')}..{profile.get('max_value', '')}")
    suffix = f"; {', '.join(extras)}" if extras else ""
    return f"- {name}: {column['type']}, nullable={column['nullable']}{suffix}"


def _format_top_values(top_values_by_column: dict[str, list[dict[str, str]]]) -> list[str]:
    lines: list[str] = []
    for column in sorted(top_values_by_column)[:MAX_TOP_VALUE_COLUMNS_PER_TABLE]:
        values = sorted(
            top_values_by_column[column],
            key=lambda row: int(row.get("rank") or 999),
        )[:MAX_TOP_VALUES_PER_COLUMN]
        rendered = ", ".join(
            f"{row.get('value', '')}={row.get('row_count', '')}" for row in values
        )
        if rendered:
            lines.append(f"- {column}: {rendered}")
    return lines


def _looks_like_sql(value: str) -> bool:
    ok, _reason = is_select_only(value)
    return ok


def _fallback_answer(execution: QueryExecution) -> str:
    if len(execution.rows) == 1 and len(execution.rows[0]) == 1:
        return f"O resultado e {execution.rows[0][0]}."
    return f"A consulta retornou {len(execution.rows)} linha(s)."


def _guess_tables_used(sql: str) -> list[str]:
    lowered = (sql or "").lower()
    tables = _load_business_tables()
    return [table for table in tables if table.lower() in lowered]


DOMAIN_TABLE_NOTES = {
    "internacoes": [
        "Fact table for hospital admissions; one row per N_AIH.",
        "Main dates: DT_INTER for admission date, DT_SAIDA for discharge date.",
        "Main amount fields: VAL_TOT for admission total, VAL_UTI for ICU cost.",
        "Principal diagnosis is DIAG_PRINC; death indicator is MORTE.",
    ],
    "internacao_procedimento": [
        "Fact table for procedures performed during admissions.",
        "Join to internacoes on N_AIH and to procedimentos on PROC_REA.",
    ],
    "cid": [
        "CID diagnosis lookup. CID joins to internacoes.DIAG_PRINC or CID_MORTE.",
        "Use prefix LIKE for CID categories and exact equality only for exact codes.",
    ],
    "procedimentos": [
        "Procedure lookup table. PROC_REA is the performed procedure code.",
    ],
    "municipios": [
        "Municipality lookup. Use human-readable municipality/UF columns when available.",
    ],
    "socioeconomico": [
        "Municipality/year socioeconomic indicators and population denominators.",
        "Aggregate admissions before joining population to avoid duplicated denominators.",
    ],
}
