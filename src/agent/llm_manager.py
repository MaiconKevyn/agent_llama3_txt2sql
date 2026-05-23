import os
from typing import Any

from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from ..application.config.simple_config import ApplicationConfig
from ..utils.logging_config import get_llm_manager_logger
from ..utils.sql_safety import is_select_only, sanitize_sql_for_execution
from .runtime_budget import record_llm_call

logger = get_llm_manager_logger()


class OpenAILLMManager:
    """
    OpenAI-only LLM manager responsible for:
    - Creating ChatOpenAI client
    - Wiring SQLDatabase + SQLDatabaseToolkit tools
    - Exposing convenience helpers for SQL generation/execution
    """

    def __init__(self, config: ApplicationConfig):
        self.config = config
        self._llm: BaseChatModel | None = None
        self._bound_llm = None
        self._sql_database: SQLDatabase | None = None
        self._sql_toolkit: SQLDatabaseToolkit | None = None

        self._initialize_database()
        self._initialize_llm()
        self._initialize_sql_toolkit()
        self._bind_tools()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def _initialize_database(self):
        db_path = self.config.database_path or ""
        if not (db_path.startswith("postgresql") or db_path.startswith("duckdb")):
            raise ValueError("Defina DATABASE_PATH ou DATABASE_URL com uma URL DuckDB válida")

        # Normalize psycopg2 style
        if db_path.startswith("postgresql+psycopg2://"):
            db_path = db_path.replace("postgresql+psycopg2://", "postgresql://", 1)

        redacted = db_path
        try:
            if "://" in db_path and "@" in db_path:
                scheme, rest = db_path.split("://", 1)
                after_at = rest.split("@", 1)[1]
                redacted = f"{scheme}://****@{after_at}"
        except Exception:
            redacted = "[redacted]"

        logger.info("Connecting to database", extra={"connection_string": redacted})

        self._sql_database = SQLDatabase.from_uri(db_path)
        table_names = self._sql_database.get_usable_table_names()
        if not table_names:
            raise ValueError("No usable tables found in database")

    def _initialize_llm(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")

        self._llm = ChatOpenAI(
            model=self.config.llm_model,
            temperature=self.config.llm_temperature,
            timeout=self.config.llm_timeout,
            max_retries=self.config.llm_max_retries,
            api_key=api_key,
            seed=42,
        )

        logger.info("OpenAI LLM initialized", extra={"model": self.config.llm_model})

    def _initialize_sql_toolkit(self):
        if not self._llm or not self._sql_database:
            raise ValueError("LLM and database must be initialized first")

        self._sql_toolkit = SQLDatabaseToolkit(db=self._sql_database, llm=self._llm)
        self._enhanced_tools = self._create_enhanced_tools(self._sql_toolkit.get_tools())
        logger.info(
            "SQLDatabaseToolkit initialized", extra={"tool_count": len(self._enhanced_tools)}
        )

    def _create_enhanced_tools(self, standard_tools: list[BaseTool]) -> list[BaseTool]:
        try:
            from .tools.enhanced_list_tables_tool import EnhancedListTablesTool

            tools = [tool for tool in standard_tools if tool.name != "sql_db_list_tables"]
            tools.append(EnhancedListTablesTool(db=self._sql_database))
            logger.info("Enhanced list_tables tool installed", extra={"count": len(tools)})
            return tools
        except Exception as e:
            logger.warning("Falling back to standard tools", extra={"error": str(e)})
            return standard_tools

    def _bind_tools(self):
        tools = self.get_sql_tools()
        self._bound_llm = self._llm.bind_tools(tools)
        logger.info("Tools bound to LLM", extra={"tool_count": len(tools)})

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    def get_sql_tools(self) -> list[BaseTool]:
        return getattr(self, "_enhanced_tools", []) or (
            self._sql_toolkit.get_tools() if self._sql_toolkit else []
        )

    def get_bound_llm(self) -> BaseChatModel:
        return self._bound_llm or self._llm

    def get_database(self) -> SQLDatabase:
        return self._sql_database

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def create_messages(
        self,
        user_query: str,
        system_prompt: str | None = None,
        conversation_history: list[BaseMessage] | None = None,
    ) -> list[BaseMessage]:
        messages: list[BaseMessage] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        if conversation_history:
            messages.extend(conversation_history)
        messages.append(HumanMessage(content=user_query))
        return messages

    def invoke_with_tools(
        self, messages: list[BaseMessage], max_iterations: int = 5
    ) -> dict[str, Any]:
        llm = self.get_bound_llm()
        record_llm_call("tool_bound_chat")
        response = llm.invoke(messages)
        tool_calls = getattr(response, "tool_calls", []) or []
        return {
            "response": response,
            "messages": messages + [response],
            "tool_calls": tool_calls,
            "has_tool_calls": len(tool_calls) > 0,
        }

    def generate_sql_query(
        self,
        user_query: str,
        schema_context: str,
        conversation_history: list[BaseMessage] | None = None,
    ) -> dict[str, Any]:
        system_prompt = f"""You are a SQL expert assistant for Brazilian healthcare (SUS) data.

Database Schema:
{schema_context}

Rules:
1. Generate syntactically correct DuckDB SQL.
2. Use table/column names exactly.
3. Answer in SQL only.
4. Default LIMIT 100 when missing.
"""

        messages = self.create_messages(user_query, system_prompt, conversation_history)
        result = self.invoke_with_tools(messages)

        if result.get("has_tool_calls"):
            for call in result["tool_calls"]:
                if call.get("name") in {"sql_db_query", "sql_db_query_checker"}:
                    sql_query = call.get("args", {}).get("query", "")
                    return {
                        "success": True,
                        "sql_query": self._clean_sql_query(sql_query),
                        "messages": result["messages"],
                        "tool_calls": result["tool_calls"],
                        "error": None,
                    }

        content = getattr(result["response"], "content", "") or ""
        return {
            "success": True,
            "sql_query": self._clean_sql_query(content),
            "messages": result["messages"],
            "tool_calls": result["tool_calls"],
            "error": None,
        }

    def generate_conversational_response(
        self,
        user_query: str,
        context: str | None = None,
        conversation_history: list[BaseMessage] | None = None,
    ) -> dict[str, Any]:
        system_prompt = f"""You are a helpful assistant for Brazilian healthcare (SUS) data analysis.
Answer in Portuguese, be concise.
{f"Contexto: {context}" if context else ""}
        """
        messages = self.create_messages(user_query, system_prompt, conversation_history)
        record_llm_call("conversational_chat")
        response = self.get_bound_llm().invoke(messages)
        return {
            "success": True,
            "response": getattr(response, "content", str(response)),
            "messages": messages + [response],
            "error": None,
        }

    def invoke_chat(self, messages: list[BaseMessage]):
        """Simple chat invocation without provider branching (OpenAI only)."""
        record_llm_call("chat")
        return self._llm.invoke(messages)

    def invoke_chat_structured(self, messages: list[BaseMessage], output_schema):
        """Invoke LLM with structured output schema (Pydantic model).

        Returns an instance of output_schema populated by the LLM, or raises
        on failure so callers can fall back to text-based parsing.
        """
        structured_llm = self._llm.with_structured_output(output_schema)
        record_llm_call("structured_chat")
        return structured_llm.invoke(messages)

    def validate_sql_query(self, sql_query: str) -> dict[str, Any]:
        if not self._sql_database or not hasattr(self._sql_database, "_engine"):
            return {"is_valid": False, "error": "Database not initialized", "suggestions": []}

        from sqlalchemy import text

        engine = self._sql_database._engine
        cleaned_sql = sanitize_sql_for_execution(sql_query)
        try:
            with engine.connect() as conn:
                conn.execute(text(f"EXPLAIN {cleaned_sql}"))
            return {"is_valid": True, "error": None, "suggestions": []}
        except Exception as e:
            suggestions = ["Verifique nomes de tabelas/colunas", "Revise a sintaxe SQL"]
            return {"is_valid": False, "error": str(e), "suggestions": suggestions}

    def execute_sql_query(self, sql_query: str) -> dict[str, Any]:
        if not self._sql_database:
            return {
                "success": False,
                "results": [],
                "error": "Database not initialized",
                "row_count": 0,
            }

        ok, reason = is_select_only(sql_query)
        if not ok:
            return {
                "success": False,
                "results": [],
                "error": f"SQL execution blocked: {reason}",
                "row_count": 0,
            }

        cleaned_sql = sanitize_sql_for_execution(sql_query)
        try:
            result = self._sql_database.run(cleaned_sql)
            if isinstance(result, str):
                rows = []
                for line in result.strip().split("\n"):
                    if line.strip():
                        rows.append({"result": line.strip()})
                return {"success": True, "results": rows, "error": None, "row_count": len(rows)}
            return {
                "success": True,
                "results": result if isinstance(result, list) else [result],
                "error": None,
                "row_count": len(result) if isinstance(result, list) else 1,
            }
        except Exception as e:
            return {"success": False, "results": [], "error": str(e), "row_count": 0}

    def _clean_sql_query(self, sql_query: str) -> str:
        if not sql_query:
            return ""
        sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
        # Strip EXPLAIN prefix that LLM occasionally adds
        if sql_query.upper().startswith("EXPLAIN "):
            sql_query = sql_query[8:].strip()
        if not sql_query.endswith(";"):
            sql_query += ";"
        return sanitize_sql_for_execution(sql_query)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    def get_model_info(self) -> dict[str, Any]:
        return {
            "provider": "openai",
            "model_name": self.config.llm_model,
            "temperature": self.config.llm_temperature,
            "timeout": self.config.llm_timeout,
            "available": True,
            "tools_bound": self._bound_llm is not None,
            "database_connected": self._sql_database is not None,
        }

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self._llm and self._sql_database else "degraded",
            "components": {
                "llm_status": "healthy" if self._llm else "failed",
                "database_status": "healthy" if self._sql_database else "failed",
                "toolkit_status": "healthy" if self._sql_toolkit else "failed",
                "tools_bound": "yes" if self._bound_llm else "no",
            },
            "model_info": self.get_model_info(),
        }


def create_openai_llm_manager(config: ApplicationConfig) -> OpenAILLMManager:
    return OpenAILLMManager(config)


# ---------------------------------------------------------------------------
# Global singleton — set by orchestrator, used by all nodes
# ---------------------------------------------------------------------------
_llm_manager: OpenAILLMManager | None = None


def set_global_llm_manager(manager: "OpenAILLMManager") -> None:
    """Set the global LLM manager instance (called by orchestrator)."""
    global _llm_manager
    _llm_manager = manager
    logger.info(
        "Global LLM manager updated",
        extra={
            "provider": manager.config.llm_provider,
            "model": manager.config.llm_model,
        },
    )


def get_llm_manager() -> "OpenAILLMManager":
    """Return the global LLM manager, creating a default instance if needed."""
    global _llm_manager
    if _llm_manager is None:
        logger.warning(
            "LLM Manager not initialized by orchestrator, using default config",
            extra={"fallback": True},
        )
        _llm_manager = OpenAILLMManager(ApplicationConfig())
    return _llm_manager
