#!/usr/bin/env python3
"""
TXT2SQL Agent with Clean Architecture - Following Single Responsibility Principle

This new implementation addresses all SRP violations mentioned in the presentation:
- Database connection management: IDatabaseConnectionService
- LLM communication: ILLMCommunicationService  
- Schema introspection: ISchemaIntrospectionService
- User interface logic: IUserInterfaceService
- Error handling: IErrorHandlingService
- Query processing: IQueryProcessingService

Each service has a single, well-defined responsibility and can be tested independently.
"""

import sys
import argparse
from typing import Optional

# Import the clean architecture components
from src.application.container.dependency_injection import (
    ContainerFactory, 
    ServiceConfig
)
from src.application.orchestrator.text2sql_orchestrator import (
    Text2SQLOrchestrator,
    OrchestratorConfig
)
from src.application.services.user_interface_service import InterfaceType


def create_service_config(args) -> ServiceConfig:
    """Create service configuration from command line arguments"""
    return ServiceConfig(
        # Database configuration
        database_type="sqlite",
        database_path=args.database_path,
        
        # LLM configuration
        llm_provider="ollama",
        llm_model=args.model,
        llm_temperature=0.0,
        llm_timeout=args.timeout,
        llm_max_retries=3,
        
        # Schema configuration
        schema_type="sus",
        
        # UI configuration
        ui_type="cli",
        interface_type=InterfaceType.CLI_INTERACTIVE if args.interactive else InterfaceType.CLI_BASIC,
        
        # Error handling configuration
        error_handling_type="comprehensive",
        enable_error_logging=args.enable_logging,
        
        # Query processing configuration
        query_processing_type="comprehensive"
    )


def create_orchestrator_config(args) -> OrchestratorConfig:
    """Create orchestrator configuration from command line arguments"""
    return OrchestratorConfig(
        max_query_length=1000,
        enable_query_history=True,
        enable_statistics=True,
        session_timeout=3600,
        enable_conversational_response=True,  # Enable multi-LLM conversational responses
        conversational_fallback=True          # Enable fallback if conversational LLM fails
    )


def main():
    """Main entry point with clean architecture"""
    parser = argparse.ArgumentParser(
        description="TXT2SQL Claude - Arquitetura Limpa seguindo Princípios SOLID",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  python txt2sql_agent_clean.py                    # Usar configurações padrão
  python txt2sql_agent_clean.py --model mistral    # Usar modelo Mistral
  python txt2sql_agent_clean.py --basic            # Interface básica (sem emojis)
  python txt2sql_agent_clean.py --query "Quantas mortes em Porto Alegre?"  # Query única

Arquitetura:
  Este agente segue os princípios SOLID com separação clara de responsabilidades:
  • DatabaseConnectionService: Gerencia conexões com banco
  • LLMCommunicationService: Comunica com modelos LLM
  • SchemaIntrospectionService: Analisa schema do banco
  • UserInterfaceService: Gerencia interação com usuário
  • ErrorHandlingService: Trata todos os erros
  • QueryProcessingService: Processa consultas
  • DependencyContainer: Injeta dependências
  • Text2SQLOrchestrator: Coordena todos os serviços
        """
    )
    
    # Database options
    parser.add_argument(
        "--database-path", 
        default="sus_database.db",
        help="Caminho para o banco de dados SQLite (padrão: sus_database.db)"
    )
    
    # LLM options
    parser.add_argument(
        "--model", 
        default="llama3",
        help="Modelo LLM para usar (padrão: llama3)"
    )
    parser.add_argument(
        "--timeout", 
        type=int, 
        default=120,
        help="Timeout para requisições LLM em segundos (padrão: 120)"
    )
    
    # Interface options
    parser.add_argument(
        "--interactive", 
        action="store_true",
        help="Usar interface interativa com emojis (padrão)"
    )
    parser.add_argument(
        "--basic", 
        action="store_true",
        help="Usar interface básica sem emojis"
    )
    
    # Query options
    parser.add_argument(
        "--query", 
        type=str,
        help="Executar uma única consulta e sair"
    )
    
    # System options
    parser.add_argument(
        "--enable-logging", 
        action="store_true", 
        default=True,
        help="Habilitar logging de erros (padrão: habilitado)"
    )
    parser.add_argument(
        "--disable-logging", 
        action="store_true",
        help="Desabilitar logging de erros"
    )
    parser.add_argument(
        "--health-check", 
        action="store_true",
        help="Executar verificação de saúde do sistema e sair"
    )
    parser.add_argument(
        "--version", 
        action="store_true",
        help="Mostrar informações de versão e arquitetura"
    )
    
    args = parser.parse_args()
    
    # Handle version info
    if args.version:
        print("""
TXT2SQL Claude - Arquitetura Limpa
====================================

Versão: 2.0.0
Arquitetura: Clean Architecture com SOLID principles
Última atualização: Janeiro 2025

Componentes:
• DatabaseConnectionService: Gerenciamento de conexões
• LLMCommunicationService: Comunicação com LLM
• SchemaIntrospectionService: Introspecção de schema
• UserInterfaceService: Interface com usuário
• ErrorHandlingService: Tratamento de erros
• QueryProcessingService: Processamento de consultas
• DependencyContainer: Injeção de dependências
• Text2SQLOrchestrator: Orquestração

Melhorias sobre versão anterior:
✅ Violações SRP corrigidas
✅ Separação clara de responsabilidades
✅ Injeção de dependências
✅ Testabilidade melhorada
✅ Manutenibilidade aumentada
""")
        return
    
    # Process arguments
    if args.disable_logging:
        args.enable_logging = False
    
    if args.basic:
        args.interactive = False
    else:
        args.interactive = True
    
    try:
        # Create configuration
        service_config = create_service_config(args)
        orchestrator_config = create_orchestrator_config(args)
        
        # Create dependency container
        container = ContainerFactory.create_container_with_config(service_config)
        
        # Health check mode
        if args.health_check:
            print("🔍 Executando verificação de saúde do sistema...")
            container.initialize()
            health_status = container.health_check()
            
            print(f"\n📊 Status do Sistema: {health_status['status'].upper()}")
            print("=" * 50)
            
            for service_name, service_health in health_status['services'].items():
                status_icon = "✅" if service_health.get('healthy', False) else "❌"
                print(f"{status_icon} {service_name.title()}: {'OK' if service_health.get('healthy', False) else 'ERRO'}")
            
            if health_status['status'] != 'healthy':
                print(f"\n⚠️ Sistema não está completamente saudável")
                sys.exit(1)
            else:
                print(f"\n🎉 Sistema funcionando perfeitamente!")
            return
        
        # Create orchestrator
        orchestrator = Text2SQLOrchestrator(container, orchestrator_config)
        
        # Single query mode
        if args.query:
            print(f"🔍 Processando consulta: {args.query}")
            result = orchestrator.process_single_query(args.query)
            
            if result.success:
                print(f"✅ Resultado: {result.row_count} registros encontrados")
                if result.results:
                    if len(result.results) == 1 and len(result.results[0]) == 1:
                        value = list(result.results[0].values())[0]
                        print(f"📊 Valor: {value}")
                print(f"⏱️ Tempo de execução: {result.execution_time:.2f}s")
                print(f"🔧 SQL: {result.sql_query}")
            else:
                print(f"❌ Erro: {result.error_message}")
                sys.exit(1)
            return
        
        # Interactive session mode
        orchestrator.start_interactive_session()
        
    except KeyboardInterrupt:
        print("\n\n👋 Até logo!")
        sys.exit(0)
    
    except Exception as e:
        print(f"❌ Erro fatal: {str(e)}")
        print("\n💡 Dicas para resolução:")
        print("• Verifique se o Ollama está rodando: ollama serve")
        print("• Verifique se o modelo está instalado: ollama pull llama3")
        print("• Verifique se o banco de dados existe: python database_setup.py")
        print("• Execute health check: python txt2sql_agent_clean.py --health-check")
        sys.exit(1)


if __name__ == "__main__":
    main()