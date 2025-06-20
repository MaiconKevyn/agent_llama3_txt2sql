#!/usr/bin/env python3
"""
Demo script to show the Multi-LLM Conversational System working
"""

import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.application.container.dependency_injection import ContainerFactory, ServiceConfig
from src.application.orchestrator.text2sql_orchestrator import Text2SQLOrchestrator, OrchestratorConfig
from src.application.services.user_interface_service import InterfaceType

def main():
    print("🚀 Demo: Multi-LLM Conversational System")
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
        
        # Test queries to demonstrate conversational responses
        test_queries = [
            "Quantos pacientes existem no total?",
            "Qual a média de idade dos pacientes?",
            "Quantas mortes ocorreram em Porto Alegre?",
            "Quais são os 5 diagnósticos mais comuns?"
        ]
        
        print("\n🧪 Testing Multi-LLM Conversational Responses:")
        print("-" * 50)
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n{i}. 🔍 Query: {query}")
            print("   Processing...")
            
            result = orchestrator.process_single_query(query)
            
            if result.success:
                print(f"   ✅ Success: {result.row_count} results")
                print(f"   ⏱️ Time: {result.execution_time:.1f}s")
                print(f"   💬 SQL: {result.sql_query[:80]}...")
            else:
                print(f"   ❌ Error: {result.error_message}")
                
            print("   " + "-" * 45)
        
        print(f"\n🎉 Demo completed!")
        print(f"🔧 Conversational LLM: llama3.2:latest")
        print(f"🔧 SQL Generation LLM: llama3:latest")
        print(f"📊 System is using DUAL LLM architecture for better responses!")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        print("\n💡 Make sure:")
        print("• Ollama is running: ollama serve")
        print("• Models are available: ollama pull llama3 && ollama pull llama3.2")
        print("• Database exists: python database_setup.py")

if __name__ == "__main__":
    main()