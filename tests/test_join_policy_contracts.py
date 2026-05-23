from src.semantic.contracts.join_policy import (
    JOIN_ENFORCEMENT_ALLOW,
    JOIN_ENFORCEMENT_ALLOW_WITH_CAVEAT,
    JOIN_ENFORCEMENT_BLOCK,
    load_join_policy_registry,
)
from src.semantic.planner import build_semantic_plan
from src.semantic.validators import validate_sql_against_semantic_plan


def test_diag_princ_to_cid_is_allowed_without_caveat():
    registry = load_join_policy_registry()

    policy = registry.lookup("internacoes", "DIAG_PRINC", "cid", "CID")

    assert policy is not None
    assert policy.is_allowed is True
    assert policy.requires_caveat is False
    assert policy.is_audit_only is False
    assert policy.enforcement == JOIN_ENFORCEMENT_ALLOW
    assert policy.match_rate_non_null is not None
    assert policy.match_rate_non_null > 0.99


def test_munic_res_requires_mapped_scope_caveat():
    registry = load_join_policy_registry()

    policy = registry.lookup("internacoes", "MUNIC_RES", "municipios", "CO_MUNICIPIO_6D")

    assert policy is not None
    assert policy.is_allowed is True
    assert policy.requires_caveat is True
    assert policy.enforcement == JOIN_ENFORCEMENT_ALLOW_WITH_CAVEAT
    assert policy.caveat_code == "internacoes_munic_res_mapped_scope"
    assert policy.message_ptbr is not None
    assert "cobertura imperfeita" in policy.message_ptbr


def test_hospital_municipio_movimento_is_allowed_without_caveat():
    registry = load_join_policy_registry()

    policy = registry.lookup("hospital", "MUNIC_MOV", "municipios", "CO_MUNICIPIO_6D")

    assert policy is not None
    assert policy.is_allowed is True
    assert policy.requires_caveat is False
    assert policy.is_audit_only is False
    assert policy.enforcement == JOIN_ENFORCEMENT_ALLOW


def test_raca_cor_audit_policy_is_caveated_by_coverage_contract():
    registry = load_join_policy_registry()

    policy = registry.lookup("internacoes", "RACA_COR", "raca_cor", "RACA_COR")

    assert policy is not None
    assert policy.is_audit_only is True
    assert policy.is_allowed is True
    assert policy.requires_caveat is True
    assert policy.enforcement == JOIN_ENFORCEMENT_ALLOW_WITH_CAVEAT
    assert policy.caveat_code == "internacoes_raca_cor_audit_coverage"
    assert policy.message_ptbr is not None
    assert "baixa cobertura" in policy.message_ptbr


def test_cid_morte_to_cid_is_audit_only():
    registry = load_join_policy_registry()

    policy = registry.lookup("internacoes", "CID_MORTE", "cid", "CID")

    assert policy is not None
    assert policy.is_allowed is False
    assert policy.requires_caveat is False
    assert policy.is_audit_only is True
    assert policy.enforcement == JOIN_ENFORCEMENT_BLOCK
    assert policy.caveat_code == "internacoes_cid_morte_audit_only"
    assert policy.message_ptbr is not None
    assert "audit-only" in policy.message_ptbr


def test_diag_secun_to_cid_is_audit_only():
    registry = load_join_policy_registry()

    policy = registry.lookup("internacoes", "DIAG_SECUN", "cid", "CID")

    assert policy is not None
    assert policy.is_allowed is False
    assert policy.is_audit_only is True
    assert policy.enforcement == JOIN_ENFORCEMENT_BLOCK


def test_all_join_policies_have_declarative_enforcement():
    registry = load_join_policy_registry()
    allowed_values = {
        JOIN_ENFORCEMENT_ALLOW,
        JOIN_ENFORCEMENT_ALLOW_WITH_CAVEAT,
        JOIN_ENFORCEMENT_BLOCK,
    }

    assert registry.policies
    for policy in registry.policies:
        assert policy.enforcement in allowed_values
        if policy.enforcement == JOIN_ENFORCEMENT_BLOCK:
            assert policy.is_allowed is False
            assert policy.message_ptbr is not None
        if policy.enforcement == JOIN_ENFORCEMENT_ALLOW_WITH_CAVEAT:
            assert policy.is_allowed is True
            assert policy.requires_caveat is True
            assert policy.message_ptbr is not None


def test_lookup_is_bidirectional():
    registry = load_join_policy_registry()

    forward = registry.lookup("internacoes", "DIAG_PRINC", "cid", "CID")
    reverse = registry.lookup("cid", "CID", "internacoes", "DIAG_PRINC")

    assert forward is not None
    assert reverse == forward


def test_semantic_validator_rejects_audit_only_join_policy():
    plan = build_semantic_plan("Quantas internações foram registradas?")
    sql = """
        SELECT COUNT(*) AS total_internacoes
        FROM internacoes i
        JOIN cid c ON i."CID_MORTE" = c."CID"
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "blocked" in (message or "")


def test_semantic_validator_rejects_low_coverage_audit_only_join_policy():
    plan = build_semantic_plan("Quantas internações foram registradas?")
    sql = """
        SELECT COUNT(*) AS total_internacoes
        FROM internacoes i
        JOIN cid c ON i."DIAG_SECUN" = c."CID"
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "blocked" in (message or "")


def test_semantic_validator_allows_confirmed_diag_princ_join_policy():
    plan = build_semantic_plan("Quais capítulos CID concentraram mais internações?")
    sql = """
        SELECT c."DS_CAPITULO" AS cid_capitulo, COUNT(*) AS total_internacoes
        FROM internacoes i
        JOIN cid c ON i."DIAG_PRINC" = c."CID"
        GROUP BY c."DS_CAPITULO"
        ORDER BY total_internacoes DESC
        LIMIT 10
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True, message
