from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.orchestrator_support import resolve_database_url  # noqa: E402

RESULTS_DIR = Path("evaluation/cid_investigation/results")

CANONICAL_SQL = {
    "structure": """
        SELECT COUNT(*) AS total_cids, COUNT(DISTINCT CID) AS distinct_cids
        FROM cid
    """,
    "hierarchy": """
        SELECT
            COUNT(DISTINCT DS_CAPITULO) AS capitulos,
            COUNT(DISTINCT DS_GRUPO) AS grupos,
            COUNT(DISTINCT DS_CATEGORIA) AS categorias
        FROM cid
    """,
    "chapters": """
        SELECT DS_CAPITULO, COUNT(*) AS codigos
        FROM cid
        GROUP BY DS_CAPITULO
        ORDER BY codigos DESC, DS_CAPITULO
        LIMIT 30
    """,
    "pneumonia_lookup": """
        SELECT CID, DESCRICAO, DS_CATEGORIA, DS_GRUPO, DS_CAPITULO
        FROM cid
        WHERE lower(DESCRICAO) LIKE '%pneumonia%'
           OR lower(DS_CATEGORIA) LIKE '%pneumonia%'
           OR lower(DS_GRUPO) LIKE '%pneumonia%'
        ORDER BY CID
        LIMIT 100
    """,
    "internacoes_by_chapter": """
        SELECT c.DS_CAPITULO, COUNT(*) AS internacoes
        FROM internacoes i
        JOIN cid c ON i.DIAG_PRINC = c.CID
        GROUP BY c.DS_CAPITULO
        ORDER BY internacoes DESC
        LIMIT 20
    """,
    "join_quality": """
        SELECT
            COUNT(*) AS internacoes,
            COUNT(*) FILTER (WHERE i.DIAG_PRINC IS NOT NULL) AS com_diag_principal,
            COUNT(*) FILTER (WHERE i.DIAG_PRINC IS NOT NULL AND c.CID IS NULL) AS sem_match_cid
        FROM internacoes i
        LEFT JOIN cid c ON i.DIAG_PRINC = c.CID
    """,
}

SEARCH_TERMS = [
    "pneumonia",
    "tuberculose",
    "diabetes",
    "hipertens",
    "infarto",
    "neoplas",
    "dengue",
    "asma",
    "renal",
    "gravidez",
]


def rows_as_dicts(result: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in result.mappings().all()]


def build_payload() -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    engine = create_engine(resolve_database_url(None))
    payload: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "database_url": resolve_database_url(None),
        "canonical": {},
        "term_samples": {},
    }

    with engine.connect() as connection:
        for name, sql in CANONICAL_SQL.items():
            payload["canonical"][name] = rows_as_dicts(connection.execute(text(sql)))

        for term in SEARCH_TERMS:
            sql = text(
                """
                SELECT CID, DESCRICAO, DS_CATEGORIA, DS_GRUPO, DS_CAPITULO
                FROM cid
                WHERE lower(DESCRICAO) LIKE :pattern
                   OR lower(DS_CATEGORIA) LIKE :pattern
                   OR lower(DS_GRUPO) LIKE :pattern
                   OR lower(DS_CAPITULO) LIKE :pattern
                ORDER BY CID
                LIMIT 100
                """
            )
            payload["term_samples"][term] = rows_as_dicts(
                connection.execute(sql, {"pattern": f"%{term}%"})
            )

    return payload


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    output = RESULTS_DIR / f"cid_baseline_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
