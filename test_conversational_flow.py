#!/usr/bin/env python3
"""
Test the complete conversational flow with fixed parsing
"""

import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.application.container.dependency_injection import ContainerFactory, ServiceConfig
from src.application.orchestrator.text2sql_orchestrator import Text2SQLOrchestrator, OrchestratorConfig
from src.application.services.user_interface_service import InterfaceType

def main():
    print("🤖 Testing Complete Conversational Flow")
    print("=" * 50)
    
    try:
        # Create configuration with conversational features enabled
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
            enable_conversational_response=True,  # ✅ Multi-LLM enabled
            conversational_fallback=True          # ✅ Fallback enabled
        )
        
        # Create dependency container and orchestrator
        container = ContainerFactory.create_container_with_config(service_config)
        orchestrator = Text2SQLOrchestrator(container, orchestrator_config)
        
        # Test the problematic complex query
        query = "Quais foram as 5 cidades que mais morreram homens abaixo dos 30 anos?"
        
        print(f"🔍 Query: {query}")
        print("-" * 50)
        
        # Process the query
        result = orchestrator.process_single_query(query)
        
        print(f"\n📊 QueryResult:")
        print(f"   ✅ Success: {result.success}")
        print(f"   📈 Row Count: {result.row_count}")
        print(f"   ⏱️ Execution Time: {result.execution_time:.2f}s")
        print(f"   📝 SQL Query: {result.sql_query}")
        
        # Show the raw results structure
        print(f"\n📋 Raw Results Structure:")
        for i, result_item in enumerate(result.results):
            print(f"   Item {i+1}: {list(result_item.keys())}")
            if "city" in result_item and "count" in result_item:
                print(f"      City: {result_item['city']}, Count: {result_item['count']}")
            elif "final_answer_text" in result_item:
                print(f"      Final Answer: {result_item['final_answer_text'][:80]}...")
        
        # Format and display the conversational response
        print(f"\n💬 Testing Conversational Response:")
        print("-" * 50)
        
        # Get the conversational service directly to test
        conv_service = orchestrator._conversational_service
        if conv_service and conv_service.is_conversational_llm_available():
            try:
                conv_response = conv_service.generate_response(
                    user_query=query,
                    sql_query=result.sql_query,
                    sql_results=result.results,  # This now contains structured data!
                    session_id="test_session"
                )
                
                print(f"   🎯 Response Type: {conv_response.response_type.value}")
                print(f"   🎯 Confidence: {conv_response.confidence_score}")
                print(f"   💬 Message:")
                print(f"      {conv_response.message}")
                
                # Check if the response mentions the specific cities and counts
                if "Uruguaiana" in conv_response.message and "20" in conv_response.message:
                    print(f"\n   ✅ SUCCESS: Response includes specific cities and counts!")
                else:
                    print(f"\n   ⚠️  Response is generic - may need prompt tuning")
                    
            except Exception as conv_error:
                print(f"   ❌ Conversational LLM error: {conv_error}")
        else:
            print("   ❌ Conversational LLM not available")
        
        print(f"\n🎉 Test completed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()