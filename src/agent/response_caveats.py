"""Caveats derived from semantic, join-policy and data-quality contracts."""

from __future__ import annotations

from typing import Any

from ..semantic.contracts.data_quality import data_quality_caveats_for_sql
from ..semantic.contracts.join_policy import JoinPolicy, policies_for_sql_joins


def build_domain_caveats(*, user_query: str, semantic_plan: dict[str, Any] | None) -> list[str]:
    """Return user-facing caveats for implicit domain policies."""

    filters = (semantic_plan or {}).get("filters", [])
    caveats: list[str] = []
    normalized = (user_query or "").lower()
    if any(
        token in normalized for token in ["crianca", "criança", "criancas", "crianças", "pediatric"]
    ) and any(
        item.get("field") == "idade"
        and item.get("operator") == "<"
        and item.get("values") == ["18"]
        for item in filters
    ):
        caveats.append("Crianca foi operacionalizado como idade menor que 18 anos.")
    if ("respirat" in normalized or "cid j" in normalized) and any(
        item.get("field") == "diagnostico_principal_prefix" and item.get("values") == ["J%"]
        for item in filters
    ):
        caveats.append("Causas respiratorias foram operacionalizadas como CID J00-J99.")
    if (
        ("quais cid" in normalized or "quais cids" in normalized)
        and "analisar" in normalized
        and any(item.get("field") == "diagnostico_principal_prefix" for item in filters)
    ):
        caveats.append(
            "Lista candidata de CIDs; confirme o escopo clinico antes de usar em contagens."
        )
    if "cronica" in normalized or "cronicas" in normalized or "crônica" in normalized:
        caveats.append(
            "Doencas cronicas nao sao um unico bloco CID; confirme a lista de condicoes ou o escopo clinico."
        )
    if any(item.get("field") == "desfecho" for item in filters):
        caveats.append("Mortes hospitalares foram filtradas com MORTE=true.")
    return caveats


def build_join_policy_caveats(sql_query: str | None) -> list[str]:
    """Return user-facing caveats implied by executable join contracts."""

    if not sql_query:
        return []

    caveats: list[str] = []
    for policy in policies_for_sql_joins(sql_query):
        caveat = _join_policy_caveat(policy)
        if caveat and caveat not in caveats:
            caveats.append(caveat)
    return caveats


def build_data_quality_caveats(sql_query: str | None) -> list[str]:
    """Return user-facing caveats implied by generated data quality checks."""

    return data_quality_caveats_for_sql(sql_query)


def _join_policy_caveat(policy: JoinPolicy) -> str | None:
    if policy.requires_caveat:
        return policy.message_ptbr
    return None
