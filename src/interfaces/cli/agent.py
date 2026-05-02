from __future__ import annotations

import argparse
import os
import sys
import traceback

from dotenv import load_dotenv

# Add project root to path
project_root = os.path.join(os.path.dirname(__file__), '..', '..', '..')
sys.path.append(project_root)

# Load environment variables from the local .env file
load_dotenv()


def _print_llm_configuration(orchestrator: LangGraphOrchestrator):
    """Print a concise summary of configured LLMs (SQL + conversational)."""
    try:
        cfg = orchestrator.app_config
        sql_provider = getattr(cfg, "llm_provider", "unknown")
        sql_model = getattr(cfg, "llm_model", "unknown")
        sql_temp = getattr(cfg, "llm_temperature", None)
        sql_timeout = getattr(cfg, "llm_timeout", None)

        conv_model = getattr(cfg, "conversational_llm_model", sql_model)
        conv_temp = getattr(cfg, "conversational_llm_temperature", None)
        conv_timeout = getattr(cfg, "conversational_llm_timeout", None)

        same_model = (str(sql_model) == str(conv_model))

        print(" LLM Configuration")
        print("-" * 70)
        print(f" SQL generation LLM : {sql_provider}/{sql_model}  (temp={sql_temp}, timeout={sql_timeout}s)")
        print(f" Conversational LLM : {conv_model}  (temp={conv_temp}, timeout={conv_timeout}s)"
              + ("  [same as SQL]" if same_model else ""))
        print("-" * 70)
    except Exception:
        # Do not break execution if any attribute is missing
        pass


def create_app_config(args) -> ApplicationConfig:
    """Create application configuration from command line arguments"""
    from src.application.config.simple_config import ApplicationConfig, InterfaceType

    # Use defaults from ApplicationConfig and override with command line args when explicitly provided
    config = ApplicationConfig()
    
    # Override with command line arguments if they differ from defaults
    # Database URL (PostgreSQL)
    if hasattr(args, 'db_url') and args.db_url:
        config.database_type = "postgresql"
        config.database_path = args.db_url
    
    # LLM model
    # Only override if --model was explicitly provided
    if hasattr(args, 'model') and args.model:
        config.llm_model = args.model
    if hasattr(args, 'timeout') and args.timeout != 120:
        config.llm_timeout = args.timeout
    # Interface sempre interativa; --basic removido
    config.interface_type = InterfaceType.CLI_INTERACTIVE
    if hasattr(args, 'enable_logging'):
        config.enable_error_logging = args.enable_logging
    
    return config


def create_orchestrator_config(args) -> OrchestratorConfig:
    """Create orchestrator configuration from command line arguments"""
    from src.application.config.simple_config import OrchestratorConfig

    return OrchestratorConfig(
        max_query_length=1000,
        enable_query_history=True,
        enable_statistics=True,
        session_timeout=3600,
        enable_conversational_response=True,  # Enable multi-LLM conversational responses
        conversational_fallback=True,         # Enable fallback if conversational LLM fails
        table_selection_preset=args.table_selection_preset,
        table_selection_mode=args.table_selection_mode,
        table_selection_description_variant=args.table_selection_description_variant,
        table_selection_prompt_variant=args.table_selection_prompt_variant,
    )


def debug_query_execution(orchestrator, user_query: str):
    # Initialize logger
    from src.utils.logging_config import get_cli_logger

    logger = get_cli_logger()
    """
    Execute query with detailed step-by-step debugging
    
    Args:
        orchestrator: LangGraphOrchestrator instance
        user_query: User's natural language question
    """
    import time
    
    logger.info("Starting debug mode execution", extra={"query": user_query})
    print(" DEBUG MODE: Workflow Step-by-Step Analysis")
    print("=" * 70)
    print(f" Query: {user_query}")
    print("=" * 70)
    # Show configured LLMs for transparency
    _print_llm_configuration(orchestrator)
    
    # Track debug data
    debug_data = {
        "question": user_query,
        "start_time": time.time(),
        "steps": [],
        "classification": None,
        "tables_discovered": None,
        "tables_selected": None,
        "sql_generated": None,
        "sql_validated": None,
        "execution_results": None,
        "final_response": None
    }
    
    step_counter = 1
    
    try:
        # Create config for streaming with checkpointer
        config = {
            "configurable": {
                "thread_id": f"debug_{hash(user_query) % 10000}"
            }
        }
        
        # Use streaming process_query to preserve workflow metadata in debug mode
        session_id = f"debug_{hash(user_query) % 10000}"
        results = orchestrator.process_query(
            user_query=user_query,
            session_id=session_id,
            streaming=True,
            config=config,
            run_name=f"debug_query_{session_id}",
            tags=["debug", "cli_agent"],
            metadata={"debug_mode": True, "script": "src/interfaces/cli/agent.py"}
        )
        
        # Process streaming results
        for update in results:
            for node_name, node_state in update.items():
                
                print(f"\n STEP {step_counter}: {node_name.upper()}")
                print("-" * 50)
                
                # Extract and display relevant data based on node type
                step_data = {"node": node_name, "data": {}}
                
                # 1. Classification Node
                if node_name == "classify_query":
                    route = node_state.get("query_route")
                    classification = node_state.get("classification")
                    
                    # Extract route and confidence correctly
                    route_str = route.value if route else "N/A"
                    confidence = classification.confidence_score if classification else "N/A"
                    
                    debug_data["classification"] = route_str
                    step_data["data"]["route"] = route_str
                    step_data["data"]["confidence"] = confidence
                    
                    print(f" Classification: {route_str}")
                    print(f" Confidence: {confidence}")
                    if route:
                        print(f"   Next: {'SQL Pipeline' if route_str == 'DATABASE' else 'Direct Response'}")
                        if classification:
                            print(f"   Reasoning: {classification.reasoning}")
                            print(f"   Requires Tools: {classification.requires_tools}")
                
                # 2. Table Discovery Node
                elif node_name == "list_tables":
                    available = node_state.get("available_tables", [])
                    selected = node_state.get("selected_tables", [])
                    
                    debug_data["tables_discovered"] = available
                    debug_data["tables_selected"] = selected
                    step_data["data"]["available_tables"] = available
                    step_data["data"]["selected_tables"] = selected
                    
                    print(f"  Tables Available: {len(available)}")
                    print(f"     Full list: {available[:5]}{'...' if len(available) > 5 else ''}")
                    print(f" Tables Selected: {len(selected)}")
                    print(f"     Selected: {selected}")
                    
                    if selected:
                        if "atendimentos" in selected:
                            print("     Great! Selected 'atendimentos' junction for procedure queries")
                        if "procedimentos" in selected:
                            print("     Great! Selected 'procedimentos' table for procedure queries")
                
                # 3. Schema Node
                elif node_name == "get_schema":
                    schema_context = node_state.get("schema_context", "")
                    enhanced_mappings = node_state.get("enhanced_with_sus_mappings", False)
                    
                    step_data["data"]["schema_size"] = len(schema_context)
                    step_data["data"]["sus_enhanced"] = enhanced_mappings
                    
                    print(f" Schema Context: {len(schema_context)} characters")
                    print(f" SUS Mappings: {' Enhanced' if enhanced_mappings else ' Not enhanced'}")
                    
                    # Show partial schema for debug
                    if schema_context and len(schema_context) > 100:
                        print(f"     Schema preview: {schema_context[:100]}...")
                
                # 4. SQL Generation Node
                elif node_name == "generate_sql":
                    sql = node_state.get("generated_sql", "")
                    selected_tables = node_state.get("selected_tables", [])
                    
                    debug_data["sql_generated"] = sql
                    step_data["data"]["sql"] = sql
                    step_data["data"]["tables_used"] = selected_tables
                    
                    print(" SQL Generated:")
                    print(f"     Query: {sql}")
                    print(f"      Using tables: {selected_tables}")
                    
                    # Validate SQL quality
                    if sql:
                        if "COUNT(*)" in sql.upper():
                            print("     Count query detected")
                        if any(table in sql.lower() for table in ["atendimentos", "procedimentos", "cid"]):
                            print("     Using specialized healthcare tables")
                        if "SELECT *" in sql.upper():
                            print("      Warning: SELECT * detected (might be inefficient)")
                
                # 5. SQL Validation Node
                elif node_name == "validate_sql":
                    validated_sql = node_state.get("validated_sql", "")
                    validation_errors = node_state.get("validation_errors", [])
                    
                    debug_data["sql_validated"] = validated_sql
                    step_data["data"]["validated_sql"] = validated_sql
                    step_data["data"]["errors"] = validation_errors
                    
                    print(" SQL Validation:")
                    if validated_sql:
                        print("     Validation passed")
                        print(f"     Validated SQL: {validated_sql}")
                    
                    if validation_errors:
                        print(f"     Validation errors: {validation_errors}")
                
                # 6. SQL Execution Node
                elif node_name == "execute_sql":
                    execution_result = node_state.get("sql_execution_result")
                    if hasattr(execution_result, 'results'):
                        # SQLExecutionResult object
                        results = execution_result.results or []
                        success = execution_result.success
                        error = execution_result.error_message or ""
                    else:
                        # Dictionary format
                        results = execution_result.get("results", []) if execution_result else []
                        success = execution_result.get("success", False) if execution_result else False
                        error = execution_result.get("error_message", "") if execution_result else ""
                    
                    debug_data["execution_results"] = {
                        "success": success,
                        "row_count": len(results),
                        "first_row": results[0] if results else None
                    }
                    step_data["data"]["execution"] = debug_data["execution_results"]
                    
                    print(" SQL Execution:")
                    if success:
                        print("     Execution successful")
                        print(f"     Results: {len(results)} rows returned")
                        if results:
                            print(f"     First row: {results[0]}")
                            # Handle different result formats
                            first_row = results[0]
                            if isinstance(first_row, dict) and 'result' in first_row:
                                # Extract count from string format
                                result_str = first_row['result']
                                if result_str.startswith('[') and result_str.endswith(']'):
                                    try:
                                        # Parse [(569405,)] format
                                        import ast
                                        parsed_result = ast.literal_eval(result_str)
                                        if parsed_result and len(parsed_result) > 0:
                                            count_value = parsed_result[0][0] if isinstance(parsed_result[0], tuple) else parsed_result[0]
                                            print(f"     Count result: {count_value:,}")
                                    except:
                                        pass
                            elif isinstance(first_row, (list, tuple)) and len(first_row) == 1:
                                count_value = first_row[0]
                                if isinstance(count_value, (int, float)):
                                    print(f"     Count result: {count_value:,}")
                    else:
                        print(f"     Execution failed: {error}")
                
                # 7. Clarification Node
                elif node_name == "clarification":
                    question = node_state.get("final_response", "") or node_state.get("clarification_question", "")
                    success = node_state.get("success", False)
                    
                    debug_data["final_response"] = question
                    step_data["data"]["response"] = question
                    step_data["data"]["success"] = success
                    
                    print(" Clarification Request:")
                    print(f"     Question: {question}")
                    print(f"     Success: {success}")

                # 8. Response Generation Node
                elif node_name == "generate_response":
                    # Extract response from the correct field
                    response = node_state.get("final_response", "") or node_state.get("response", "")
                    success = node_state.get("success", False)
                    completed = node_state.get("completed", False)
                    
                    debug_data["final_response"] = response
                    step_data["data"]["response"] = response
                    step_data["data"]["success"] = success
                    step_data["data"]["completed"] = completed
                    
                    print(" Response Generation:")
                    print(f"     Final response: {response}")
                    print(f"     Success: {success}")
                    print(f"     Completed: {completed}")
                
                # 8. Generic state info
                else:
                    # Show any other relevant state information
                    relevant_keys = [k for k in node_state.keys() if not k.startswith("_")]
                    if relevant_keys:
                        print(f" State keys: {relevant_keys}")
                
                # Add step to debug data
                debug_data["steps"].append(step_data)
                step_counter += 1
                
                print("-" * 50)
        
        # Final summary
        total_time = time.time() - debug_data["start_time"]
        
        print("\n DEBUG SUMMARY")
        print("=" * 70)
        print(f" Query: {debug_data['question']}")
        print(f" Classification: {debug_data['classification']}")
        print(f"  Tables discovered: {len(debug_data['tables_discovered']) if debug_data['tables_discovered'] else 0}")
        print(f" Tables selected: {debug_data['tables_selected']}")
        print(f" SQL generated: {debug_data['sql_generated']}")
        if debug_data['execution_results']:
            results = debug_data['execution_results']
            print(f" Execution: {' Success' if results['success'] else ' Failed'} ({results['row_count']} rows)")
        print(f" Response: {debug_data['final_response'][:100] if debug_data['final_response'] else 'N/A'}{'...' if debug_data['final_response'] and len(debug_data['final_response']) > 100 else ''}")
        print(f"   Total time: {total_time:.2f}s")
        print(f" Steps executed: {len(debug_data['steps'])}")
        
    except KeyboardInterrupt:
        logger.info("Debug session interrupted by user")
        print("\n\n Debug interrupted by user")
    except Exception as e:
        logger.error("Debug execution error", extra={"error": str(e)})
        print(f"\n Debug error: {str(e)}")
        traceback.print_exc()


def start_interactive_debug_session(orchestrator):
    # Initialize logger
    from src.utils.logging_config import get_cli_logger

    logger = get_cli_logger()
    """
    Start interactive session with debug mode enabled
    """
    logger.info("Starting interactive debug session")
    print(" TEXT2SQL DEBUG MODE - Interactive Session")
    print("=" * 60)
    print("Digite 'exit', 'quit' ou 'sair' para sair")
    print("Cada query será executada com debug detalhado")
    print("=" * 60)
    _print_llm_configuration(orchestrator)
    
    while True:
        try:
            user_input = input("\n Sua pergunta (debug mode): ").strip()
            
            # Handle exit commands
            if user_input.lower() in ['exit', 'quit', 'sair']:
                logger.info("Debug session ended by user")
                print("\n Até logo!")
                break
            elif not user_input:
                continue
            
            # Execute query with debug
            print()  # Empty line for better readability
            debug_query_execution(orchestrator, user_input)
            
        except KeyboardInterrupt:
            logger.info("Debug session interrupted by user")
            print("\n\n Até logo!")
            break
        except Exception as e:
            logger.error("Interactive debug session error", extra={"error": str(e)})
            print(f"\n Erro interno: {str(e)}")
            print("Digite 'exit' para sair ou tente outra pergunta.")


def main():
    # Initialize logger
    from src.agent.orchestrator import LangGraphOrchestrator
    from src.utils.logging_config import get_cli_logger

    logger = get_cli_logger()
    """Main entry point with clean architecture"""
    parser = argparse.ArgumentParser(
        description="TXT2SQL - LangGraph V3 (PostgreSQL)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
        Exemplos de uso:
          python src/interfaces/cli/agent.py                              # Padrão (interativo)
          python src/interfaces/cli/agent.py --model gpt-4o-mini          # Escolher modelo OpenAI
          
          python src/interfaces/cli/agent.py --query "Quantas mortes em Porto Alegre?"   # Query única
          python src/interfaces/cli/agent.py --query "Quantas mortes?" --debug-steps     # Query c/ debug
          python src/interfaces/cli/agent.py --debug-steps                # Modo interativo com debug
          python src/interfaces/cli/agent.py --db-url postgresql+psycopg2://user:pass@localhost:5432/sihrd5  # DB via CLI
        
        Arquitetura (LangGraph V3):
          • LangGraphOrchestrator: Orquestração principal
          • Nodes: Classification, Table Discovery, Schema, SQL Gen, Validation, Execution, Response
          • LLM Manager + SQLDatabaseToolkit (LangChain)
          • DatabaseConnectionService (PostgreSQL)
          • Logging centralizado (logs/*)
          • Interfaces: CLI e API FastAPI
        """
    )
    
    # Database options (PostgreSQL)
    parser.add_argument(
        "--db-url",
        default=None,
        help=(
            "URL de conexão PostgreSQL (SQLAlchemy), por ex.: "
            "postgresql+psycopg2://usuario:senha@localhost:5432/sihrd5. "
            "Se omitido, usa ApplicationConfig ou a variável de ambiente DATABASE_URL."
        ),
    )
    
    # LLM options
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Modelo LLM para SQL. Se omitido, usa o padrão do ApplicationConfig. "
            "Ex.: --model mistral"
        )
    )
    parser.add_argument(
        "--timeout", 
        type=int, 
        default=120,
        help="Timeout para requisições LLM em segundos (padrão: 120)"
    )
    parser.add_argument(
        "--show-models",
        action="store_true",
        help="Exibe os modelos LLM configurados (SQL e conversacional)"
    )
    
    # Interface options: --interactive removido (modo interativo é padrão)
    # --basic removido: CLI é interativo por padrão
    
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
    parser.add_argument(
        "--visualize-workflow", 
        action="store_true",
        help="Gerar diagrama visual do workflow LangGraph e sair"
    )
    parser.add_argument(
        "--debug-workflow", 
        action="store_true",
        help="Mostrar estrutura textual do workflow LangGraph e sair"
    )
    parser.add_argument(
        "--debug-steps", 
        action="store_true",
        help="Mostrar estados detalhados de cada step do workflow durante execução"
    )
    from src.application.prompts.table_selection.catalog import (
        get_available_description_variants,
        get_available_prompt_variants,
        get_available_table_selection_presets,
    )

    parser.add_argument(
        "--table-selection-preset",
        default="llm_best",
        choices=get_available_table_selection_presets(),
        help="Preset nomeado do selector de tabelas usado pelo agente.",
    )
    parser.add_argument(
        "--table-selection-mode",
        default="full_cascade",
        choices=[
            "full_cascade",
            "heuristic_only",
            "embedding_only",
            "heuristic_embedding_only",
            "llm_only",
            "llm_disabled_current_fallback",
        ],
        help="Modo do selector de tabelas para a execução atual.",
    )
    parser.add_argument(
        "--table-selection-description-variant",
        default="current",
        choices=get_available_description_variants(),
        help="Variante das descrições de tabelas usada no fallback/selector com LLM.",
    )
    parser.add_argument(
        "--table-selection-prompt-variant",
        default="current",
        choices=get_available_prompt_variants(),
        help="Variante do prompt usada no selector com LLM.",
    )
    
    args = parser.parse_args()
    
    # Handle version info
    if args.version:
        print("""
TXT2SQL Claude - LangGraph V3
====================================

Versão: 3.0.0
Arquitetura: LangGraph SQL Agent com PostgreSQL
Última atualização: Agosto 2025

Componentes LangGraph V3:
• LangGraphOrchestrator: Orquestração principal
• Query Classification Node: Roteamento inteligente
• Table Discovery Node: Seleção inteligente de tabelas
• Schema Introspection Node: Análise de schema
• SQL Generation Node: Geração de SQL
• SQL Validation Node: Validação de SQL
• SQL Execution Node: Execução no PostgreSQL
• Response Generation Node: Formatação de resposta

Melhorias da V3:
 Migração completa para LangGraph
 PostgreSQL com 16 tabelas especializadas (sihrd5)
 Seleção inteligente de tabelas (75%+ precisão)
 Suporte a healthcare brasileiro (SUS)
 Visualização de workflow (--visualize-workflow)
     Debug interativo com retry mechanisms
     OpenAI tool calling (gpt-4o / gpt-4o-mini)

Database: PostgreSQL sihrd5 (18M+ internacoes, 37M+ atendimentos)
Domínio: Healthcare brasileiro (internações, procedimentos, diagnósticos)
""")
        return
    
    # Process arguments
    if args.disable_logging:
        args.enable_logging = False
    
    # Modo interativo é padrão; --interactive foi removido

    # Validar chave OpenAI antes de continuar
    if not os.getenv("OPENAI_API_KEY"):
        print("Erro: defina a variável de ambiente OPENAI_API_KEY para usar o modelo OpenAI.")
        sys.exit(1)
    
    try:
        # Create configuration
        app_config = create_app_config(args)
        orchestrator_config = create_orchestrator_config(args)
        
        # Create orchestrator directly with configurations (LangGraph V3)
        orchestrator = LangGraphOrchestrator(app_config, orchestrator_config)
        
        # Optionally display configured LLMs up-front
        if args.show_models:
            _print_llm_configuration(orchestrator)
        
        # Health check mode
        if args.health_check:
            logger.info("Starting system health check")
            print(" Executando verificação de saúde do sistema...")
            health_status = orchestrator.health_check()
            
            print(f"\n Status do Sistema: {health_status['status'].upper()}")
            print("=" * 50)
            
            # Monta serviços a partir da estrutura real do orchestrator
            llm_h = health_status.get("llm_manager", {})
            orch_h = health_status.get("orchestrator", {})
            services = {
                "llm": {"healthy": llm_h.get("status") == "healthy"},
                "database": {"healthy": llm_h.get("components", {}).get("database_status") == "healthy"},
                "workflow": {"healthy": orch_h.get("workflow_status") == "healthy"},
            }
            for service_name, service_health in services.items():
                status_icon = "" if service_health.get('healthy', False) else ""
                print(f"{status_icon} {service_name.title()}: {'OK' if service_health.get('healthy', False) else 'ERRO'}")
            
            if health_status['status'] != 'healthy':
                logger.warning("System health check failed", extra={"status": health_status['status']})
                print("\n Sistema não está completamente saudável")
                sys.exit(1)
            else:
                logger.info("System health check passed")
                print("\n Sistema funcionando perfeitamente!")
            return
        
        # Workflow visualization mode
        if args.visualize_workflow:
            logger.info("Generating workflow visualization")
            print(" Gerando diagrama visual do workflow LangGraph...")
            try:
                out_png = "langgraph_workflow.png"
                orchestrator.save_workflow_diagram(out_png, xray=True)
                if os.path.exists(out_png):
                    logger.info("Workflow diagram generated successfully", extra={"filename": out_png})
                    print(f" Diagrama visual salvo como '{out_png}'")
                    print(" Dica: Abra o arquivo PNG para ver o fluxo completo do agente")
                else:
                    # Fallback saved as Mermaid text
                    out_mmd = out_png.rsplit('.', 1)[0] + ".mmd"
                    if os.path.exists(out_mmd):
                        logger.info("Mermaid source saved", extra={"filename": out_mmd})
                        print(f" PNG indisponível no ambiente; Mermaid salvo como '{out_mmd}'")
                        print(" Dica: Use Mermaid Live Editor ou mmdc para renderizar.")
                    else:
                        print(" Não foi possível salvar o diagrama.")
            except Exception as e:
                logger.error("Failed to generate workflow diagram", extra={"error": str(e)})
                print(f" Erro ao gerar diagrama: {str(e)}")
                sys.exit(1)
            return
        
        # Workflow structure debug mode
        if args.debug_workflow:
            logger.info("Displaying workflow structure")
            print(" Exibindo estrutura textual do workflow LangGraph...")
            try:
                orchestrator.print_workflow_structure()
                print("\n Use --visualize-workflow para gerar diagrama PNG")
            except Exception as e:
                logger.error("Failed to display workflow structure", extra={"error": str(e)})
                print(f" Erro ao exibir estrutura: {str(e)}")
                sys.exit(1)
            return
        
        # Orchestrator already created above for health check compatibility
        
        # Single query mode
        if args.query:
            if args.debug_steps:
                # Debug mode with detailed step-by-step workflow
                debug_query_execution(orchestrator, args.query)
            else:
                # Normal mode with workflow metadata attached to the query run
                logger.info("Processing single query", extra={"query": args.query})
                print(f" Processando consulta: {args.query}")
                if args.show_models:
                    _print_llm_configuration(orchestrator)
                session_id = f"cli_{hash(args.query) % 10000}"
                result = orchestrator.process_query(
                    user_query=args.query,
                    session_id=session_id,
                    streaming=False,
                    run_name=f"cli_query_{session_id}",
                    tags=["production", "cli"],
                    metadata={"script": "src/interfaces/cli/agent.py", "mode": "single_query"}
                )
                
                if result["success"]:
                    logger.info("Query processed successfully", extra={
                        "execution_time": result['execution_time'],
                        "sql_query": result.get('sql_query', '')
                    })
                    # Show response
                    print(f" {result['response']}")
                    print(f"   Tempo de execução: {result['execution_time']:.2f}s")
                    
                    # Show SQL for debugging if available
                    if result.get("sql_query"):
                        print(f" SQL: {result['sql_query']}")
                else:
                    logger.error("Query processing failed", extra={"error": result['error_message']})
                    print(f" Erro: {result['error_message']}")
                    sys.exit(1)
            return
        
        # Interactive session mode
        if args.debug_steps:
            logger.info("Starting interactive debug session")
            start_interactive_debug_session(orchestrator)
        else:
            logger.info("Starting interactive session")
            if args.show_models:
                _print_llm_configuration(orchestrator)
            orchestrator.start_interactive_session()
        
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        print("\n\n Até logo!")
        sys.exit(0)
    
    except Exception as e:
        logger.error("Fatal application error", extra={"error": str(e)})
        print(f" Erro fatal: {str(e)}")
        print("\n Dicas para resolução:")
        print("• Verifique se OPENAI_API_KEY está definido")
        print("• Confirme o modelo configurado (ex.: gpt-4o-mini) e limites de uso da conta")
        print("• Verifique se o banco PostgreSQL está acessível (DATABASE_URL no .env)")
        print("• Execute health check: python src/interfaces/cli/agent.py --health-check")
        sys.exit(1)


if __name__ == "__main__":
    main()
