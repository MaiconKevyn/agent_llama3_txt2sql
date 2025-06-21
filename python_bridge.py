#!/usr/bin/env python3
"""
Python Bridge for DataVisSUS Web Interface
Connects Node.js server to existing Python TXT2SQL architecture
"""

import sys
import os
import json
import io
from datetime import datetime

# Add project root and src to path - Fixed for working directory independence
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = script_dir  # python_bridge.py is in project root
sys.path.append(project_root)
sys.path.append(os.path.join(project_root, 'src'))

try:
    from src.application.container.dependency_injection import (
        ContainerFactory, 
        ServiceConfig
    )
    from src.application.orchestrator.text2sql_orchestrator import (
        Text2SQLOrchestrator,
        OrchestratorConfig
    )
    from src.application.services.user_interface_service import InterfaceType
    from src.application.services.schema_introspection_service import ISchemaIntrospectionService
except ImportError as e:
    # Fallback error response
    error_response = {
        "success": False,
        "error_message": f"Failed to import required modules: {str(e)}",
        "timestamp": datetime.now().isoformat()
    }
    print(json.dumps(error_response))
    sys.exit(1)

# Global agent instance
agent = None

def initialize_agent():
    """Initialize the clean architecture agent"""
    global agent
    
    if agent is not None:
        return agent
    
    try:
        # Suppress colored output by setting environment variable
        os.environ['NO_COLOR'] = '1'
        os.environ['TERM'] = 'dumb'
        
        service_config = ServiceConfig(
            database_type="sqlite",
            database_path=os.path.join(project_root, "sus_database.db"),
            llm_provider="ollama",
            llm_model="llama3",
            llm_temperature=0.0,
            llm_timeout=120,
            llm_max_retries=3,
            schema_type="sus",
            ui_type="cli",
            interface_type=InterfaceType.CLI_BASIC,
            error_handling_type="comprehensive",
            enable_error_logging=True,
            query_processing_type="comprehensive"
        )
        
        orchestrator_config = OrchestratorConfig(
            max_query_length=1000,
            enable_query_history=True,
            enable_statistics=True,
            session_timeout=3600
        )
        
        container = ContainerFactory.create_container_with_config(service_config)
        agent = Text2SQLOrchestrator(container, orchestrator_config)
        
        return agent
        
    except Exception as e:
        raise RuntimeError(f"Failed to initialize agent: {str(e)}")

def process_query(question):
    """Process a query using the TXT2SQL agent"""
    try:
        # Capture stdout to prevent colored output from interfering
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        
        try:
            agent = initialize_agent()
            
            # Use conversational response instead of raw SQL results
            result = agent.process_conversational_query(question)
            
            # Ensure the result has the expected format
            if not isinstance(result, dict):
                return {
                    "success": False,
                    "error_message": "Invalid response format from agent",
                    "question": question,
                    "timestamp": datetime.now().isoformat()
                }
            
            # Add timestamp if not present
            if "timestamp" not in result:
                result["timestamp"] = datetime.now().isoformat()
            
            return result
            
        finally:
            # Restore stdout
            sys.stdout = old_stdout
        
    except Exception as e:
        return {
            "success": False,
            "error_message": str(e),
            "question": question,
            "timestamp": datetime.now().isoformat()
        }

def get_schema():
    """Get database schema information"""
    try:
        agent = initialize_agent()
        schema_service = agent.container.get_service(ISchemaIntrospectionService)
        schema_context = schema_service.get_schema_context()
        
        return {
            "schema": schema_context.formatted_context,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

def main():
    """Main entry point for the bridge script"""
    if len(sys.argv) < 2:
        error_response = {
            "success": False,
            "error_message": "Usage: python_bridge.py <command> [args...]",
            "timestamp": datetime.now().isoformat()
        }
        print(json.dumps(error_response))
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    try:
        if command == "query":
            if len(sys.argv) < 3:
                error_response = {
                    "success": False,
                    "error_message": "Query command requires a question argument",
                    "timestamp": datetime.now().isoformat()
                }
                print(json.dumps(error_response))
                sys.exit(1)
            
            question = sys.argv[2]
            result = process_query(question)
            print(json.dumps(result, ensure_ascii=False, indent=None))
            
        elif command == "schema":
            result = get_schema()
            print(json.dumps(result, ensure_ascii=False, indent=None))
            
        elif command == "health":
            # Health check
            try:
                agent = initialize_agent()
                health_status = agent.container.health_check()
                print(json.dumps(health_status, ensure_ascii=False, indent=None))
            except Exception as e:
                health_response = {
                    "status": "unhealthy",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
                print(json.dumps(health_response, ensure_ascii=False, indent=None))
                
        else:
            error_response = {
                "success": False,
                "error_message": f"Unknown command: {command}. Available commands: query, schema, health",
                "timestamp": datetime.now().isoformat()
            }
            print(json.dumps(error_response))
            sys.exit(1)
            
    except Exception as e:
        error_response = {
            "success": False,
            "error_message": f"Bridge script error: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
        print(json.dumps(error_response))
        sys.exit(1)

if __name__ == "__main__":
    main()