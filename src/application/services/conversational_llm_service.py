"""
Serviço de comunicação com LLM especializado em conversação e domínio SUS.
"""

import json
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

import requests
from requests.exceptions import RequestException, Timeout

from src.domain.exceptions.custom_exceptions import (
    LLMCommunicationError,
    LLMTimeoutError,
    LLMUnavailableError
)


@dataclass
class ConversationalConfig:
    """Configuração especializada para LLM conversacional."""
    model_name: str = "llama3.2:latest"  # Use available model
    temperature: float = 0.7  # Mais criativo para conversação
    max_tokens: int = 1000
    timeout: int = 60
    max_retries: int = 3
    system_role: str = "assistant"
    stream: bool = False


class ConversationalLLMService:
    """
    Serviço especializado em comunicação com LLM para respostas conversacionais
    amigáveis no domínio SUS.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        config: Optional[ConversationalConfig] = None
    ):
        self.base_url = base_url.rstrip('/')
        self.config = config or ConversationalConfig()
        self.logger = logging.getLogger(__name__)
        
        # Endpoints
        self.chat_endpoint = f"{self.base_url}/api/chat"
        self.health_endpoint = f"{self.base_url}/api/tags"
        
        self.logger.info(
            f"ConversationalLLMService inicializado com modelo: {self.config.model_name}"
        )

    def is_available(self) -> bool:
        """Verifica se o serviço LLM conversacional está disponível."""
        try:
            response = requests.get(
                self.health_endpoint,
                timeout=5
            )
            return response.status_code == 200
        except RequestException as e:
            self.logger.warning(f"LLM conversacional indisponível: {e}")
            return False

    def generate_conversational_response(
        self,
        user_query: str,
        sql_query: str,
        sql_results: Any,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Gera resposta conversacional amigável baseada nos resultados SQL.
        
        Args:
            user_query: Pergunta original do usuário
            sql_query: Query SQL executada
            sql_results: Resultados da query SQL
            context: Contexto adicional da conversação
            
        Returns:
            Resposta em linguagem natural amigável
        """
        prompt = self._build_conversational_prompt(
            user_query, sql_query, sql_results, context
        )
        
        return self._call_llm(prompt)

    def _build_conversational_prompt(
        self,
        user_query: str,
        sql_query: str,
        sql_results: Any,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Constrói prompt especializado para respostas conversacionais."""
        
        # Contexto SUS especializado
        sus_context = """
        Você é um assistente especialista em dados do Sistema Único de Saúde (SUS) brasileiro.
        Sua função é transformar resultados de consultas SQL em respostas conversacionais
        amigáveis e informativas para profissionais de saúde e gestores públicos.
        
        CARACTERÍSTICAS DA SUA RESPOSTA:
        - Linguagem clara e profissional, mas amigável
        - Explicações contextualizadas sobre o SUS quando relevante
        - Interpretação dos dados com insights úteis
        - Formatação organizada e fácil de ler
        - Sugestões de ações ou análises adicionais quando apropriado
        
        CONHECIMENTO ESPECÍFICO DO SUS:
        - CNES: Cadastro Nacional de Estabelecimentos de Saúde
        - CID: Classificação Internacional de Doenças
        - SIGTAP: Sistema de Gerenciamento da Tabela de Procedimentos
        - Estados e municípios brasileiros
        - Terminologia médica em português brasileiro
        
        FORMATO DA RESPOSTA:
        Responda APENAS com:
        
        **Resumo Direto:**
        [Uma resposta direta e amigável em 1-2 frases]
        
        **Dados Detalhados:**
        [Apresentação clara dos números/resultados encontrados]
        
        Mantenha a resposta concisa, amigável e em português brasileiro.
        NÃO inclua contextualização adicional, insights ou sugestões.
        """
        
        # Formatação dos resultados SQL
        results_text = self._format_sql_results(sql_results)
        
        prompt = f"""{sus_context}

PERGUNTA DO USUÁRIO:
{user_query}

CONSULTA SQL EXECUTADA:
{sql_query}

RESULTADOS OBTIDOS:
{results_text}

CONTEXTO ADICIONAL:
{json.dumps(context or {}, ensure_ascii=False, indent=2)}

Transforme estes dados em uma resposta conversacional amigável e informativa.
Responda em português brasileiro, focando na utilidade prática da informação.
"""
        
        return prompt

    def _format_sql_results(self, sql_results: Any) -> str:
        """Formata os resultados SQL para inclusão no prompt."""
        if sql_results is None:
            return "Nenhum resultado encontrado."
        
        if isinstance(sql_results, (list, tuple)):
            if len(sql_results) == 0:
                return "Nenhum resultado encontrado."
            
            # Limita a quantidade de resultados para evitar prompts muito longos
            limited_results = sql_results[:20]
            
            if isinstance(limited_results[0], (list, tuple)):
                # Resultados tabulares
                formatted = []
                for row in limited_results:
                    formatted.append(str(row))
                
                result_text = "\n".join(formatted)
                
                if len(sql_results) > 20:
                    result_text += f"\n... (mostrando 20 de {len(sql_results)} resultados)"
                
                return result_text
            else:
                # Lista simples
                return str(limited_results)
        
        return str(sql_results)

    def _call_llm(self, prompt: str) -> str:
        """Realiza chamada para o LLM com retry logic."""
        for attempt in range(self.config.max_retries):
            try:
                response = self._make_request(prompt)
                return response
                
            except LLMTimeoutError:
                if attempt == self.config.max_retries - 1:
                    raise
                self.logger.warning(
                    f"Timeout na tentativa {attempt + 1}, tentando novamente..."
                )
                time.sleep(2 ** attempt)  # Backoff exponencial
                
            except LLMCommunicationError as e:
                if attempt == self.config.max_retries - 1:
                    raise
                self.logger.warning(
                    f"Erro de comunicação na tentativa {attempt + 1}: {e}"
                )
                time.sleep(2 ** attempt)

        raise LLMCommunicationError("Falha após todas as tentativas de retry")

    def _make_request(self, prompt: str) -> str:
        """Faz a requisição HTTP para o LLM."""
        if not self.is_available():
            raise LLMUnavailableError(
                "Serviço LLM conversacional indisponível"
            )

        payload = {
            "model": self.config.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "Você é um assistente especialista em dados do SUS brasileiro."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            "stream": self.config.stream,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens
            }
        }

        try:
            start_time = time.time()
            
            response = requests.post(
                self.chat_endpoint,
                json=payload,
                timeout=self.config.timeout
            )
            
            response_time = time.time() - start_time
            
            if response.status_code != 200:
                error_msg = f"Erro HTTP {response.status_code}: {response.text}"
                self.logger.error(error_msg)
                raise LLMCommunicationError(error_msg)

            response_data = response.json()
            
            if 'message' not in response_data:
                raise LLMCommunicationError(
                    "Resposta do LLM em formato inesperado"
                )

            llm_response = response_data['message']['content']
            
            self.logger.info(
                f"Resposta conversacional gerada em {response_time:.2f}s"
            )
            
            return llm_response.strip()

        except Timeout:
            raise LLMTimeoutError(
                f"Timeout na comunicação com LLM conversacional ({self.config.timeout}s)"
            )
        except RequestException as e:
            raise LLMCommunicationError(
                f"Erro na comunicação com LLM conversacional: {e}"
            )
        except json.JSONDecodeError as e:
            raise LLMCommunicationError(
                f"Erro ao decodificar resposta JSON do LLM: {e}"
            )

    def get_model_info(self) -> Dict[str, Any]:
        """Retorna informações sobre o modelo conversacional."""
        return {
            "model_name": self.config.model_name,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "timeout": self.config.timeout,
            "specialization": "Conversational responses for SUS healthcare data",
            "language": "Portuguese (Brazilian)",
            "available": self.is_available()
        }