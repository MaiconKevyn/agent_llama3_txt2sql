from src.agent.response import _generate_formatted_response


class FailingLLMManager:
    def generate_conversational_response(self, *args, **kwargs):
        raise AssertionError("deterministic response formatting should not call the LLM")


def test_scalar_response_is_formatted_without_llm():
    response = _generate_formatted_response(
        llm_manager=FailingLLMManager(),
        user_query="Quantas internacoes foram registradas em 2018?",
        sql_query='SELECT COUNT(*) AS total_internacoes FROM internacoes WHERE "ano" = 2018',
        results=[{"result": (11857648,)}],
        row_count=1,
    )

    assert response == "Total de internacoes: 11.857.648."


def test_grouped_response_is_formatted_without_llm():
    response = _generate_formatted_response(
        llm_manager=FailingLLMManager(),
        user_query="Quais UFs tiveram maior leitos SUS por 1000 habitantes em 2021?",
        sql_query='SELECT "SG_UF" AS uf, 3.25 AS valor_indicador FROM municipios',
        results=[
            {"uf": "RS", "valor_indicador": 3.25},
            {"uf": "SC", "valor_indicador": 3.1},
        ],
        row_count=2,
    )

    assert response == (
        "Resultados:\n1. UF: RS; Valor do indicador: 3,25\n2. UF: SC; Valor do indicador: 3,1"
    )
