from src.agent.response import build_domain_caveats


def test_domain_caveats_explain_child_and_respiratory_defaults():
    semantic_plan = {
        "filters": [
            {"field": "idade", "values": ["18"], "operator": "<"},
            {"field": "diagnostico_principal_prefix", "values": ["J%"], "operator": "LIKE"},
            {"field": "desfecho", "values": ["MORTE = true"], "operator": "semantic"},
        ]
    }

    caveats = build_domain_caveats(
        user_query="mortes de crianca por causas respiratorias",
        semantic_plan=semantic_plan,
    )

    assert "idade menor que 18 anos" in " ".join(caveats)
    assert "CID J00-J99" in " ".join(caveats)
    assert "MORTE=true" in " ".join(caveats)
