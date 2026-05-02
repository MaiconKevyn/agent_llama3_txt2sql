"""
Synthetic tests validating the 8 agent improvement patterns.
Uses NO benchmark queries — all examples are fabricated for testing logic only.
"""
import sys, os
sys.path.insert(0, '/home/maiconkevyn/PycharmProjects/txt2sql_refactor_openai')
os.chdir('/home/maiconkevyn/PycharmProjects/txt2sql_refactor_openai')
from dotenv import load_dotenv; load_dotenv()

from decimal import Decimal
from collections import Counter
from evaluation.metrics.execution_accuracy import ExecutionAccuracyMetric

metric = ExecutionAccuracyMetric()

PASS = "\033[92m✅ PASS\033[0m"
FAIL = "\033[91m❌ FAIL\033[0m"
results = []

def check(label, got, expected):
    ok = got == expected
    results.append(ok)
    print(f"  {PASS if ok else FAIL}  {label}")
    if not ok:
        print(f"       got={got!r}, expected={expected!r}")

# ─────────────────────────────────────────────────────────────────────────────
print("\n=== 1. FP DRIFT TOLERANCE (Pattern: large SUM floating-point) ===")
gt1 = [(Decimal('52749713976.82'),)]
pr1 = [(Decimal('52749713976.83'),)]
check("52B decimal differs by 0.01 → ROUND to 0 → equal",
      Counter(metric._normalize_results(gt1)) == Counter(metric._normalize_results(pr1)), True)

gt2 = [(Decimal('1234.82'),)]
pr2 = [(Decimal('1234.83'),)]
check("Small value 1234.82 vs 1234.83 → 2dp round → NOT equal (precision preserved)",
      Counter(metric._normalize_results(gt2)) == Counter(metric._normalize_results(pr2)), False)

gt3 = [(Decimal('1000000.00'),), (Decimal('2000000.50'),)]
pr3 = [(Decimal('1000000.01'),), (Decimal('2000000.48'),)]
check("Two >=1M values: drift within ±1 → round-0 absorbs → equal",
      Counter(metric._normalize_results(gt3)) == Counter(metric._normalize_results(pr3)), True)

# ─────────────────────────────────────────────────────────────────────────────
print("\n=== 2. REVERSE PROJECTED MATCH (gold has extra diagnostic columns) ===")
gt_rows = [("Porto Alegre", 5000, 7.5, 5.2), ("Caxias", 3000, 6.8, 5.2)]
pr_rows = [("Porto Alegre", 5000, 7.5), ("Caxias", 3000, 6.8)]
match, details = metric._compare_results(gt_rows, pr_rows)
check("Reverse projected: gold 4 cols, pred 3 cols, same rows → True", match, True)
check("  Details has reverse_projected_match flag", details.get("reverse_projected_match"), True)

# Edge case: completely different data — should NOT match
gt_rows2 = [("Porto Alegre", 5000, 7.5, 5.2), ("Caxias", 3000, 6.8, 5.2)]
pr_rows2 = [("Curitiba", 8000, 3.1), ("Floripa", 9000, 4.2)]
match2, _ = metric._compare_results(gt_rows2, pr_rows2)
check("Reverse projected: different cities → False", match2, False)

# ─────────────────────────────────────────────────────────────────────────────
print("\n=== 3. FORWARD + BIDIRECTIONAL MATCH ===")
gt_rows3 = [("Porto Alegre", 7.5), ("Caxias", 6.8)]
pr_rows3 = [("Porto Alegre", 5000, 7.5), ("Caxias", 3000, 6.8)]
match3, _ = metric._compare_results(gt_rows3, pr_rows3)
check("Forward projected: gold 2 cols, pred 3 cols → True", match3, True)

gt_rows4 = [("Pneumonia", 10026, 26.27), ("Psicose", 18210, 26.14)]
pr_rows4 = [("Pneumonia", 26.27, 10026), ("Psicose", 26.14, 18210)]
match4, _ = metric._compare_results(gt_rows4, pr_rows4)
check("Bidirectional: 3-col column swap → True", match4, True)

# ─────────────────────────────────────────────────────────────────────────────
print("\n=== 4. HINT GENERATION ===")
from src.agent.sql_generation import _build_pregeneration_hints

h = _build_pregeneration_hints(["municipios"], "Quais os 3 hospitais com maior custo médio de UTI por estado (MA e RS)?")
check("'por estado' + 'maior' → PER-ESTADO hint + PARTITION BY", "PER-ESTADO" in h and "PARTITION BY" in h, True)

h2 = _build_pregeneration_hints(["especialidade"], "Qual o hospital com maior receita total por especialidade médica?")
check("'por especialidade' + 'maior' → PARTITION BY in hint", "PARTITION BY" in h2, True)

h3 = _build_pregeneration_hints([], "Quantos hospitais nunca tiveram nenhum óbito registrado?")
check("'quantos' + 'nunca' → COUNT semantics hint", "COUNT" in h3, True)
check("'nunca' → NOT EXISTS anti-join hint", "NOT EXISTS" in h3, True)

h4 = _build_pregeneration_hints(["especialidade", "municipios"],
     "Qual a média de dias de internação por especialidade comparando lado a lado os estados MA e RS?")
check("'comparando lado a lado MA e RS' → PIVOT hint", "CASE WHEN" in h4, True)

h5 = _build_pregeneration_hints([], "Quais municípios têm taxa de mortalidade acima da média estadual?")
check("'acima da média' → global vs local avg hint", any(x in h5 for x in ["CTE", "GLOBAL", "global"]), True)

h6 = _build_pregeneration_hints(["hospital"], "Quais são os 10 hospitais com mais de 1000 internações sem registro de UTI?")
check("'hospitais com mais de' → aggregation-first hint", "internacoes" in h6.lower(), True)

h7 = _build_pregeneration_hints(["municipios"], "Como se distribuem os hospitais em quartis de volume de internações?")
check("No spurious hints for non-ranking query", "PARTITION BY" not in h7 and "PER-" not in h7, True)

# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== 5. VALIDATION SEMANTIC RULE CHECKS ===")
from src.agent.validation import check_semantic_rules

# 5a: count vs list
passed5a, msg5a = check_semantic_rules(
    "Quantos hospitais registraram internações sem nenhum óbito?",
    'SELECT "CNES" FROM internacoes GROUP BY "CNES" HAVING SUM(CASE WHEN "MORTE" THEN 1 END) IS NULL'
)
check("'quantos' + no outer COUNT → error mentioning COUNT", not passed5a and "COUNT" in (msg5a or ""), True)

# 5b: NOT IN → NOT EXISTS
passed5b, msg5b = check_semantic_rules(
    "Quais CIDs aparecem como causa de morte mas nunca como diagnóstico principal?",
    'SELECT "CID_MORTE" FROM internacoes WHERE "CID_MORTE" IS NOT NULL AND "CID_MORTE" NOT IN (SELECT "DIAG_PRINC" FROM internacoes)'
)
check("NOT IN subquery → validation recommends NOT EXISTS", not passed5b and "NOT EXISTS" in (msg5b or ""), True)

# 5c: per-group top-N with LIMIT, no PARTITION BY
passed5c, msg5c = check_semantic_rules(
    "Quais são os 3 hospitais com maior custo médio de UTI por estado (MA e RS)?",
    """SELECT mu.estado, i."CNES", AVG(i."VAL_UTI") AS custo FROM internacoes i
       JOIN municipios mu ON i."MUNIC_RES"=mu.codigo_6d
       WHERE i."VAL_UTI">0 AND mu.estado IN ('MA','RS')
       GROUP BY mu.estado, i."CNES" ORDER BY custo DESC LIMIT 6"""
)
check("'por estado' + 'maior' + LIMIT (no PARTITION BY) → PARTITION error",
      not passed5c and "PARTITION" in (msg5c or ""), True)

# 5d: valid per-group query WITH PARTITION BY — must NOT trigger error
passed5d, msg5d = check_semantic_rules(
    "Quais são os 3 hospitais com maior custo médio de UTI por estado (MA e RS)?",
    """SELECT estado, "CNES", custo_medio FROM (
         SELECT mu.estado, i."CNES", AVG(i."VAL_UTI") AS custo_medio,
                ROW_NUMBER() OVER (PARTITION BY mu.estado ORDER BY AVG(i."VAL_UTI") DESC) AS rn
         FROM internacoes i JOIN municipios mu ON i."MUNIC_RES"=mu.codigo_6d
         WHERE i."VAL_UTI">0 AND mu.estado IN ('MA','RS')
         GROUP BY mu.estado, i."CNES"
       ) sub WHERE rn <= 3 ORDER BY estado, rn"""
)
check("Correct PARTITION BY query passes validation", passed5d, True)


print("\n=== 6. ANTI-OVERFITTING CHECKS ===")
import inspect
from src.agent import sql_generation as sg
src = inspect.getsource(sg)
import re as _re

check("No GT IDs hardcoded in sql_generation.py",
      not any(f"GT{n:03d}" in src for n in range(1, 136)), True)

# CID code hardcoding: check it only appears in negative-example context (as string in comment/error text)
# not as an actual WHERE condition
positively_hardcoded = bool(_re.search(r"DIAG_PRINC\s*=\s*'J18'(?!\s+is WRONG)", src))
check("'J18' only in anti-pattern doc, not as real condition",
      not positively_hardcoded, True)

from src.agent import validation as vl
vsrc = inspect.getsource(vl)
check("No GT IDs in validation.py", not any(f"GT{n:03d}" in vsrc for n in range(1,136)), True)

from src.application.config import table_templates as tt
tsrc = inspect.getsource(tt)
check("No GT IDs in table_templates.py", not any(f"GT{n:03d}" in tsrc for n in range(1,136)), True)

check("All hints use generic placeholders (no benchmark question text)",
      "Santo Antônio" not in src and "Lavras do Sul" not in src
      and "CNES 2237253" not in src and "GT086" not in src, True)

# ─────────────────────────────────────────────────────────────────────────────
total = len(results)
passed = sum(results)
print(f"\n{'='*55}")
print(f"  TOTAL: {passed}/{total} passed  ({'%.0f' % (passed/total*100)}%)")
print(f"{'='*55}")
sys.exit(0 if passed == total else 1)
