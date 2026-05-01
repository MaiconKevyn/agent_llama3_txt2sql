from pydantic import BaseModel, Field


class SQLOutput(BaseModel):
    """Structured output for SQL generation."""

    sql: str = Field(description="Valid PostgreSQL SELECT query answering the user question")
    reasoning: str = Field(description="Brief explanation of table/filter choices (1-2 sentences)")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score 0-1; use <0.6 for uncertain queries",
    )


__all__ = ["SQLOutput"]
