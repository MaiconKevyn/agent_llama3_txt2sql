#!/usr/bin/env python3
"""
Flask Web Interface for TXT2SQL Agent - Clean Architecture
Simple web interface using Flask
"""

import sys
import os
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime

# Add parent directory and src to path
parent_dir = os.path.dirname(os.path.dirname(__file__))
sys.path.append(parent_dir)
sys.path.append(os.path.join(parent_dir, 'src'))

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
agent = None

def initialize_agent():
    """Initialize the clean architecture agent"""
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

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TXT2SQL - Flask Interface</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; margin-bottom: 30px; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .chat-container { background: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); overflow: hidden; }
        .chat-messages { height: 400px; overflow-y: auto; padding: 20px; border-bottom: 1px solid #eee; }
        .message { margin-bottom: 15px; padding: 10px; border-radius: 8px; }
        .user-message { background: #007bff; color: white; margin-left: 20%; }
        .assistant-message { background: #f8f9fa; color: #333; margin-right: 20%; border-left: 4px solid #28a745; }
        .error-message { background: #f8d7da; color: #721c24; border-left: 4px solid #dc3545; }
        .chat-input { display: flex; padding: 20px; gap: 10px; }
        .chat-input input { flex: 1; padding: 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 16px; }
        .chat-input button { padding: 12px 24px; background: #007bff; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; }
        .chat-input button:hover { background: #0056b3; }
        .examples { background: white; margin-top: 20px; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .example-btn { display: inline-block; margin: 5px; padding: 8px 16px; background: #6c757d; color: white; border: none; border-radius: 20px; cursor: pointer; font-size: 14px; }
        .example-btn:hover { background: #545b62; }
        .metadata { font-size: 12px; color: #666; margin-top: 10px; padding: 8px; background: #f8f9fa; border-radius: 4px; }
        .loading { text-align: center; padding: 20px; color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🗃️ TXT2SQL Flask Interface</h1>
            <p>Ask questions about the healthcare database in natural language!</p>
        </div>
        
        <div class="chat-container">
            <div class="chat-messages" id="messages">
                <div class="assistant-message">
                    <strong>Assistant:</strong> Hello! I'm ready to help you query the SUS healthcare database. Ask me anything!
                </div>
            </div>
            
            <div class="chat-input">
                <input type="text" id="questionInput" placeholder="Type your question here..." onkeypress="handleKeyPress(event)">
                <button onclick="sendQuery()">Send</button>
                <button onclick="getSchema()">Schema</button>
            </div>
        </div>
        
        <div class="examples">
            <h3>💡 Example Questions:</h3>
            <button class="example-btn" onclick="askExample('How many patients are there?')">How many patients?</button>
            <button class="example-btn" onclick="askExample('What is the average age of patients?')">Average age?</button>
            <button class="example-btn" onclick="askExample('How many deaths occurred?')">Total deaths?</button>
            <button class="example-btn" onclick="askExample('Show patients from Porto Alegre')">Patients from Porto Alegre</button>
            <button class="example-btn" onclick="askExample('What are the most common diagnoses?')">Common diagnoses</button>
        </div>
    </div>

    <script>
        function addMessage(content, type = 'assistant', metadata = null) {
            const messages = document.getElementById('messages');
            const messageDiv = document.createElement('div');
            
            let className = type === 'user' ? 'user-message' : 
                           type === 'error' ? 'error-message' : 'assistant-message';
            
            messageDiv.className = `message ${className}`;
            
            let html = `<strong>${type === 'user' ? 'You' : 'Assistant'}:</strong> ${content}`;
            
            if (metadata && metadata.execution_time) {
                html += `<div class="metadata">
                    <strong>Tempo:</strong> ${metadata.execution_time.toFixed(2)}s
                </div>`;
            }
            
            messageDiv.innerHTML = html;
            messages.appendChild(messageDiv);
            messages.scrollTop = messages.scrollHeight;
        }
        
        function showLoading() {
            const messages = document.getElementById('messages');
            const loadingDiv = document.createElement('div');
            loadingDiv.className = 'loading';
            loadingDiv.id = 'loading';
            loadingDiv.innerHTML = '🔄 Processing your question...';
            messages.appendChild(loadingDiv);
            messages.scrollTop = messages.scrollHeight;
        }
        
        function hideLoading() {
            const loading = document.getElementById('loading');
            if (loading) loading.remove();
        }
        
        async function sendQuery() {
            const input = document.getElementById('questionInput');
            const question = input.value.trim();
            
            if (!question) return;
            
            addMessage(question, 'user');
            input.value = '';
            showLoading();
            
            try {
                const response = await fetch('/api/query', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question: question })
                });
                
                const data = await response.json();
                hideLoading();
                
                if (data.success) {
                    // Display conversational response from LLM
                    addMessage(data.response, 'assistant', {
                        execution_time: data.execution_time
                    });
                } else {
                    addMessage(`Error: ${data.error_message}`, 'error');
                }
            } catch (error) {
                hideLoading();
                addMessage(`Network error: ${error.message}`, 'error');
            }
        }
        
        async function getSchema() {
            showLoading();
            
            try {
                const response = await fetch('/api/schema');
                const data = await response.json();
                hideLoading();
                
                addMessage(`<strong>Database Schema:</strong><br><pre style="white-space: pre-wrap; font-family: monospace; background: #f8f9fa; padding: 10px; border-radius: 4px; margin-top: 10px;">${data.schema}</pre>`, 'assistant');
            } catch (error) {
                hideLoading();
                addMessage(`Error loading schema: ${error.message}`, 'error');
            }
        }
        
        function askExample(question) {
            document.getElementById('questionInput').value = question;
            sendQuery();
        }
        
        function handleKeyPress(event) {
            if (event.key === 'Enter') {
                sendQuery();
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    """Main page"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/query', methods=['POST'])
def query_api():
    """Process query via API"""
    global agent
    
    if not agent:
        return jsonify({"success": False, "error_message": "Agent not initialized"}), 500
    
    data = request.get_json()
    question = data.get('question', '')
    
    if not question:
        return jsonify({"success": False, "error_message": "Question is required"}), 400
    
    try:
        # Use conversational response instead of raw SQL results
        conversational_result = agent.process_conversational_query(question)
        
        return jsonify(conversational_result)
    except Exception as e:
        return jsonify({
            "success": False,
            "question": question,
            "error_message": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/api/schema', methods=['GET'])
def schema_api():
    """Get database schema"""
    global agent
    
    if not agent:
        return jsonify({"error": "Agent not initialized"}), 500
    
    try:
        schema_service = agent.container.get_schema_introspection_service()
        schema_info = schema_service.get_schema_information()
        
        return jsonify({
            "schema": schema_info,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("🚀 Starting TXT2SQL Flask Server...")
    print("📍 Make sure Ollama is running with llama3 model")
    print("🌐 Interface will be available at http://localhost:5000")
    print("⏹️  Press Ctrl+C to stop")
    
    try:
        print("Initializing agent...")
        agent = initialize_agent()
        print("✅ Agent initialized successfully!")
        
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=True
        )
    except Exception as e:
        print(f"❌ Failed to start: {str(e)}")