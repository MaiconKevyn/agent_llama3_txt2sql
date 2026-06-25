"""LlamaIndex schema/domain retrieval for the early Text-to-SQL pipeline."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..application.config.table_descriptions import TABLE_DESCRIPTIONS
from ..application.prompts.table_selection.catalog import (
    render_table_description_lines,
)

LLAMAINDEX_MODE_CURRENT = "current"
LLAMAINDEX_MODE_CONTEXT = "context"
LLAMAINDEX_MODE_SQL_DRAFT = "sql_draft"
LLAMAINDEX_MODE_HYBRID = "hybrid"

_MODE_ALIASES = {
    "current": LLAMAINDEX_MODE_CURRENT,
    "none": LLAMAINDEX_MODE_CURRENT,
    "off": LLAMAINDEX_MODE_CURRENT,
    "context": LLAMAINDEX_MODE_CONTEXT,
    "llamaindex_context": LLAMAINDEX_MODE_CONTEXT,
    "sql_draft": LLAMAINDEX_MODE_SQL_DRAFT,
    "llamaindex_sql_draft": LLAMAINDEX_MODE_SQL_DRAFT,
    "hybrid": LLAMAINDEX_MODE_HYBRID,
    "hybrid_context_current_generator": LLAMAINDEX_MODE_HYBRID,
}

_GENERATED_SCHEMA_FILES = (
    "table_metadata.csv",
    "column_catalog.csv",
    "column_profiles_exact.csv",
    "column_profiles_approx.csv",
    "join_policy.csv",
)
_INDEX_SOURCE_MANIFEST = "txt2sql_llamaindex_source.json"
_BLOCKED_RUNTIME_TABLE_PREFIXES = (
    "stg_",
    "source_",
    "relationships_",
    "not_null_",
    "accepted_values_",
    "dbt_",
)


@dataclass
class SimpleSchemaDocument:
    """Small document fallback used when LlamaIndex is unavailable."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_content(self, *_args: Any, **_kwargs: Any) -> str:
        return self.text


@dataclass
class LlamaIndexRetrievedContext:
    selected_tables: list[str] = field(default_factory=list)
    table_context: list[str] = field(default_factory=list)
    schema_context: str = ""
    retrieval_mode: str = "llamaindex_schema"
    confidence: float = 0.0
    error: str = ""


@dataclass(frozen=True)
class GeneratedSchemaDocuments:
    docs_by_table: dict[str, str] = field(default_factory=dict)
    source_dir: Path | None = None
    source_fingerprint: str = ""


def normalize_llamaindex_mode(mode: str | None) -> str:
    """Return the canonical LlamaIndex mode name."""
    key = (mode or LLAMAINDEX_MODE_CURRENT).strip().lower()
    return _MODE_ALIASES.get(key, key)


def should_use_llamaindex_context(flags: dict[str, Any] | None) -> bool:
    flags = flags or {}
    mode = normalize_llamaindex_mode(str(flags.get("llamaindex_mode", "current")))
    return bool(flags.get("enable_llamaindex_context")) or mode in {
        LLAMAINDEX_MODE_CONTEXT,
        LLAMAINDEX_MODE_SQL_DRAFT,
        LLAMAINDEX_MODE_HYBRID,
    }


def should_use_llamaindex_sql_draft(flags: dict[str, Any] | None) -> bool:
    flags = flags or {}
    mode = normalize_llamaindex_mode(str(flags.get("llamaindex_mode", "current")))
    return bool(flags.get("enable_llamaindex_sql_draft")) or mode == LLAMAINDEX_MODE_SQL_DRAFT


def _stringify_items(values: Any, *, max_items: int = 8) -> str:
    if not values:
        return ""
    if isinstance(values, dict):
        items = [f"{key}: {value}" for key, value in list(values.items())[:max_items]]
        return "; ".join(items)
    if isinstance(values, (list, tuple, set)):
        return "; ".join(str(item) for item in list(values)[:max_items])
    return str(values)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _generated_schema_dir() -> Path:
    raw_path = os.getenv("LLAMAINDEX_SCHEMA_DOCS_DIR", "src/application/schema/generated")
    path = Path(raw_path)
    return path if path.is_absolute() else _project_root() / path


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def _safe_int(value: str | None) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except ValueError:
        return 0


def _row_table_name(row: dict[str, str]) -> str:
    return row.get("table_name", "").strip()


def _split_qualified_column(value: str) -> tuple[str, str]:
    parts = value.split(".", maxsplit=1)
    if len(parts) != 2:
        return value, ""
    return parts[0], parts[1]


def _is_runtime_business_table(table_name: str) -> bool:
    return bool(table_name) and not table_name.startswith(_BLOCKED_RUNTIME_TABLE_PREFIXES)


def _generated_source_fingerprint(available_tables: list[str], docs_dir: Path) -> str:
    digest = hashlib.sha256()
    digest.update("\n".join(sorted(available_tables)).encode("utf-8"))
    digest.update(
        json.dumps(
            {table: TABLE_DESCRIPTIONS.get(table, {}) for table in sorted(available_tables)},
            ensure_ascii=True,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    )
    for filename in _GENERATED_SCHEMA_FILES:
        path = docs_dir / filename
        digest.update(filename.encode("utf-8"))
        if path.exists():
            digest.update(path.read_bytes())
        else:
            digest.update(b"<missing>")
    return digest.hexdigest()


def _format_generated_columns(rows: list[dict[str, str]], *, max_columns: int = 80) -> str:
    lines: list[str] = []
    for row in sorted(rows, key=lambda item: _safe_int(item.get("ordinal_position")))[:max_columns]:
        column = row.get("column_name", "")
        data_type = row.get("data_type", "")
        nullable = row.get("is_nullable", "")
        lines.append(f"- {column}: {data_type}, nullable={nullable}")
    if len(rows) > max_columns:
        lines.append(f"- ... {len(rows) - max_columns} additional columns omitted")
    return "\n".join(lines)


def _format_generated_profiles(rows: list[dict[str, str]], *, max_profiles: int = 30) -> str:
    lines: list[str] = []
    for row in rows[:max_profiles]:
        lines.append(
            "- {column}: type={data_type}, rows={row_count}, null_rate={null_rate}, "
            "distinct={distinct}, min={min_value}, max={max_value}, mode={mode}".format(
                column=row.get("column_name", ""),
                data_type=row.get("data_type", ""),
                row_count=row.get("row_count", ""),
                null_rate=row.get("null_rate", ""),
                distinct=row.get("distinct_count_for_catalog", ""),
                min_value=row.get("min_value", ""),
                max_value=row.get("max_value", ""),
                mode=row.get("profile_mode", ""),
            )
        )
    if len(rows) > max_profiles:
        lines.append(f"- ... {len(rows) - max_profiles} additional profiled columns omitted")
    return "\n".join(lines)


def _format_generated_join_policies(rows: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for row in rows:
        lines.append(
            "- {left} -> {right}: {meaning}; confidence={confidence}; "
            "policy={policy}; unmatched_rows={unmatched}".format(
                left=row.get("left", ""),
                right=row.get("right", ""),
                meaning=row.get("business_meaning", ""),
                confidence=row.get("confidence", ""),
                policy=row.get("accepted_usage_policy", ""),
                unmatched=row.get("unmatched_rows", ""),
            )
        )
    return "\n".join(lines)


def _load_generated_schema_documents(available_tables: list[str]) -> GeneratedSchemaDocuments:
    docs_dir = _generated_schema_dir()
    source_fingerprint = _generated_source_fingerprint(available_tables, docs_dir)
    table_rows = _read_csv_rows(docs_dir / "table_metadata.csv")
    column_rows = _read_csv_rows(docs_dir / "column_catalog.csv")
    if not table_rows or not column_rows:
        return GeneratedSchemaDocuments(
            source_dir=docs_dir,
            source_fingerprint=source_fingerprint,
        )

    available = set(available_tables)
    metadata_by_table = {
        _row_table_name(row): row
        for row in table_rows
        if row.get("schema_name", "main") == "main"
        and _row_table_name(row) in available
        and _is_runtime_business_table(_row_table_name(row))
    }

    columns_by_table: dict[str, list[dict[str, str]]] = {}
    for row in column_rows:
        table_name = _row_table_name(row)
        if table_name in metadata_by_table:
            columns_by_table.setdefault(table_name, []).append(row)

    profile_rows = _read_csv_rows(docs_dir / "column_profiles_exact.csv")
    profile_rows.extend(_read_csv_rows(docs_dir / "column_profiles_approx.csv"))
    profiles_by_table: dict[str, list[dict[str, str]]] = {}
    for row in profile_rows:
        table_name = _row_table_name(row)
        if table_name in metadata_by_table:
            profiles_by_table.setdefault(table_name, []).append(row)

    joins_by_table: dict[str, list[dict[str, str]]] = {}
    for row in _read_csv_rows(docs_dir / "join_policy.csv"):
        left_table, _ = _split_qualified_column(row.get("left", ""))
        right_table, _ = _split_qualified_column(row.get("right", ""))
        for table_name in {left_table, right_table}:
            if table_name in metadata_by_table:
                joins_by_table.setdefault(table_name, []).append(row)

    docs_by_table: dict[str, str] = {}
    for table_name, metadata in sorted(metadata_by_table.items()):
        desc = TABLE_DESCRIPTIONS.get(table_name, {})
        description_lines: list[str] = []
        for variant in ("role_guardrails", "schema_contract"):
            try:
                rendered = render_table_description_lines([table_name], description_variant=variant)
                description_lines.extend(rendered)
            except Exception:
                continue

        parts = [
            f"TABLE: {table_name}",
            "SOURCE: src/application/schema/generated",
            f"SCHEMA: {metadata.get('schema_name', 'main')}",
            f"ROW_COUNT_ESTIMATE: {metadata.get('estimated_size', '')}",
            f"COLUMN_COUNT: {metadata.get('column_count', '')}",
            f"HAS_PRIMARY_KEY: {metadata.get('has_primary_key', '')}",
            f"INDEX_COUNT: {metadata.get('index_count', '')}",
            f"CHECK_CONSTRAINT_COUNT: {metadata.get('check_constraint_count', '')}",
            f"CURATED_TITLE: {desc.get('title', table_name)}",
            f"CURATED_PURPOSE: {desc.get('purpose', '')}",
            f"CURATED_DESCRIPTION: {desc.get('description', '')}",
            f"KEY_COLUMNS: {_stringify_items(desc.get('key_columns'), max_items=40)}",
            f"VALUE_MAPPINGS: {_stringify_items(desc.get('value_mappings'), max_items=40)}",
            f"CRITICAL_NOTES: {_stringify_items(desc.get('critical_notes'), max_items=20)}",
            f"CURATED_RELATIONSHIPS: {_stringify_items(desc.get('relationships'), max_items=20)}",
            "COLUMNS:\n" + _format_generated_columns(columns_by_table.get(table_name, [])),
        ]
        profiles_text = _format_generated_profiles(profiles_by_table.get(table_name, []))
        if profiles_text:
            parts.append("PROFILED_COLUMNS:\n" + profiles_text)
        joins_text = _format_generated_join_policies(joins_by_table.get(table_name, []))
        if joins_text:
            parts.append("JOIN_POLICIES:\n" + joins_text)
        if description_lines:
            parts.append("TABLE_SELECTION_HINTS:\n" + "\n".join(description_lines))
        docs_by_table[table_name] = "\n".join(part for part in parts if part.strip())

    return GeneratedSchemaDocuments(
        docs_by_table=docs_by_table,
        source_dir=docs_dir,
        source_fingerprint=source_fingerprint,
    )


def _table_document_text(table_name: str) -> str:
    desc = TABLE_DESCRIPTIONS.get(table_name, {})
    description_lines: list[str] = []
    for variant in ("role_guardrails", "schema_contract"):
        try:
            rendered = render_table_description_lines([table_name], description_variant=variant)
            description_lines.extend(rendered)
        except Exception:
            continue

    parts = [
        f"TABLE: {table_name}",
        f"TITLE: {desc.get('title', table_name)}",
        f"PURPOSE: {desc.get('purpose', '')}",
        f"DESCRIPTION: {desc.get('description', '')}",
        f"KEY_COLUMNS: {_stringify_items(desc.get('key_columns'), max_items=40)}",
        f"VALUE_MAPPINGS: {_stringify_items(desc.get('value_mappings'), max_items=40)}",
        f"CRITICAL_NOTES: {_stringify_items(desc.get('critical_notes'), max_items=20)}",
        f"RELATIONSHIPS: {_stringify_items(desc.get('relationships'), max_items=20)}",
    ]
    if description_lines:
        parts.append("TABLE_SELECTION_HINTS: " + "\n".join(description_lines))
    return "\n".join(part for part in parts if part.strip())


def build_llamaindex_schema_documents(available_tables: list[str]) -> list[object]:
    """Build one schema/domain document per available table.

    When ``src/application/schema/generated`` is available, it is the primary source because it
    carries the live schema catalog, profiled columns, and join policy evidence.
    ``TABLE_DESCRIPTIONS`` remains an overlay/fallback for curated domain notes.

    The function returns LlamaIndex ``Document`` objects when the package is
    installed and lightweight local documents otherwise, so tests and fallback
    behavior do not require optional dependencies.
    """
    try:
        from llama_index.core import Document

        document_cls: Any = Document
    except Exception:
        document_cls = SimpleSchemaDocument

    generated = _load_generated_schema_documents(available_tables)
    if generated.docs_by_table:
        table_docs = generated.docs_by_table
    else:
        table_docs = {
            table_name: _table_document_text(table_name) for table_name in available_tables
        }

    documents: list[object] = []
    for table_name, text in table_docs.items():
        metadata = {
            "table_name": table_name,
            "source": "src/application/schema/generated"
            if generated.docs_by_table
            else "table_descriptions",
            "source_fingerprint": generated.source_fingerprint,
        }
        if document_cls is SimpleSchemaDocument:
            documents.append(SimpleSchemaDocument(text=text, metadata=metadata))
        else:
            documents.append(document_cls(text=text, metadata=metadata))
    return documents


def _unavailable_context(error: str) -> LlamaIndexRetrievedContext:
    return LlamaIndexRetrievedContext(
        selected_tables=[],
        table_context=[],
        schema_context="",
        retrieval_mode="llamaindex_unavailable",
        confidence=0.0,
        error=error,
    )


def _index_source_changed(persist_dir: Path, source_fingerprint: str) -> bool:
    manifest_path = persist_dir / _INDEX_SOURCE_MANIFEST
    if not manifest_path.exists():
        return True
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    return manifest.get("source_fingerprint") != source_fingerprint


def _write_index_source_manifest(persist_dir: Path, source_fingerprint: str) -> None:
    manifest_path = persist_dir / _INDEX_SOURCE_MANIFEST
    manifest_path.write_text(
        json.dumps(
            {
                "source_fingerprint": source_fingerprint,
                "schema_docs_dir": str(_generated_schema_dir()),
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )


def retrieve_llamaindex_schema_context(
    user_query: str,
    available_tables: list[str],
    *,
    top_k_tables: int,
    index_dir: str,
    rebuild_index: bool = False,
) -> LlamaIndexRetrievedContext:
    """Retrieve table context with a persisted LlamaIndex vector index.

    This function never executes SQL. It only indexes static project metadata
    and returns table/context hints for downstream LangGraph nodes.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _unavailable_context("OPENAI_API_KEY not set")

    try:
        from llama_index.core import (
            Settings,
            StorageContext,
            VectorStoreIndex,
            load_index_from_storage,
        )
        from llama_index.embeddings.openai import OpenAIEmbedding
    except Exception as exc:
        return _unavailable_context(str(exc))

    try:
        persist_dir = Path(index_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)
        index_exists = (persist_dir / "index_store.json").exists()
        source_fingerprint = _generated_source_fingerprint(
            available_tables,
            _generated_schema_dir(),
        )
        source_changed = _index_source_changed(persist_dir, source_fingerprint)

        Settings.embed_model = OpenAIEmbedding(
            model=os.getenv("LLAMAINDEX_EMBED_MODEL", "text-embedding-3-small"),
            api_key=api_key,
        )

        if rebuild_index or not index_exists or source_changed:
            documents = build_llamaindex_schema_documents(available_tables)
            index = VectorStoreIndex.from_documents(documents)
            index.storage_context.persist(persist_dir=str(persist_dir))
            _write_index_source_manifest(persist_dir, source_fingerprint)
        else:
            storage_context = StorageContext.from_defaults(persist_dir=str(persist_dir))
            index = load_index_from_storage(storage_context)

        retriever = index.as_retriever(similarity_top_k=max(1, int(top_k_tables)))
        nodes = retriever.retrieve(user_query)

        selected_tables: list[str] = []
        table_context: list[str] = []
        scores: list[float] = []
        available = set(available_tables)
        for node in nodes:
            node_obj = getattr(node, "node", node)
            metadata = getattr(node_obj, "metadata", {}) or {}
            table_name = metadata.get("table_name")
            if table_name not in available:
                continue
            if table_name not in selected_tables:
                selected_tables.append(table_name)
            if hasattr(node_obj, "get_content"):
                table_context.append(node_obj.get_content())
            else:
                table_context.append(str(node_obj))
            score = getattr(node, "score", None)
            if isinstance(score, (int, float)):
                scores.append(float(score))

        confidence = sum(scores) / len(scores) if scores else (1.0 if selected_tables else 0.0)
        return LlamaIndexRetrievedContext(
            selected_tables=selected_tables,
            table_context=table_context,
            schema_context="\n\n".join(table_context),
            retrieval_mode="llamaindex_schema",
            confidence=confidence,
        )
    except Exception as exc:
        return _unavailable_context(str(exc))
