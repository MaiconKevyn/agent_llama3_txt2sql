"""
Serviço de templates de prompts especializados para o domínio SUS.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum


class PromptType(Enum):
    """Tipos de prompts disponíveis."""
    BASIC_RESPONSE = "basic_response"
    STATISTICAL_ANALYSIS = "statistical_analysis"
    COMPARATIVE_ANALYSIS = "comparative_analysis"
    TREND_ANALYSIS = "trend_analysis"
    GEOGRAPHIC_ANALYSIS = "geographic_analysis"
    ERROR_EXPLANATION = "error_explanation"
    SUGGESTION_RESPONSE = "suggestion_response"


@dataclass
class PromptTemplate:
    """Template de prompt com metadados."""
    name: str
    system_prompt: str
    user_template: str
    response_format: str
    specialized_knowledge: List[str]


class SUSPromptTemplateService:
    """
    Serviço especializado em templates de prompts para o domínio SUS.
    Fornece prompts otimizados para diferentes tipos de análise de dados de saúde.
    """

    def __init__(self):
        self.templates = self._initialize_templates()
        self.sus_knowledge_base = self._initialize_sus_knowledge()

    def _initialize_templates(self) -> Dict[PromptType, PromptTemplate]:
        """Inicializa os templates de prompts especializados."""
        return {
            PromptType.BASIC_RESPONSE: PromptTemplate(
                name="Resposta Básica SUS",
                system_prompt=self._get_base_sus_system_prompt(),
                user_template=self._get_basic_response_template(),
                response_format="conversational",
                specialized_knowledge=["terminologia_sus", "estrutura_dados"]
            ),
            
            PromptType.STATISTICAL_ANALYSIS: PromptTemplate(
                name="Análise Estatística SUS",
                system_prompt=self._get_statistical_system_prompt(),
                user_template=self._get_statistical_template(),
                response_format="analytical",
                specialized_knowledge=["estatisticas_saude", "indicadores_sus", "epidemiologia"]
            ),
            
            PromptType.COMPARATIVE_ANALYSIS: PromptTemplate(
                name="Análise Comparativa SUS",
                system_prompt=self._get_comparative_system_prompt(),
                user_template=self._get_comparative_template(),
                response_format="comparative",
                specialized_knowledge=["comparacao_regional", "benchmarking_saude"]
            ),
            
            PromptType.TREND_ANALYSIS: PromptTemplate(
                name="Análise de Tendências SUS",
                system_prompt=self._get_trend_system_prompt(),
                user_template=self._get_trend_template(),
                response_format="temporal",
                specialized_knowledge=["series_temporais", "tendencias_saude"]
            ),
            
            PromptType.GEOGRAPHIC_ANALYSIS: PromptTemplate(
                name="Análise Geográfica SUS",
                system_prompt=self._get_geographic_system_prompt(),
                user_template=self._get_geographic_template(),
                response_format="geographic",
                specialized_knowledge=["geografia_saude", "regioes_brasil"]
            ),
            
            PromptType.ERROR_EXPLANATION: PromptTemplate(
                name="Explicação de Erros SUS",
                system_prompt=self._get_error_system_prompt(),
                user_template=self._get_error_template(),
                response_format="explanatory",
                specialized_knowledge=["resolucao_problemas", "dados_sus"]
            ),
            
            PromptType.SUGGESTION_RESPONSE: PromptTemplate(
                name="Sugestões de Análise SUS",
                system_prompt=self._get_suggestion_system_prompt(),
                user_template=self._get_suggestion_template(),
                response_format="suggestive",
                specialized_knowledge=["analise_avancada", "insights_saude"]
            )
        }

    def _initialize_sus_knowledge(self) -> Dict[str, str]:
        """Inicializa a base de conhecimento especializada do SUS."""
        return {
            "terminologia_sus": """
            TERMINOLOGIA SUS:
            - CNES: Cadastro Nacional de Estabelecimentos de Saúde
            - DATASUS: Departamento de Informática do SUS
            - SIA: Sistema de Informações Ambulatoriais
            - SIH: Sistema de Informações Hospitalares
            - SINASC: Sistema de Informações sobre Nascidos Vivos
            - SIM: Sistema de Informações sobre Mortalidade
            - CID-10: Classificação Internacional de Doenças
            - SIGTAP: Sistema de Gerenciamento da Tabela de Procedimentos
            - AIH: Autorização de Internação Hospitalar
            - APAC: Autorização de Procedimentos de Alta Complexidade
            """,
            
            "estrutura_dados": """
            ESTRUTURA DOS DADOS SUS:
            - Estabelecimentos de saúde identificados por código CNES
            - Procedimentos codificados conforme SIGTAP
            - Diagnósticos seguem classificação CID-10
            - Dados organizados por estado, município e estabelecimento
            - Informações temporais por mês/ano de competência
            """,
            
            "indicadores_sus": """
            PRINCIPAIS INDICADORES SUS:
            - Taxa de mortalidade infantil
            - Cobertura de vacinação
            - Índice de leitos por habitante
            - Tempo médio de internação
            - Taxa de ocupação hospitalar
            - Índice de consultas per capita
            - Cobertura da Atenção Básica
            """,
            
            "regioes_brasil": """
            ORGANIZAÇÃO GEOGRÁFICA SUS:
            - 5 regiões: Norte, Nordeste, Centro-Oeste, Sudeste, Sul
            - 27 unidades federativas (26 estados + DF)
            - Mais de 5.500 municípios
            - Regiões de Saúde para planejamento
            - Macrorregiões e microrregiões de saúde
            """
        }

    def _get_base_sus_system_prompt(self) -> str:
        """Prompt base do sistema para domínio SUS."""
        return """
        Você é um assistente especialista em dados do Sistema Único de Saúde (SUS) brasileiro.
        Sua expertise inclui análise de dados de saúde pública, terminologia médica em português,
        estrutura organizacional do SUS e interpretação de indicadores de saúde.

        SUAS RESPONSABILIDADES:
        - Transformar dados SQL em insights de saúde pública
        - Explicar contexto e relevância dos dados SUS
        - Usar terminologia médica e do SUS apropriada
        - Fornecer interpretações práticas para gestores de saúde
        - Manter linguagem profissional mas acessível

        SEMPRE CONSIDERE:
        - Impacto na saúde pública
        - Relevância para gestão em saúde
        - Contexto epidemiológico brasileiro
        - Implicações para políticas públicas de saúde
        """

    def _get_basic_response_template(self) -> str:
        """Template para resposta básica."""
        return """
        PERGUNTA DO USUÁRIO: {user_query}
        CONSULTA SQL: {sql_query}
        RESULTADOS: {sql_results}
        
        Transforme estes dados em uma resposta clara e informativa.
        Inclua contexto relevante sobre o SUS e implicações práticas dos dados.
        
        FORMATO DA RESPOSTA:
        1. Resposta direta à pergunta
        2. Interpretação dos dados
        3. Contexto relevante do SUS
        4. Observações práticas
        """

    def _get_statistical_system_prompt(self) -> str:
        """Prompt para análise estatística."""
        return self._get_base_sus_system_prompt() + """
        
        ESPECIALIZAÇÃO EM ANÁLISE ESTATÍSTICA:
        - Calcule e explique indicadores de saúde
        - Identifique padrões e anomalias estatísticas
        - Compare com médias nacionais e regionais
        - Avalie significância estatística quando relevante
        - Forneça interpretação epidemiológica
        """

    def _get_statistical_template(self) -> str:
        """Template para análise estatística."""
        return """
        ANÁLISE ESTATÍSTICA SOLICITADA: {user_query}
        DADOS OBTIDOS: {sql_results}
        
        Realize análise estatística completa incluindo:
        - Medidas de tendência central
        - Variabilidade dos dados
        - Comparação com padrões esperados
        - Identificação de outliers
        - Interpretação epidemiológica
        - Recomendações baseadas nos achados
        """

    def _get_comparative_system_prompt(self) -> str:
        """Prompt para análise comparativa."""
        return self._get_base_sus_system_prompt() + """
        
        ESPECIALIZAÇÃO EM ANÁLISE COMPARATIVA:
        - Compare dados entre regiões, estados, municípios
        - Identifique disparidades regionais em saúde
        - Analise performance relativa de estabelecimentos
        - Contextualize diferenças socioeconômicas
        - Sugira fatores explicativos para as diferenças
        """

    def _get_comparative_template(self) -> str:
        """Template para análise comparativa."""
        return """
        COMPARAÇÃO SOLICITADA: {user_query}
        DADOS COMPARATIVOS: {sql_results}
        
        Realize análise comparativa detalhada:
        - Ranking das entidades comparadas
        - Diferenças percentuais significativas
        - Fatores explicativos possíveis
        - Implicações para políticas públicas
        - Recomendações específicas por região/entidade
        """

    def _get_trend_system_prompt(self) -> str:
        """Prompt para análise de tendências."""
        return self._get_base_sus_system_prompt() + """
        
        ESPECIALIZAÇÃO EM ANÁLISE TEMPORAL:
        - Identifique tendências temporais em dados de saúde
        - Detecte sazonalidade e ciclos
        - Analise impacto de políticas públicas ao longo do tempo
        - Projete tendências futuras quando apropriado
        - Correlacione com eventos históricos relevantes
        """

    def _get_trend_template(self) -> str:
        """Template para análise de tendências."""
        return """
        ANÁLISE TEMPORAL SOLICITADA: {user_query}
        DADOS TEMPORAIS: {sql_results}
        
        Analise as tendências temporais:
        - Direção da tendência (crescente/decrescente/estável)
        - Taxa de mudança ao longo do tempo
        - Pontos de inflexão significativos
        - Sazonalidade identificada
        - Fatores explicativos para as mudanças
        - Projeções e implicações futuras
        """

    def _get_geographic_system_prompt(self) -> str:
        """Prompt para análise geográfica."""
        return self._get_base_sus_system_prompt() + """
        
        ESPECIALIZAÇÃO EM ANÁLISE GEOGRÁFICA:
        - Analise distribuição espacial de dados de saúde
        - Identifique clusters geográficos
        - Considere fatores socioeconômicos regionais
        - Analise acessibilidade e cobertura geográfica
        - Contextualize diferenças urbano-rurais
        """

    def _get_geographic_template(self) -> str:
        """Template para análise geográfica."""
        return """
        ANÁLISE GEOGRÁFICA SOLICITADA: {user_query}
        DADOS GEOGRÁFICOS: {sql_results}
        
        Analise a distribuição geográfica:
        - Padrões de distribuição espacial
        - Regiões com maior/menor indicador
        - Fatores geográficos explicativos
        - Implicações para acesso aos serviços
        - Recomendações de políticas regionalizadas
        """

    def _get_error_system_prompt(self) -> str:
        """Prompt para explicação de erros."""
        return self._get_base_sus_system_prompt() + """
        
        ESPECIALIZAÇÃO EM RESOLUÇÃO DE PROBLEMAS:
        - Explique erros de forma educativa
        - Sugira correções práticas
        - Forneça contexto sobre limitações dos dados SUS
        - Oriente sobre fontes alternativas de dados
        - Mantenha tom construtivo e útil
        """

    def _get_error_template(self) -> str:
        """Template para explicação de erros."""
        return """
        ERRO ENCONTRADO: {error_message}
        CONSULTA PROBLEMÁTICA: {sql_query}
        PERGUNTA ORIGINAL: {user_query}
        
        Explique o erro de forma construtiva:
        - O que causou o problema
        - Como corrigir a consulta
        - Limitações dos dados SUS relevantes
        - Alternativas de consulta
        - Dicas para futuras consultas
        """

    def _get_suggestion_system_prompt(self) -> str:
        """Prompt para sugestões de análise."""
        return self._get_base_sus_system_prompt() + """
        
        ESPECIALIZAÇÃO EM SUGESTÕES ANALÍTICAS:
        - Sugira análises complementares relevantes
        - Identifique oportunidades de aprofundamento
        - Proponha cruzamentos de dados úteis
        - Recomende visualizações apropriadas
        - Oriente sobre próximos passos analíticos
        """

    def _get_suggestion_template(self) -> str:
        """Template para sugestões."""
        return """
        CONSULTA REALIZADA: {user_query}
        RESULTADOS OBTIDOS: {sql_results}
        
        Com base nos dados, sugira:
        - Análises complementares relevantes
        - Cruzamentos de dados interessantes
        - Comparações úteis
        - Visualizações recomendadas
        - Próximos passos analíticos
        """

    def get_prompt(
        self,
        prompt_type: PromptType,
        user_query: str,
        sql_query: str = "",
        sql_results: Any = None,
        context: Optional[Dict[str, Any]] = None,
        error_message: str = ""
    ) -> str:
        """
        Gera prompt especializado baseado no tipo e contexto.
        
        Args:
            prompt_type: Tipo de prompt a ser gerado
            user_query: Pergunta original do usuário
            sql_query: Query SQL executada
            sql_results: Resultados da query
            context: Contexto adicional
            error_message: Mensagem de erro (se aplicável)
            
        Returns:
            Prompt completo formatado
        """
        template = self.templates[prompt_type]
        
        # Adiciona conhecimento especializado relevante
        specialized_knowledge = self._get_specialized_knowledge(
            template.specialized_knowledge
        )
        
        # Formata os resultados SQL
        formatted_results = self._format_results_for_prompt(sql_results)
        
        # Constrói o prompt completo
        system_prompt = template.system_prompt + "\n\n" + specialized_knowledge
        
        user_prompt = template.user_template.format(
            user_query=user_query,
            sql_query=sql_query,
            sql_results=formatted_results,
            context=context or {},
            error_message=error_message
        )
        
        return f"{system_prompt}\n\n{user_prompt}"

    def _get_specialized_knowledge(self, knowledge_areas: List[str]) -> str:
        """Obtém conhecimento especializado para as áreas especificadas."""
        knowledge_text = ""
        for area in knowledge_areas:
            if area in self.sus_knowledge_base:
                knowledge_text += self.sus_knowledge_base[area] + "\n\n"
        return knowledge_text

    def _format_results_for_prompt(self, sql_results: Any) -> str:
        """Formata resultados SQL para inclusão em prompt."""
        if sql_results is None:
            return "Nenhum resultado encontrado."
        
        if isinstance(sql_results, (list, tuple)):
            if len(sql_results) == 0:
                return "Consulta executada com sucesso, mas não retornou dados."
            
            # Limita resultados para evitar prompts excessivamente longos
            limited_results = sql_results[:15]
            
            formatted = []
            for i, row in enumerate(limited_results, 1):
                formatted.append(f"{i}. {row}")
            
            result_text = "\n".join(formatted)
            
            if len(sql_results) > 15:
                result_text += f"\n... (mostrando 15 de {len(sql_results)} resultados)"
            
            return result_text
        
        return str(sql_results)

    def determine_prompt_type(
        self,
        user_query: str,
        sql_results: Any = None,
        has_error: bool = False
    ) -> PromptType:
        """
        Determina automaticamente o tipo de prompt mais apropriado.
        
        Args:
            user_query: Pergunta do usuário
            sql_results: Resultados SQL (se disponíveis)
            has_error: Se houve erro na consulta
            
        Returns:
            Tipo de prompt mais apropriado
        """
        query_lower = user_query.lower()
        
        if has_error:
            return PromptType.ERROR_EXPLANATION
        
        # Palavras-chave para diferentes tipos de análise
        statistical_keywords = ['média', 'total', 'soma', 'count', 'quantidade', 'estatística']
        comparative_keywords = ['comparar', 'versus', 'diferença', 'maior', 'menor', 'ranking']
        trend_keywords = ['tendência', 'evolução', 'histórico', 'tempo', 'crescimento', 'ano']
        geographic_keywords = ['estado', 'município', 'região', 'cidade', 'geografia', 'mapa']
        
        if any(keyword in query_lower for keyword in statistical_keywords):
            return PromptType.STATISTICAL_ANALYSIS
        elif any(keyword in query_lower for keyword in comparative_keywords):
            return PromptType.COMPARATIVE_ANALYSIS
        elif any(keyword in query_lower for keyword in trend_keywords):
            return PromptType.TREND_ANALYSIS
        elif any(keyword in query_lower for keyword in geographic_keywords):
            return PromptType.GEOGRAPHIC_ANALYSIS
        else:
            return PromptType.BASIC_RESPONSE

    def get_available_templates(self) -> Dict[str, Dict[str, Any]]:
        """Retorna informações sobre todos os templates disponíveis."""
        return {
            prompt_type.value: {
                "name": template.name,
                "response_format": template.response_format,
                "specialized_knowledge": template.specialized_knowledge
            }
            for prompt_type, template in self.templates.items()
        }