#!/usr/bin/env python3
"""
FastAPI Server for TXT2SQL Agent - Clean Architecture
Provides REST API endpoints for the text-to-SQL functionality
"""

import sys
import os
from typing import Dict, Any, Optional
from datetime import datetime
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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

# Global agent instance
agent: Optional[Text2SQLOrchestrator] = None

# FastAPI app
app = FastAPI(
    title="TXT2SQL API",
    description="Clean Architecture Text-to-SQL API for SUS Healthcare Data",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware for web frontend
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Request/Response models
class QueryRequest(BaseModel):
    question: str
    model: str = "llama3"

class QueryResponse(BaseModel):
    success: bool
    question: str
    sql_query: Optional[str] = None
    results: Optional[Any] = None
    row_count: Optional[int] = None
    execution_time: Optional[float] = None
    error_message: Optional[str] = None
    timestamp: str

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    services: Dict[str, Any]

class SchemaResponse(BaseModel):
    schema: str
    timestamp: str

def initialize_agent(model_name: str = None) -> Text2SQLOrchestrator:
    """Initialize the clean architecture agent"""
    if model_name is None:
        model_name = os.getenv("LLM_MODEL", "llama3")
    
    service_config = ServiceConfig(
        database_type=os.getenv("DATABASE_TYPE", "sqlite"),
        database_path=os.getenv("DATABASE_PATH", "sus_database.db"),
        llm_provider=os.getenv("LLM_PROVIDER", "ollama"),
        llm_model=model_name,
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
        llm_timeout=int(os.getenv("LLM_TIMEOUT", "120")),
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "3")),
        schema_type=os.getenv("SCHEMA_TYPE", "sus"),
        ui_type=os.getenv("UI_TYPE", "cli"),
        interface_type=InterfaceType.CLI_BASIC,
        error_handling_type=os.getenv("ERROR_HANDLING_TYPE", "comprehensive"),
        enable_error_logging=os.getenv("ENABLE_ERROR_LOGGING", "true").lower() == "true",
        query_processing_type=os.getenv("QUERY_PROCESSING_TYPE", "comprehensive")
    )
    
    orchestrator_config = OrchestratorConfig(
        max_query_length=int(os.getenv("MAX_QUERY_LENGTH", "1000")),
        enable_query_history=os.getenv("ENABLE_QUERY_HISTORY", "true").lower() == "true",
        enable_statistics=os.getenv("ENABLE_STATISTICS", "true").lower() == "true",
        session_timeout=int(os.getenv("SESSION_TIMEOUT", "3600"))
    )
    
    container = ContainerFactory.create_container_with_config(service_config)
    return Text2SQLOrchestrator(container, orchestrator_config)

@app.on_event("startup")
async def startup_event():
    """Initialize agent on startup"""
    global agent
    try:
        agent = initialize_agent()
        print("✅ TXT2SQL Agent initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize agent: {str(e)}")
        raise

@app.get("/", response_class=HTMLResponse)
async def root():
    """Simple HTML interface"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>TXT2SQL API</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 800px; margin: 0 auto; }
            .query-box { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ccc; border-radius: 4px; }
            .button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
            .button:hover { background: #0056b3; }
            .result { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 4px; background: #f9f9f9; }
            .error { border-color: #dc3545; background: #f8d7da; }
            .success { border-color: #28a745; background: #d4edda; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🗃️ TXT2SQL API Interface</h1>
            <p>Ask questions about the healthcare database in natural language!</p>
            
            <div>
                <input type="text" id="question" class="query-box" placeholder="Enter your question here..." />
                <button class="button" onclick="queryAPI()">Send Query</button>
                <button class="button" onclick="getSchema()">Show Schema</button>
            </div>
            
            <div id="result"></div>
            
            <h3>Example Questions:</h3>
            <ul>
                <li><a href="#" onclick="askExample('How many patients are there?')">How many patients are there?</a></li>
                <li><a href="#" onclick="askExample('What is the average age of patients?')">What is the average age of patients?</a></li>
                <li><a href="#" onclick="askExample('How many deaths occurred?')">How many deaths occurred?</a></li>
                <li><a href="#" onclick="askExample('Show patients from Porto Alegre')">Show patients from Porto Alegre</a></li>
            </ul>
            
            <h3>API Documentation:</h3>
            <p><a href="/docs" target="_blank">Swagger UI</a> | <a href="/redoc" target="_blank">ReDoc</a></p>
        </div>
        
        <script>
            async function queryAPI() {
                const question = document.getElementById('question').value;
                if (!question.trim()) return;
                
                const resultDiv = document.getElementById('result');
                resultDiv.innerHTML = '<div class="result">Processing...</div>';
                
                try {
                    const response = await fetch('/query', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ question: question })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        resultDiv.innerHTML = `
                            <div class="result success">
                                <h4>✅ Success</h4>
                                <p><strong>Question:</strong> ${data.question}</p>
                                <p><strong>Result:</strong> ${JSON.stringify(data.results)}</p>
                                <p><strong>Rows:</strong> ${data.row_count}</p>
                                <p><strong>Time:</strong> ${data.execution_time?.toFixed(2)}s</p>
                                <details>
                                    <summary>SQL Query</summary>
                                    <pre>${data.sql_query}</pre>
                                </details>
                            </div>
                        `;
                    } else {
                        resultDiv.innerHTML = `
                            <div class="result error">
                                <h4>❌ Error</h4>
                                <p><strong>Question:</strong> ${data.question}</p>
                                <p><strong>Error:</strong> ${data.error_message}</p>
                            </div>
                        `;
                    }
                } catch (error) {
                    resultDiv.innerHTML = `<div class="result error">Network error: ${error.message}</div>`;
                }
            }
            
            async function getSchema() {
                const resultDiv = document.getElementById('result');
                resultDiv.innerHTML = '<div class="result">Loading schema...</div>';
                
                try {
                    const response = await fetch('/schema');
                    const data = await response.json();
                    
                    resultDiv.innerHTML = `
                        <div class="result">
                            <h4>📊 Database Schema</h4>
                            <pre>${data.schema}</pre>
                        </div>
                    `;
                } catch (error) {
                    resultDiv.innerHTML = `<div class="result error">Error loading schema: ${error.message}</div>`;
                }
            }
            
            function askExample(question) {
                document.getElementById('question').value = question;
                queryAPI();
            }
            
            // Enter key support
            document.getElementById('question').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') queryAPI();
            });
        </script>
    </body>
    </html>
    """

@app.post("/query", response_model=QueryResponse)
async def query_database(request: QueryRequest):
    """Process natural language query"""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    try:
        result = agent.process_single_query(request.question)
        
        return QueryResponse(
            success=result.success,
            question=request.question,
            sql_query=result.sql_query if result.success else None,
            results=result.results if result.success else None,
            row_count=result.row_count if result.success else None,
            execution_time=result.execution_time if result.success else None,
            error_message=result.error_message if not result.success else None,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        return QueryResponse(
            success=False,
            question=request.question,
            error_message=f"Internal server error: {str(e)}",
            timestamp=datetime.now().isoformat()
        )

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    try:
        if not agent:
            return HealthResponse(
                status="unhealthy",
                timestamp=datetime.now().isoformat(),
                services={"agent": "not_initialized"}
            )
        
        health_status = agent.container.health_check()
        return HealthResponse(
            status=health_status["status"],
            timestamp=datetime.now().isoformat(),
            services=health_status["services"]
        )
    except Exception as e:
        return HealthResponse(
            status="error",
            timestamp=datetime.now().isoformat(),
            services={"error": str(e)}
        )

@app.get("/schema", response_model=SchemaResponse)
async def get_schema():
    """Get database schema information"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        schema_service = agent.container.get_schema_introspection_service()
        schema_info = schema_service.get_schema_information()
        
        return SchemaResponse(
            schema=schema_info,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schema error: {str(e)}")

@app.get("/models")
async def get_available_models():
    """Get available LLM models"""
    return {
        "models": ["llama3", "mistral"],
        "default": "llama3",
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    print("🚀 Starting TXT2SQL API Server...")
    print("📍 Make sure Ollama is running with llama3 or mistral model")
    print("🌐 API will be available at http://localhost:8000")
    print("📚 Documentation at http://localhost:8000/docs")
    print("⏹️  Press Ctrl+C to stop")
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    
    print(f"🌐 API will be available at http://{host}:{port}")
    print(f"📚 Documentation at http://{host}:{port}/docs")
    
    uvicorn.run(
        "api_server:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )