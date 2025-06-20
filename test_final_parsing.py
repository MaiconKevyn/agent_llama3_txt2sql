#!/usr/bin/env python3
"""
Test the actual parsing method from the service
"""

import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

# Import needed components
from src.application.container.dependency_injection import ContainerFactory, ServiceConfig
from src.application.services.user_interface_service import InterfaceType

# Test response from actual agent
test_response = """Action: sql_db_query
Action Input: SELECT CIDADE_RESIDENCIA_PACIENTE, COUNT(*) as total FROM sus_data WHERE MORTE = 1 AND SEXO = 1 AND IDADE < 30 GROUP BY CIDADE_RESIDENCIA_PACIENTE ORDER BY total DESC LIMIT 5
Observation: [('Uruguaiana', 20), ('Ijuí', 18), ('Passo Fundo', 16), ('Porto Alegre', 15), ('Santa Maria', 14)]
Final Answer:

The top 5 cities with the most men under 30 who died are Uruguaiana, Ijuí, Passo Fundo, Porto Alegre, and Santa Maria."""

print("🔧 Testing Actual Parsing Method")
print("=" * 50)

try:
    # Create the actual service
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
    
    container = ContainerFactory.create_container_with_config(service_config)
    container.initialize()
    
    # Get the query processing service
    from src.application.services.query_processing_service import IQueryProcessingService
    query_service = container.get_service(IQueryProcessingService)
    
    # Test the parsing method directly
    print("🧪 Testing _parse_agent_results method...")
    results, row_count = query_service._parse_agent_results(test_response)
    
    print(f"\n📊 Parsing Results:")
    print(f"   • Row Count: {row_count}")
    print(f"   • Results Count: {len(results)}")
    
    for i, result in enumerate(results):
        print(f"\n   📋 Result {i+1}:")
        for key, value in result.items():
            if key == "final_answer_text":
                print(f"      {key}: {str(value)[:100]}...")
            elif key == "sql_results":
                print(f"      {key}: {value}")
            else:
                print(f"      {key}: {value}")
    
    # Check if complex query was detected
    complex_detected = any('response_type' in r and r['response_type'] == 'complex_query' for r in results)
    print(f"\n🎯 Complex Query Detection: {'✅ SUCCESS' if complex_detected else '❌ FAILED'}")
    
    if complex_detected:
        print("   🎉 The parsing correctly identified this as a complex query!")
        print("   📊 Structured data with ranks and counts was created!")
    else:
        print("   ⚠️  The parsing treated this as a simple query")
        print("   💡 Need to debug the regex patterns")

except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback
    traceback.print_exc()