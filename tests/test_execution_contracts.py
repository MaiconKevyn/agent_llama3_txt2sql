from src.agent.execution import _validate_post_execution_contract
from src.agent.execution_contracts import (
    sql_mentions_output_dimension,
    validate_post_execution_contract,
)
from src.semantic.planner import build_semantic_plan


def test_post_execution_contract_public_module_preserves_dimension_check():
    plan = build_semantic_plan("Quais categorias CID foram mais frequentes?")
    sql = 'SELECT c."DS_CATEGORIA" AS categoria_cid, COUNT(*) FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" GROUP BY 1'

    passed, message = validate_post_execution_contract(plan, sql, results=[{}], row_count=1)

    assert passed, message
    assert sql_mentions_output_dimension(sql, "cid_categoria")


def test_execution_private_facade_preserves_legacy_imports():
    plan = build_semantic_plan("Quais categorias CID foram mais frequentes?")

    passed, message = _validate_post_execution_contract(
        plan,
        "SELECT COUNT(*) AS total FROM internacoes",
        results=[{}],
        row_count=1,
    )

    assert not passed
    assert "cid_categoria" in (message or "")
