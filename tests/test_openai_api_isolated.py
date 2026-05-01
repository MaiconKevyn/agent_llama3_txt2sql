"""
Teste isolado da API OpenAI.
Verifica se OPENAI_API_KEY está configurada e se a API responde corretamente.

Uso:
    python tests/test_openai_api_isolated.py
"""
import os
import sys

# Garante que o .env é carregado antes de qualquer import que use env vars
from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage


def test_openai_api():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERRO: OPENAI_API_KEY não definida no .env")
        sys.exit(1)

    print(f"Chave encontrada: {api_key[:8]}...{api_key[-4:]}")
    print("Chamando API OpenAI (gpt-4o-mini)...")

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, api_key=api_key)
    response = llm.invoke([HumanMessage(content="Responda apenas com a frase: 'API OpenAI funcionando!'")])

    print(f"Resposta: {response.content}")

    if not response.content:
        print("ERRO: resposta vazia da API")
        sys.exit(1)

    print("\nTeste isolado PASSOU!")


if __name__ == "__main__":
    test_openai_api()
