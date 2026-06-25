"""Schema utility helpers: column parsing, alias resolution, and validation."""

import re
import difflib
from typing import Any, Dict, List


def _parse_schema_columns(schema_text: str) -> Dict[str, List[str]]:
    """Parse schema_context into {table: [columns]} using a lightweight parser."""
    if not schema_text:
        return {}
    tables: Dict[str, List[str]] = {}
    create_re = re.compile(r"CREATE\s+TABLE\s+([a-zA-Z_][\w]*)\s*\((.*?)\);", re.S | re.I)
    col_re = re.compile(r'^\s*(?:"(?P<qcol>[^"]+)"|(?P<col>[A-Za-z_][A-Za-z0-9_]*))\s+', re.M)
    for m in create_re.finditer(schema_text):
        table = (m.group(1) or "").strip()
        body = m.group(2) or ""
        cols: List[str] = []
        for cm in col_re.finditer(body):
            cname = cm.group('qcol') or cm.group('col')
            if cname and cname.upper() != 'CONSTRAINT':
                cols.append(cname)
        if cols:
            tables[table.lower()] = cols
    return tables


def _extract_alias_map(sql: str) -> Dict[str, str]:
    """Map aliases to base table names using FROM/JOIN clauses."""
    alias_map: Dict[str, str] = {}
    text = sql or ""
    for m in re.finditer(r"\bfrom\s+([a-zA-Z_][\w]*)\s+(?:as\s+)?([a-zA-Z_][\w]*)", text, flags=re.I):
        alias_map[m.group(2)] = m.group(1)
    for m in re.finditer(r"\bjoin\s+([a-zA-Z_][\w]*)\s+(?:as\s+)?([a-zA-Z_][\w]*)", text, flags=re.I):
        alias_map[m.group(2)] = m.group(1)
    return alias_map


def _extract_alias_columns(sql: str) -> List[tuple]:
    """Extract occurrences like alias.col or alias."COL"."""
    pairs: List[tuple] = []
    for m in re.finditer(r'\b([A-Za-z_][\w]*)\s*\.\s*(?:"([^"]+)"|([A-Za-z_][A-Za-z0-9_]*))', sql or ""):
        alias = m.group(1)
        col = m.group(2) or m.group(3)
        pairs.append((alias, col))
    return pairs


def _best_column_suggestions(missing_col: str, candidates: List[str], k: int = 3) -> List[str]:
    """Suggest k similar columns using difflib ratio and substring bonus."""
    if not candidates:
        return []
    target = (missing_col or "").lower()

    def score(c: str) -> float:
        c0 = (c or "").lower()
        r = difflib.SequenceMatcher(None, target, c0).ratio()
        if target in c0 or c0 in target:
            r += 0.1
        return r

    ranked = sorted(candidates, key=score, reverse=True)
    out, seen = [], set()
    for c in ranked:
        if c not in seen:
            out.append(c)
            seen.add(c)
        if len(out) >= k:
            break
    return out


def _check_columns_against_schema(schema_text: str, sql: str) -> Dict[str, Any]:
    """Check alias.column references against schema_context content."""
    schema_map = _parse_schema_columns(schema_text)
    alias_map = _extract_alias_map(sql)
    alias_cols = _extract_alias_columns(sql)
    missing = []
    suggestions: Dict[str, List[str]] = {}
    for alias, col in alias_cols:
        base = alias_map.get(alias)
        if not base:
            key = f"alias:{alias}"
            if key not in suggestions:
                missing.append((alias, col, None))
                suggestions[key] = []
            continue
        cols = schema_map.get((base or "").lower(), [])
        if col not in cols and col.upper() not in [c.upper() for c in cols]:
            missing.append((alias, col, base))
            suggestions[f"{alias}.{col}"] = _best_column_suggestions(col, cols)
    return {
        "ok": len(missing) == 0,
        "issues": missing,
        "suggestions": suggestions,
        "alias_map": alias_map,
        "schema_map": schema_map,
    }
