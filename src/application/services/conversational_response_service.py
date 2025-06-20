"""
Serviço de resposta conversacional que orquestra a geração de respostas 
amigáveis usando LLM especializado e templates de prompts do domínio SUS.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from src.application.services.conversational_llm_service import (
    ConversationalLLMService,
    ConversationalConfig
)
from src.application.services.sus_prompt_template_service import (
    SUSPromptTemplateService,
    PromptType
)
from src.domain.exceptions.custom_exceptions import (
    LLMCommunicationError,
    LLMTimeoutError,
    LLMUnavailableError
)


@dataclass
class ConversationContext:
    """Contexto da conversação para memória e continuidade."""
    session_id: str
    user_id: Optional[str] = None
    previous_queries: List[str] = None
    conversation_history: List[Dict[str, Any]] = None
    domain_preferences: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.previous_queries is None:
            self.previous_queries = []
        if self.conversation_history is None:
            self.conversation_history = []
        if self.domain_preferences is None:
            self.domain_preferences = {}


@dataclass
class ConversationalResponse:
    """Resposta conversacional estruturada."""
    message: str
    response_type: PromptType
    confidence_score: float
    processing_time: float
    context_used: bool
    suggestions: List[str]
    metadata: Dict[str, Any]


class ConversationalResponseService:
    """
    Serviço principal para geração de respostas conversacionais amigáveis
    no domínio SUS, integrando LLM conversacional e templates especializados.
    """

    def __init__(
        self,
        conversational_llm_service: Optional[ConversationalLLMService] = None,
        prompt_template_service: Optional[SUSPromptTemplateService] = None,
        enable_memory: bool = True
    ):
        self.conversational_llm = conversational_llm_service or ConversationalLLMService()
        self.prompt_service = prompt_template_service or SUSPromptTemplateService()
        self.enable_memory = enable_memory
        self.logger = logging.getLogger(__name__)
        
        # Cache de contextos de conversação
        self.conversation_contexts: Dict[str, ConversationContext] = {}
        
        self.logger.info("ConversationalResponseService inicializado")

    def generate_response(
        self,
        user_query: str,
        sql_query: str,
        sql_results: Any,
        session_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        error_message: str = ""
    ) -> ConversationalResponse:
        """
        Gera resposta conversacional amigável baseada nos resultados SQL.
        
        Args:
            user_query: Pergunta original do usuário
            sql_query: Query SQL executada
            sql_results: Resultados da query SQL
            session_id: ID da sessão para controle de contexto
            context: Contexto adicional da conversação
            error_message: Mensagem de erro se houver
            
        Returns:
            Resposta conversacional estruturada
        """
        import time
        start_time = time.time()
        
        try:
            # Determina o tipo de prompt mais apropriado
            has_error = bool(error_message)
            prompt_type = self.prompt_service.determine_prompt_type(
                user_query, sql_results, has_error
            )
            
            # Recupera ou cria contexto da conversação
            conversation_context = self._get_conversation_context(session_id)
            
            # Enriquece o contexto com informações da sessão
            enhanced_context = self._enhance_context(
                context or {}, conversation_context
            )
            
            # Gera o prompt especializado
            specialized_prompt = self.prompt_service.get_prompt(
                prompt_type=prompt_type,
                user_query=user_query,
                sql_query=sql_query,
                sql_results=sql_results,
                context=enhanced_context,
                error_message=error_message
            )
            
            # Gera a resposta conversacional
            if has_error:
                conversational_message = self._generate_error_response(
                    specialized_prompt, error_message
                )
            else:
                conversational_message = self.conversational_llm.generate_conversational_response(
                    user_query=user_query,
                    sql_query=sql_query,
                    sql_results=sql_results,
                    context=enhanced_context
                )
            
            # Gera sugestões de continuação
            suggestions = self._generate_suggestions(
                user_query, sql_results, prompt_type
            )
            
            # Atualiza contexto da conversação
            if self.enable_memory:
                self._update_conversation_context(
                    session_id, user_query, conversational_message, sql_results
                )
            
            processing_time = time.time() - start_time
            
            response = ConversationalResponse(
                message=conversational_message,
                response_type=prompt_type,
                confidence_score=self._calculate_confidence_score(sql_results, has_error),
                processing_time=processing_time,
                context_used=self.enable_memory,
                suggestions=suggestions,
                metadata={
                    "session_id": session_id,
                    "prompt_type": prompt_type.value,
                    "sql_query_length": len(sql_query),
                    "results_count": self._count_results(sql_results),
                    "has_error": has_error,
                    "llm_model": self.conversational_llm.config.model_name
                }
            )
            
            self.logger.info(
                f"Resposta conversacional gerada em {processing_time:.2f}s "
                f"(tipo: {prompt_type.value})"
            )
            
            return response
            
        except (LLMCommunicationError, LLMTimeoutError, LLMUnavailableError) as e:
            # Fallback para erro de LLM
            return self._generate_fallback_response(
                user_query, sql_results, str(e), start_time
            )
        except Exception as e:
            self.logger.error(f"Erro inesperado na geração de resposta: {e}")
            return self._generate_fallback_response(
                user_query, sql_results, f"Erro interno: {e}", start_time
            )

    def _get_conversation_context(self, session_id: str) -> ConversationContext:
        """Recupera ou cria contexto da conversação."""
        if session_id not in self.conversation_contexts:
            self.conversation_contexts[session_id] = ConversationContext(
                session_id=session_id
            )
        return self.conversation_contexts[session_id]

    def _enhance_context(
        self,
        base_context: Dict[str, Any],
        conversation_context: ConversationContext
    ) -> Dict[str, Any]:
        """Enriquece o contexto com informações da conversação."""
        enhanced = base_context.copy()
        
        if self.enable_memory and conversation_context.conversation_history:
            enhanced["conversation_history"] = conversation_context.conversation_history[-3:]  # Últimas 3 interações
            enhanced["previous_queries"] = conversation_context.previous_queries[-3:]
            enhanced["session_context"] = True
        else:
            enhanced["session_context"] = False
            
        enhanced["domain_preferences"] = conversation_context.domain_preferences
        
        return enhanced

    def _generate_error_response(self, specialized_prompt: str, error_message: str) -> str:
        """Gera resposta amigável para erros."""
        try:
            # Usa o LLM para explicar o erro de forma amigável
            return self.conversational_llm._call_llm(specialized_prompt)
        except Exception as e:
            self.logger.error(f"Erro ao gerar resposta de erro: {e}")
            return self._format_basic_error_response(error_message)

    def _format_basic_error_response(self, error_message: str) -> str:
        """Formata resposta básica de erro sem LLM."""
        return f"""
        Desculpe, encontrei um problema ao processar sua consulta.
        
        **Erro encontrado:** {error_message}
        
        **Sugestões:**
        - Verifique se os nomes das tabelas e colunas estão corretos
        - Confirme se os dados solicitados existem na base SUS
        - Tente reformular sua pergunta de forma mais específica
        
        Posso ajudá-lo a refinar sua consulta se necessário.
        """

    def _generate_suggestions(
        self,
        user_query: str,
        sql_results: Any,
        prompt_type: PromptType
    ) -> List[str]:
        """Gera sugestões de análises complementares."""
        suggestions = []
        
        # Sugestões baseadas no tipo de análise
        if prompt_type == PromptType.BASIC_RESPONSE:
            suggestions.extend([
                "Gostaria de ver a evolução temporal destes dados?",
                "Quer comparar com outras regiões?",
                "Posso mostrar estatísticas detalhadas destes resultados"
            ])
        elif prompt_type == PromptType.STATISTICAL_ANALYSIS:
            suggestions.extend([
                "Quer ver a distribuição geográfica destes indicadores?",
                "Posso comparar com períodos anteriores",
                "Gostaria de análise de tendências temporais?"
            ])
        elif prompt_type == PromptType.COMPARATIVE_ANALYSIS:
            suggestions.extend([
                "Quer entender os fatores que explicam essas diferenças?",
                "Posso mostrar a evolução temporal dessas comparações",
                "Gostaria de ver dados por estabelecimento específico?"
            ])
        elif prompt_type == PromptType.GEOGRAPHIC_ANALYSIS:
            suggestions.extend([
                "Quer analisar fatores socioeconômicos relacionados?",
                "Posso mostrar a evolução temporal por região",
                "Gostaria de comparar urbano vs rural?"
            ])
        
        # Sugestões baseadas nos resultados
        if self._has_temporal_data(sql_results):
            suggestions.append("Posso criar análise de tendências temporais")
        
        if self._has_geographic_data(sql_results):
            suggestions.append("Posso gerar análise de distribuição geográfica")
        
        # Limita a 3 sugestões mais relevantes
        return suggestions[:3]

    def _update_conversation_context(
        self,
        session_id: str,
        user_query: str,
        response: str,
        sql_results: Any
    ) -> None:
        """Atualiza o contexto da conversação com nova interação."""
        if not self.enable_memory:
            return
            
        context = self.conversation_contexts[session_id]
        
        # Adiciona query às consultas anteriores
        context.previous_queries.append(user_query)
        if len(context.previous_queries) > 10:  # Mantém apenas as 10 últimas
            context.previous_queries = context.previous_queries[-10:]
        
        # Adiciona interação ao histórico
        interaction = {
            "query": user_query,
            "response": response[:200] + "..." if len(response) > 200 else response,  # Resumo
            "timestamp": time.time(),
            "results_summary": self._summarize_results(sql_results)
        }
        
        context.conversation_history.append(interaction)
        if len(context.conversation_history) > 5:  # Mantém apenas as 5 últimas
            context.conversation_history = context.conversation_history[-5:]

    def _calculate_confidence_score(self, sql_results: Any, has_error: bool) -> float:
        """Calcula score de confiança da resposta."""
        if has_error:
            return 0.3
        
        if sql_results is None:
            return 0.5
        
        if isinstance(sql_results, (list, tuple)):
            if len(sql_results) == 0:
                return 0.6
            elif len(sql_results) < 5:
                return 0.8
            else:
                return 0.9
        
        return 0.7

    def _count_results(self, sql_results: Any) -> int:
        """Conta número de resultados."""
        if sql_results is None:
            return 0
        if isinstance(sql_results, (list, tuple)):
            return len(sql_results)
        return 1

    def _has_temporal_data(self, sql_results: Any) -> bool:
        """Verifica se os resultados contêm dados temporais."""
        if not isinstance(sql_results, (list, tuple)) or len(sql_results) == 0:
            return False
        
        # Procura por indicadores de dados temporais
        first_result = str(sql_results[0]).lower()
        temporal_indicators = ['ano', 'mes', 'data', 'periodo', '20', '19']
        
        return any(indicator in first_result for indicator in temporal_indicators)

    def _has_geographic_data(self, sql_results: Any) -> bool:
        """Verifica se os resultados contêm dados geográficos."""
        if not isinstance(sql_results, (list, tuple)) or len(sql_results) == 0:
            return False
        
        # Procura por indicadores de dados geográficos
        first_result = str(sql_results[0]).lower()
        geographic_indicators = ['estado', 'municipio', 'cidade', 'regiao', 'uf']
        
        return any(indicator in first_result for indicator in geographic_indicators)

    def _summarize_results(self, sql_results: Any) -> str:
        """Cria resumo dos resultados para contexto."""
        if sql_results is None:
            return "Nenhum resultado"
        
        if isinstance(sql_results, (list, tuple)):
            count = len(sql_results)
            if count == 0:
                return "Consulta sem resultados"
            elif count == 1:
                return f"1 resultado: {str(sql_results[0])[:50]}..."
            else:
                return f"{count} resultados encontrados"
        
        return "Resultado único"

    def _generate_fallback_response(
        self,
        user_query: str,
        sql_results: Any,
        error_message: str,
        start_time: float
    ) -> ConversationalResponse:
        """Gera resposta de fallback quando o LLM falha."""
        import time
        
        fallback_message = f"""
        Consegui processar sua consulta, mas o sistema de resposta conversacional 
        está temporariamente indisponível.
        
        **Sua pergunta:** {user_query}
        
        **Resultados obtidos:** {self._format_results_simple(sql_results)}
        
        **Status:** {error_message}
        
        Os dados foram processados com sucesso. Você pode tentar novamente em alguns instantes
        para obter uma resposta mais detalhada e contextualizada.
        """
        
        return ConversationalResponse(
            message=fallback_message,
            response_type=PromptType.BASIC_RESPONSE,
            confidence_score=0.4,
            processing_time=time.time() - start_time,
            context_used=False,
            suggestions=["Tente novamente em alguns instantes"],
            metadata={
                "fallback_used": True,
                "error": error_message,
                "results_available": sql_results is not None
            }
        )

    def _format_results_simple(self, sql_results: Any) -> str:
        """Formatação simples dos resultados para fallback."""
        if sql_results is None:
            return "Nenhum resultado encontrado"
        
        if isinstance(sql_results, (list, tuple)):
            if len(sql_results) == 0:
                return "Consulta executada, mas não retornou dados"
            
            # Mostra até 3 resultados
            limited = sql_results[:3]
            formatted = [f"• {result}" for result in limited]
            
            result_text = "\n".join(formatted)
            
            if len(sql_results) > 3:
                result_text += f"\n... e mais {len(sql_results) - 3} resultados"
            
            return result_text
        
        return f"• {sql_results}"

    def clear_conversation_context(self, session_id: str) -> bool:
        """Limpa o contexto de uma sessão específica."""
        if session_id in self.conversation_contexts:
            del self.conversation_contexts[session_id]
            self.logger.info(f"Contexto da sessão {session_id} removido")
            return True
        return False

    def get_conversation_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retorna resumo da conversação de uma sessão."""
        if session_id not in self.conversation_contexts:
            return None
        
        context = self.conversation_contexts[session_id]
        
        return {
            "session_id": session_id,
            "queries_count": len(context.previous_queries),
            "interactions_count": len(context.conversation_history),
            "last_queries": context.previous_queries[-3:] if context.previous_queries else [],
            "domain_preferences": context.domain_preferences
        }

    def is_conversational_llm_available(self) -> bool:
        """Verifica se o LLM conversacional está disponível."""
        return self.conversational_llm.is_available()

    def get_service_status(self) -> Dict[str, Any]:
        """Retorna status completo do serviço."""
        return {
            "conversational_llm_available": self.is_conversational_llm_available(),
            "memory_enabled": self.enable_memory,
            "active_sessions": len(self.conversation_contexts),
            "llm_model": self.conversational_llm.config.model_name,
            "available_prompt_types": list(self.prompt_service.get_available_templates().keys())
        }