#!/usr/bin/env python3
"""
Test script for clean architecture
"""

import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

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
    
    print("✅ All imports successful")
    
    # Test configuration creation
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
    
    print("✅ Service config created")
    
    orchestrator_config = OrchestratorConfig(
        max_query_length=1000,
        enable_query_history=True,
        enable_statistics=True,
        session_timeout=3600
    )
    
    print("✅ Orchestrator config created")
    
    # Test container creation
    container = ContainerFactory.create_container_with_config(service_config)
    print("✅ Container created")
    
    # Test orchestrator creation
    orchestrator = Text2SQLOrchestrator(container, orchestrator_config)
    print("✅ Orchestrator created")
    
    # Test simple query
    result = orchestrator.process_single_query("How many patients are there?")
    print(f"✅ Query result: {result.success}, {result.error_message if not result.success else 'Success'}")
    
except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()