#!/usr/bin/env python3
"""
Simple API test for TXT2SQL
"""

import sys
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.application.container.dependency_injection import (
    ContainerFactory, 
    ServiceConfig
)
from src.application.orchestrator.text2sql_orchestrator import (
    Text2SQLOrchestrator,
    OrchestratorConfig
)
from src.application.services.user_interface_service import InterfaceType

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
agent = None

def initialize_agent():
    """Initialize the clean architecture agent"""
    print("🔧 Initializing agent...")
    
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
        session_timeout=3600
    )
    
    container = ContainerFactory.create_container_with_config(service_config)
    return Text2SQLOrchestrator(container, orchestrator_config)

@app.route('/')
def home():
    return {"message": "TXT2SQL Simple API", "status": "running"}

@app.route('/health')
def health():
    global agent
    if not agent:
        return {"status": "error", "message": "Agent not initialized"}, 500
    
    try:
        health_status = agent.container.health_check()
        return {
            "status": health_status["status"],
            "timestamp": datetime.now().isoformat(),
            "services": health_status["services"]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/query', methods=['POST'])
def query():
    global agent
    if not agent:
        return {"success": False, "error_message": "Agent not initialized"}, 500
    
    data = request.get_json()
    question = data.get('question', '')
    
    if not question:
        return {"success": False, "error_message": "Question is required"}, 400
    
    try:
        # Use conversational response instead of raw SQL results
        conversational_result = agent.process_conversational_query(question)
        
        return conversational_result
    except Exception as e:
        return {
            "success": False,
            "question": question,
            "error_message": str(e),
            "timestamp": datetime.now().isoformat()
        }, 500

@app.route('/schema')
def schema():
    global agent
    if not agent:
        return {"error": "Agent not initialized"}, 500
    
    try:
        schema_service = agent.container.get_schema_introspection_service()
        schema_info = schema_service.get_schema_information()
        
        return {
            "schema": schema_info,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}, 500

if __name__ == "__main__":
    print("🚀 Starting Simple TXT2SQL API...")
    print("📍 Make sure Ollama is running with llama3 model")
    
    try:
        agent = initialize_agent()
        print("✅ Agent initialized successfully!")
        print("🌐 API will be available at http://localhost:5002")
        
        app.run(host="0.0.0.0", port=5002, debug=False)
    except Exception as e:
        print(f"❌ Failed to start: {str(e)}")
        import traceback
        traceback.print_exc()