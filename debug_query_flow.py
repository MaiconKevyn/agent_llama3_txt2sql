#!/usr/bin/env python3
"""
Debug script to trace the exact data flow from SQL execution to conversational LLM
"""

import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.application.container.dependency_injection import ContainerFactory, ServiceConfig
from src.application.orchestrator.text2sql_orchestrator import Text2SQLOrchestrator, OrchestratorConfig
from src.application.services.user_interface_service import InterfaceType

def main():
    print("🔍 Debug: Query Data Flow")
    print("=" * 50)
    
    try:
        # Create configuration
        service_config = ServiceConfig(
            database_type="sqlite",
            database_path="sus_database.db",
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
            session_timeout=3600,
            enable_conversational_response=True,
            conversational_fallback=True
        )
        
        # Create dependency container and orchestrator
        container = ContainerFactory.create_container_with_config(service_config)
        orchestrator = Text2SQLOrchestrator(container, orchestrator_config)
        
        # Test the problematic query
        test_query = "Quantas mulheres morreram em Porto Alegre?"
        
        print(f"🔍 Testing Query: {test_query}")
        print("-" * 50)
        
        # Process query and debug step by step
        result = orchestrator.process_single_query(test_query)
        
        print(f"\n📊 QueryResult Debug:")
        print(f"   ✅ Success: {result.success}")
        print(f"   📝 SQL Query: {result.sql_query}")
        print(f"   📊 Results: {result.results}")
        print(f"   📈 Row Count: {result.row_count}")
        print(f"   ❌ Error: {result.error_message}")
        print(f"   ⏱️ Time: {result.execution_time:.2f}s")
        
        # Check what data is being passed to conversational LLM
        if hasattr(result, 'metadata') and result.metadata:
            print(f"\n🔧 Metadata:")
            for key, value in result.metadata.items():
                if key == 'agent_response':
                    print(f"   📜 Agent Response Preview: {str(value)[:200]}...")
                else:
                    print(f"   • {key}: {value}")
        
        # Now let's manually test the conversational service with the actual data
        print(f"\n🤖 Testing Conversational LLM with correct data:")
        print("-" * 50)
        
        # Get the conversational service directly
        conv_service = orchestrator._conversational_service
        if conv_service and conv_service.is_conversational_llm_available():
            
            # Test with the correct parsed data
            correct_results = [{"result": 138}]  # This should be what was parsed
            
            conv_response = conv_service.generate_response(
                user_query=test_query,
                sql_query="SELECT COUNT(*) FROM sus_data WHERE CIDADE_RESIDENCIA_PACIENTE = 'Porto Alegre' AND MORTE = 1 AND SEXO = 3",
                sql_results=correct_results,
                session_id="debug_session"
            )
            
            print(f"   💬 Conversational Response: {conv_response.message[:300]}...")
            print(f"   🎯 Confidence: {conv_response.confidence_score}")
            print(f"   📝 Type: {conv_response.response_type.value}")
            
        else:
            print("   ❌ Conversational LLM not available")
        
    except Exception as e:
        print(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()