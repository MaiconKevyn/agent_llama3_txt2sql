#!/usr/bin/env python3
"""
Targeted test script for queries identified as likely failing due to:
  - UTI detection (VAL_UTI > 0 vs ESPEC BETWEEN 74 AND 83)
  - Death cause policy (DIAG_PRINC + MORTE=true)
  - socioeconomico table selection and wide-format indicator columns
"""

import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

import os
import psycopg2

from src.agent.orchestrator import LangGraphOrchestrator
from src.application.config.simple_config import ApplicationConfig
from evaluation.metrics.execution_accuracy import ExecutionAccuracyMetric
from evaluation.metrics.base_metrics import EvaluationContext, MetricResult

# ------------------------------------------------------------------
# Queries under test (subset of ground_truth.json)
# ------------------------------------------------------------------
TARGET_QUERIES = [
    # --- UTI: must use VAL_UTI > 0 ---
    {
        "id": "GT007", "difficulty": "easy",
        "question": "Quantos registros de internação em UTI existem?",
        "query": 'SELECT COUNT(*) AS total_uti FROM internacoes WHERE "VAL_UTI" > 0;',
        "category": "UTI detection",
    },
    {
        "id": "GT023", "difficulty": "hard",
        "question": "Quantas internações de UTI resultaram em óbito?",
        "query": 'SELECT COUNT(*) AS uti_com_obito FROM internacoes WHERE "VAL_UTI" > 0 AND "MORTE" = true;',
        "category": "UTI detection",
    },
    {
        "id": "GT027", "difficulty": "hard",
        "question": "Quantas internações obstétricas foram registradas em UTI?",
        "query": 'SELECT COUNT(*) AS obstetricos_uti FROM internacoes WHERE "ESPEC" = 2 AND "VAL_UTI" > 0;',
        "category": "UTI detection",
    },
    {
        "id": "GT030", "difficulty": "medium",
        "question": "Qual é o valor médio de UTI para homens?",
        "query": 'SELECT AVG("VAL_UTI") AS valor_medio_uti_homens FROM internacoes WHERE "SEXO" = 1 AND "VAL_UTI" > 0;',
        "category": "UTI detection",
    },
    {
        "id": "GT044", "difficulty": "hard",
        "question": "Quantos hospitais atenderam casos de UTI em 2020?",
        "query": 'SELECT COUNT(DISTINCT "CNES") FROM internacoes WHERE "VAL_UTI" > 0 AND EXTRACT(YEAR FROM "DT_INTER") = 2020;',
        "category": "UTI detection",
    },
    # --- Death cause policy: DIAG_PRINC + MORTE=true ---
    {
        "id": "GT014", "difficulty": "medium",
        "question": "Quantas internações por meningite ocasionaram em morte?",
        "query": 'SELECT COUNT(*) FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" WHERE c."DESCRICAO" ILIKE \'%meningite%\' AND i."MORTE" = true;',
        "category": "Death cause policy",
    },
    {
        "id": "GT042", "difficulty": "medium",
        "question": "Quais são as três causas de morte mais frequentes entre mulheres?",
        "query": 'SELECT c."DESCRICAO", COUNT(*) AS total_mortes FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" WHERE i."SEXO" = 3 AND i."MORTE" = true AND i."DIAG_PRINC" IS NOT NULL GROUP BY c."DESCRICAO" ORDER BY total_mortes DESC LIMIT 3;',
        "category": "Death cause policy",
    },
    {
        "id": "GT052", "difficulty": "hard",
        "question": "Quais são as 10 principais causas de morte (com descrição)?",
        "query": 'SELECT c."DESCRICAO", COUNT(*) AS total_mortes FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" WHERE i."MORTE" = true GROUP BY c."DESCRICAO" ORDER BY total_mortes DESC LIMIT 10;',
        "category": "Death cause policy",
    },
    # --- socioeconomico table ---
    {
        "id": "GT006", "difficulty": "easy",
        "question": "Quantos municípios têm dados socioeconômicos registrados?",
        "query": 'SELECT COUNT(DISTINCT "CO_MUNICIPIO_6D") AS total_municipios FROM socioeconomico;',
        "category": "socioeconomico",
    },
    {
        "id": "GT018", "difficulty": "medium",
        "question": "Qual município tem a maior população segundo dados do IBGE?",
        "query": 'SELECT mu."NO_MUNICIPIO" AS municipio_maior_populacao FROM socioeconomico s JOIN municipios mu ON s."CO_MUNICIPIO_6D" = mu."CO_MUNICIPIO_6D" WHERE s."QT_POPULACAO" IS NOT NULL ORDER BY s."QT_POPULACAO" DESC LIMIT 1;',
        "category": "socioeconomico",
    },
    {
        "id": "GT043", "difficulty": "medium",
        "question": "Qual a taxa de mortalidade infantil média no Brasil?",
        "query": 'SELECT AVG("VL_MORT_INFANTIL") AS taxa_media_mortalidade_infantil FROM socioeconomico WHERE "VL_MORT_INFANTIL" IS NOT NULL;',
        "category": "socioeconomico",
    },
]


def run_agent_query(orchestrator, question: str) -> dict:
    """Run a single question through the agent and return the SQL + result."""
    try:
        start = time.time()
        response = orchestrator.process_query(question)
        elapsed = time.time() - start

        # Extract SQL from response metadata or content
        sql = None
        if hasattr(response, "get"):
            sql = response.get("generated_sql") or response.get("sql_query")
        if sql is None and hasattr(response, "generated_sql"):
            sql = response.generated_sql

        return {"sql": sql, "response": response, "elapsed": elapsed, "error": None}
    except Exception as e:
        return {"sql": None, "response": None, "elapsed": 0, "error": str(e)}


class _DBConn:
    """Minimal DB wrapper matching the interface expected by ExecutionAccuracyMetric."""
    def __init__(self, db_url: str):
        self.connection = psycopg2.connect(db_url)

    def execute_query(self, sql: str):
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql)
            results = cursor.fetchall()
            self.connection.commit()
            return results, None
        except Exception as e:
            self.connection.rollback()
            return None, str(e)

    def get_raw_connection(self):
        return self.connection

    def close(self):
        if self.connection:
            self.connection.close()


def main():
    print("\n" + "=" * 70)
    print("TARGETED QUERY TEST — post-fix validation")
    print("=" * 70)

    # Initialize DB connection
    db_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PATH")
    if not db_url:
        print("ERROR: DATABASE_URL not set in environment.")
        sys.exit(1)
    # Normalize driver prefix for psycopg2
    db_url = db_url.replace("postgresql+psycopg2://", "postgresql://")
    db_conn = _DBConn(db_url)

    # Initialize agent and metric
    config = ApplicationConfig()
    orchestrator = LangGraphOrchestrator(config)
    ex_metric = ExecutionAccuracyMetric()

    results_by_category: dict = {}
    total_pass = 0
    total_fail = 0

    current_category = None

    for item in TARGET_QUERIES:
        cat = item["category"]
        if cat != current_category:
            print(f"\n{'─'*70}")
            print(f"  CATEGORY: {cat}")
            print(f"{'─'*70}")
            current_category = cat

        print(f"\n[{item['id']}] ({item['difficulty']}) {item['question']}")
        print(f"  GT SQL: {item['query'][:100]}{'...' if len(item['query']) > 100 else ''}")

        result = run_agent_query(orchestrator, item["question"])

        if result["error"]:
            print(f"  ❌ AGENT ERROR: {result['error']}")
            total_fail += 1
            results_by_category.setdefault(cat, []).append(False)
            continue

        agent_sql = result["sql"]
        print(f"  AGENT SQL: {str(agent_sql)}")

        # Evaluate execution accuracy
        try:
            ctx = EvaluationContext(
                question_id=item["id"],
                question=item["question"],
                ground_truth_sql=item["query"],
                predicted_sql=agent_sql or "",
                database_connection=db_conn,
            )
            score: MetricResult = ex_metric.evaluate(ctx)
            passed = score.score >= 0.8

            if passed:
                print(f"  ✅ EX={score.score:.2f}  ({result['elapsed']:.1f}s)")
                total_pass += 1
            else:
                print(f"  ❌ EX={score.score:.2f}  ({result['elapsed']:.1f}s)")
                if score.details:
                    print(f"     Details: {score.details}")
                total_fail += 1

            results_by_category.setdefault(cat, []).append(passed)

        except Exception as e:
            print(f"  ⚠️  Metric error: {e}")
            total_fail += 1
            results_by_category.setdefault(cat, []).append(False)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for cat, passes in results_by_category.items():
        n = len(passes)
        p = sum(passes)
        print(f"  {cat:30s}  {p}/{n}  ({'✅' if p == n else '⚠️ '})")
    print(f"\n  TOTAL  {total_pass}/{total_pass + total_fail}")
    print("=" * 70 + "\n")

    db_conn.close()


if __name__ == "__main__":
    main()
