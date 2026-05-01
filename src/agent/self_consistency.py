import concurrent.futures
import os
from typing import Dict, List, Optional

from langchain_openai import ChatOpenAI

from .schemas import SQLOutput
from ..utils.logging_config import get_nodes_logger

logger = get_nodes_logger()

N_SQL_CANDIDATES = 3
TEMPERATURE_CANDIDATES = 0.1
SEED_CANDIDATES = 42


def generate_sql_candidates(
    formatted_messages: list,
    llm_manager,
    primary_sql: str,
    primary_confidence: float,
    n: int = N_SQL_CANDIDATES,
) -> List[Dict]:
    """Generate N SQL candidates in parallel for majority voting."""
    candidates: List[Dict] = [{"sql": primary_sql, "confidence": primary_confidence}]

    if n <= 1:
        return candidates

    api_key = os.getenv("OPENAI_API_KEY")
    diverse_llm = ChatOpenAI(
        model=llm_manager.config.llm_model,
        temperature=TEMPERATURE_CANDIDATES,
        seed=SEED_CANDIDATES,
        api_key=api_key,
    ).with_structured_output(SQLOutput)

    def _one(_) -> Optional[Dict]:
        try:
            result = diverse_llm.invoke(formatted_messages)
            sql = llm_manager._clean_sql_query(result.sql)
            return {"sql": sql, "confidence": result.confidence} if sql else None
        except Exception as exc:
            logger.debug("Candidate generation failed", extra={"error": str(exc)})
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=n - 1) as pool:
        futures = [pool.submit(_one, index) for index in range(n - 1)]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result and result.get("sql"):
                candidates.append(result)

    logger.info(
        "SQL candidates generated",
        extra={"n_requested": n, "n_generated": len(candidates)},
    )
    return candidates


__all__ = [
    "N_SQL_CANDIDATES",
    "SEED_CANDIDATES",
    "TEMPERATURE_CANDIDATES",
    "generate_sql_candidates",
]
