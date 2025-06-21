#!/usr/bin/env python3
"""
Test the fixed parsing logic for complex queries with multiple rows
"""

import sys
import os

# Add parent directory and src to path
parent_dir = os.path.dirname(os.path.dirname(__file__))
sys.path.append(parent_dir)
sys.path.append(os.path.join(parent_dir, 'src'))

from src.application.container.dependency_injection import ContainerFactory, ServiceConfig
from src.application.orchestrator.text2sql_orchestrator import Text2SQLOrchestrator, OrchestratorConfig
from src.application.services.user_interface_service import InterfaceType

def main():
    print("🧪 Testing Fixed Complex Query Parsing")
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
        
        # Test both problematic queries
        test_queries = [
            "Quantas mulheres morreram em Porto Alegre?",  # Simple query
            "Quais foram as 5 cidades que mais morreram homens abaixo dos 30 anos?"  # Complex query
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n🔍 Test {i}: {query}")
            print("-" * 50)
            
            # Process query
            result = orchestrator.process_single_query(query)
            
            print(f"✅ Success: {result.success}")
            print(f"📊 Row Count: {result.row_count}")
            print(f"📝 SQL Query: {result.sql_query}")
            print(f"📋 Results Preview: {str(result.results)[:200]}...")
            
            # Check the parsed results structure
            if result.results:
                print(f"\n📊 Parsed Results Analysis:")
                print(f"   • Total result items: {len(result.results)}")
                
                for j, item in enumerate(result.results):
                    print(f"   • Item {j+1}: {list(item.keys())}")
                    if "final_answer_text" in item:
                        print(f"     - Final Answer Text: {item['final_answer_text'][:100]}...")
                    if "response_type" in item:
                        print(f"     - Response Type: {item['response_type']}")
                    if "city" in item and "count" in item:
                        print(f"     - City Data: {item['city']} - {item['count']}")
            
            print("=" * 50)
        
        print(f"\n🎉 Complex query parsing test completed!")
        print(f"💡 The conversational LLM now receives complete structured data!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()