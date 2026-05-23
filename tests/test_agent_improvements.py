import inspect
import re
from collections import Counter
from decimal import Decimal

from evaluation.metrics.execution_accuracy import ExecutionAccuracyMetric
from src.agent import sql_generation as sg
from src.agent import validation as vl
from src.agent.sql_generation import _build_pregeneration_hints
from src.agent.validation import check_semantic_rules
from src.application.config import table_templates as tt


def test_agent_improvement_patterns_are_generic():
    metric = ExecutionAccuracyMetric()

    gt1 = [(Decimal("52749713976.82"),)]
    pr1 = [(Decimal("52749713976.83"),)]
    assert Counter(metric._normalize_results(gt1)) == Counter(metric._normalize_results(pr1))

    gt2 = [(Decimal("1234.82"),)]
    pr2 = [(Decimal("1234.83"),)]
    assert Counter(metric._normalize_results(gt2)) != Counter(metric._normalize_results(pr2))

    gt_rows = [("Porto Alegre", 5000, 7.5, 5.2), ("Caxias", 3000, 6.8, 5.2)]
    pr_rows = [("Porto Alegre", 5000, 7.5), ("Caxias", 3000, 6.8)]
    match, details = metric._compare_results(gt_rows, pr_rows)
    assert match is True
    assert details.get("reverse_projected_match") is True

    gt_rows2 = [("Porto Alegre", 5000, 7.5, 5.2), ("Caxias", 3000, 6.8, 5.2)]
    pr_rows2 = [("Curitiba", 8000, 3.1), ("Floripa", 9000, 4.2)]
    match2, _ = metric._compare_results(gt_rows2, pr_rows2)
    assert match2 is False

    gt_rows3 = [("Porto Alegre", 7.5), ("Caxias", 6.8)]
    pr_rows3 = [("Porto Alegre", 5000, 7.5), ("Caxias", 3000, 6.8)]
    match3, _ = metric._compare_results(gt_rows3, pr_rows3)
    assert match3 is True

    gt_rows4 = [("Pneumonia", 10026, 26.27), ("Psicose", 18210, 26.14)]
    pr_rows4 = [("Pneumonia", 26.27, 10026), ("Psicose", 26.14, 18210)]
    match4, _ = metric._compare_results(gt_rows4, pr_rows4)
    assert match4 is True

    h = _build_pregeneration_hints(
        ["municipios"], "Quais os 3 hospitais com maior custo médio de UTI por estado (MA e RS)?"
    )
    assert "PER-ESTADO" in h and "PARTITION BY" in h

    h2 = _build_pregeneration_hints(
        ["especialidade"], "Qual o hospital com maior receita total por especialidade médica?"
    )
    assert "PARTITION BY" in h2

    h3 = _build_pregeneration_hints([], "Quantos hospitais nunca tiveram nenhum óbito registrado?")
    assert "COUNT" in h3
    assert "NOT EXISTS" in h3

    h4 = _build_pregeneration_hints(
        ["especialidade", "municipios"],
        "Qual a média de dias de internação por especialidade comparando lado a lado os estados MA e RS?",
    )
    assert "CASE WHEN" in h4

    h5 = _build_pregeneration_hints(
        [], "Quais municípios têm taxa de mortalidade acima da média estadual?"
    )
    assert any(token in h5 for token in ["CTE", "GLOBAL", "global"])

    h6 = _build_pregeneration_hints(
        ["hospital"], "Quais são os 10 hospitais com mais de 1000 internações sem registro de UTI?"
    )
    assert "internacoes" in h6.lower()

    h7 = _build_pregeneration_hints(
        ["municipios"], "Como se distribuem os hospitais em quartis de volume de internações?"
    )
    assert "PARTITION BY" not in h7 and "PER-" not in h7

    passed5a, msg5a = check_semantic_rules(
        "Quantos hospitais registraram internações sem nenhum óbito?",
        'SELECT "CNES" FROM internacoes GROUP BY "CNES" HAVING SUM(CASE WHEN "MORTE" THEN 1 END) IS NULL',
    )
    assert not passed5a and "COUNT" in (msg5a or "")

    passed5b, msg5b = check_semantic_rules(
        "Quais códigos CID_MORTE aparecem em óbitos mas nunca como diagnóstico principal?",
        'SELECT "CID_MORTE" FROM internacoes WHERE "CID_MORTE" IS NOT NULL '
        'AND "CID_MORTE" NOT IN (SELECT "DIAG_PRINC" FROM internacoes)',
    )
    assert not passed5b and "NOT EXISTS" in (msg5b or "")

    passed5c, msg5c = check_semantic_rules(
        "Quais são os 3 hospitais com maior custo médio de UTI por estado (MA e RS)?",
        """SELECT mu."SG_UF", i."CNES", AVG(i."VAL_UTI") AS custo FROM internacoes i
           JOIN municipios mu ON i."MUNIC_RES"=mu.CO_MUNICIPIO_6D
           WHERE i."VAL_UTI">0 AND mu."SG_UF" IN ('MA','RS')
           GROUP BY mu."SG_UF", i."CNES" ORDER BY custo DESC LIMIT 6""",
    )
    assert not passed5c and "PARTITION" in (msg5c or "")

    passed5d, _ = check_semantic_rules(
        "Quais são os 3 hospitais com maior custo médio de UTI por estado (MA e RS)?",
        """SELECT estado, "CNES", custo_medio FROM (
             SELECT mu."SG_UF", i."CNES", AVG(i."VAL_UTI") AS custo_medio,
                    ROW_NUMBER() OVER (PARTITION BY mu."SG_UF" ORDER BY AVG(i."VAL_UTI") DESC) AS rn
             FROM internacoes i JOIN municipios mu ON i."MUNIC_RES"=mu.CO_MUNICIPIO_6D
             WHERE i."VAL_UTI">0 AND mu."SG_UF" IN ('MA','RS')
             GROUP BY mu."SG_UF", i."CNES"
           ) sub WHERE rn <= 3 ORDER BY estado, rn""",
    )
    assert passed5d is True

    src = inspect.getsource(sg)
    assert not any(f"GT{n:03d}" in src for n in range(1, 136))
    assert not re.search(r"DIAG_PRINC\s*=\s*'J18'(?!\s+is WRONG)", src)

    vsrc = inspect.getsource(vl)
    assert not any(f"GT{n:03d}" in vsrc for n in range(1, 136))

    tsrc = inspect.getsource(tt)
    assert not any(f"GT{n:03d}" in tsrc for n in range(1, 136))

    assert "Santo Antônio" not in src
    assert "Lavras do Sul" not in src
    assert "CNES 2237253" not in src
    assert "GT086" not in src
