"""
Query Processing Service - Single Responsibility: Handle all query processing logic
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import time
import re

from .llm_communication_service import ILLMCommunicationService, LLMResponse
from .database_connection_service import IDatabaseConnectionService
from .schema_introspection_service import ISchemaIntrospectionService
from .error_handling_service import IErrorHandlingService, ErrorCategory


@dataclass
class QueryRequest:
    """Query request with metadata"""
    user_query: str
    session_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    context: Optional[Dict[str, Any]] = None


@dataclass
class QueryResult:
    """Complete query result with metadata"""
    sql_query: str
    results: List[Dict[str, Any]]
    success: bool
    execution_time: float
    row_count: int
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class QueryValidationResult:
    """Query validation result"""
    is_valid: bool
    is_safe: bool
    warnings: List[str]
    blocked_reasons: List[str]


class IQueryProcessingService(ABC):
    """Interface for query processing"""
    
    @abstractmethod
    def process_natural_language_query(self, request: QueryRequest) -> QueryResult:
        """Process natural language query and return results"""
        pass
    
    @abstractmethod
    def validate_sql_query(self, sql_query: str) -> QueryValidationResult:
        """Validate SQL query for safety and correctness"""
        pass
    
    @abstractmethod
    def execute_sql_query(self, sql_query: str) -> QueryResult:
        """Execute SQL query and return results"""
        pass


class ComprehensiveQueryProcessingService(IQueryProcessingService):
    """Comprehensive query processing implementation using LangChain"""
    
    def __init__(
        self,
        llm_service: ILLMCommunicationService,
        db_service: IDatabaseConnectionService,
        schema_service: ISchemaIntrospectionService,
        error_service: IErrorHandlingService
    ):
        """
        Initialize query processing service
        
        Args:
            llm_service: LLM communication service
            db_service: Database connection service
            schema_service: Schema introspection service
            error_service: Error handling service
        """
        self._llm_service = llm_service
        self._db_service = db_service
        self._schema_service = schema_service
        self._error_service = error_service
        self._query_history: List[QueryResult] = []
        
        # Initialize LangChain components
        self._setup_langchain_agent()
    
    def _setup_langchain_agent(self) -> None:
        """Setup LangChain SQL agent"""
        try:
            from langchain_community.agent_toolkits.sql.base import create_sql_agent
            from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
            from langchain.agents.agent_types import AgentType
            
            # Get LLM instance (assuming Ollama service)
            if hasattr(self._llm_service, 'get_llm_instance'):
                llm_instance = self._llm_service.get_llm_instance()
            else:
                raise ValueError("LLM service does not provide LangChain-compatible instance")
            
            # Get database connection
            db_connection = self._db_service.get_connection()
            
            # Create SQL toolkit
            self._toolkit = SQLDatabaseToolkit(db=db_connection, llm=llm_instance)
            
            # Create SQL agent
            self._agent = create_sql_agent(
                llm=llm_instance,
                toolkit=self._toolkit,
                agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
                verbose=True,
                handle_parsing_errors=True
            )
            
        except Exception as e:
            error_info = self._error_service.handle_error(e, ErrorCategory.SYSTEM)
            raise RuntimeError(f"Failed to setup LangChain agent: {error_info.message}")
    
    def process_natural_language_query(self, request: QueryRequest) -> QueryResult:
        """Process natural language query using LLM and execute SQL"""
        start_time = time.time()
        
        try:
            # Get schema context
            schema_context = self._schema_service.get_schema_context()
            
            # Create enhanced prompt with schema context
            enhanced_prompt = self._create_enhanced_prompt(request.user_query, schema_context)
            
            # Process with LangChain agent
            agent_response = self._agent.run(enhanced_prompt)
            
            # Extract SQL query from response (if available)
            sql_query = self._extract_sql_from_response(agent_response)
            
            # Parse results from agent response
            results, row_count = self._parse_agent_results(agent_response)
            
            execution_time = time.time() - start_time
            
            query_result = QueryResult(
                sql_query=sql_query,
                results=results,
                success=True,
                execution_time=execution_time,
                row_count=row_count,
                metadata={
                    "agent_response": agent_response,
                    "schema_context_used": True,
                    "langchain_agent": True
                }
            )
            
            self._query_history.append(query_result)
            return query_result
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_info = self._error_service.handle_error(e, ErrorCategory.QUERY_PROCESSING)
            
            query_result = QueryResult(
                sql_query="",
                results=[],
                success=False,
                execution_time=execution_time,
                row_count=0,
                error_message=error_info.message,
                metadata={"error_code": error_info.error_code}
            )
            
            self._query_history.append(query_result)
            return query_result
    
    def validate_sql_query(self, sql_query: str) -> QueryValidationResult:
        """Validate SQL query for safety and correctness"""
        warnings = []
        blocked_reasons = []
        
        # Basic SQL injection protection
        dangerous_keywords = [
            "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE",
            "EXEC", "EXECUTE", "xp_", "sp_", "BULK", "OPENROWSET"
        ]
        
        sql_upper = sql_query.upper()
        
        for keyword in dangerous_keywords:
            if keyword in sql_upper:
                blocked_reasons.append(f"Palavra-chave perigosa detectada: {keyword}")
        
        # Check for suspicious patterns
        suspicious_patterns = [
            r"--",  # SQL comments
            r"/\*.*\*/",  # Block comments
            r";.*DROP",  # Multiple statements with DROP
            r";.*DELETE",  # Multiple statements with DELETE
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, sql_query, re.IGNORECASE):
                warnings.append(f"Padrão suspeito detectado: {pattern}")
        
        # Check for SELECT-only queries (safer)
        if not sql_upper.strip().startswith("SELECT"):
            warnings.append("Consulta não é uma operação SELECT")
        
        is_safe = len(blocked_reasons) == 0
        is_valid = is_safe and len(warnings) < 3  # Allow some warnings
        
        return QueryValidationResult(
            is_valid=is_valid,
            is_safe=is_safe,
            warnings=warnings,
            blocked_reasons=blocked_reasons
        )
    
    def execute_sql_query(self, sql_query: str) -> QueryResult:
        """Execute SQL query directly (with validation)"""
        start_time = time.time()
        
        try:
            # Validate query first
            validation = self.validate_sql_query(sql_query)
            
            if not validation.is_safe:
                raise ValueError(f"Query blocked for safety: {', '.join(validation.blocked_reasons)}")
            
            # Execute query
            conn = self._db_service.get_raw_connection()
            cursor = conn.cursor()
            cursor.execute(sql_query)
            
            # Fetch results
            results = cursor.fetchall()
            column_names = [description[0] for description in cursor.description] if cursor.description else []
            
            # Convert to list of dictionaries
            result_dicts = [dict(zip(column_names, row)) for row in results]
            
            execution_time = time.time() - start_time
            
            return QueryResult(
                sql_query=sql_query,
                results=result_dicts,
                success=True,
                execution_time=execution_time,
                row_count=len(result_dicts),
                metadata={
                    "validation_warnings": validation.warnings,
                    "direct_execution": True
                }
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_info = self._error_service.handle_error(e, ErrorCategory.DATABASE)
            
            return QueryResult(
                sql_query=sql_query,
                results=[],
                success=False,
                execution_time=execution_time,
                row_count=0,
                error_message=error_info.message
            )
    
    def _create_enhanced_prompt(self, user_query: str, schema_context) -> str:
        """Create enhanced prompt with schema context"""
        return f"""
{schema_context.formatted_context}

Pergunta do usuário: {user_query}

Por favor, gere e execute uma consulta SQL apropriada para responder esta pergunta.
Seja cuidadoso com nomes de colunas e tipos de dados.
Use as informações do contexto para gerar consultas precisas.
"""
    
    def _extract_sql_from_response(self, response: str) -> str:
        """Extract SQL query from agent response"""
        # Look for SQL query patterns in the response
        sql_patterns = [
            r"```sql\n(.*?)\n```",
            r"```\n(SELECT.*?)\n```",
            r"Action Input:\s*(SELECT.*?)(?:\n|$)",
            r"(SELECT.*?)(?:\n|$)"
        ]
        
        for pattern in sql_patterns:
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return "SQL query not found in response"
    
    def _parse_agent_results(self, response: str) -> tuple[List[Dict[str, Any]], int]:
        """Parse results from agent response"""
        # This is a simplified parser - in practice, LangChain agent
        # handles query execution and result formatting
        
        # Look for Final Answer in the response (with or without colon)
        if "Final Answer:" in response:
            # Extract the final answer part
            final_answer_start = response.find("Final Answer:")
            if final_answer_start != -1:
                final_answer_part = response[final_answer_start + len("Final Answer:"):].strip()
                
                # Try to extract the numerical result from the entire final answer section
                # Look for patterns like "is: 308" or "answer is 308"
                numbers = re.findall(r'\d+', final_answer_part)
                if numbers:
                    # Get the last/most specific number mentioned (usually the answer)
                    result_value = int(numbers[-1])
                    return [{"result": result_value}], result_value
        
        # Look for "final answer" without colon
        if "final answer" in response.lower():
            # Find the phrase and extract numbers after it
            final_answer_match = re.search(r'final answer[^0-9]*(\d+)', response, re.IGNORECASE)
            if final_answer_match:
                result_value = int(final_answer_match.group(1))
                return [{"result": result_value}], result_value
        
        # Look for patterns like "result was 308" or just a number at the start
        if "result was" in response.lower():
            # Extract number after "result was"
            match = re.search(r'result was (\d+)', response, re.IGNORECASE)
            if match:
                result_value = int(match.group(1))
                return [{"result": result_value}], result_value
        
        # Look for a number at the beginning of the response (simple case)
        first_line = response.strip().split('\n')[0].strip()
        if first_line.isdigit():
            result_value = int(first_line)
            return [{"result": result_value}], result_value
        
        # Look for structured results in Observation (fallback)
        if "Observation:" in response:
            # Extract the observation part which usually contains query results
            observation_start = response.find("Observation:")
            if observation_start != -1:
                observation_part = response[observation_start:]
                
                # Try to extract numerical results
                numbers = re.findall(r'\d+', observation_part)
                if numbers:
                    # Simple case: single number result
                    result_value = int(numbers[0])
                    return [{"result": result_value}], result_value
        
        # Fallback: return empty results
        return [], 0
    
    def get_query_statistics(self) -> Dict[str, Any]:
        """Get query processing statistics"""
        if not self._query_history:
            return {"total_queries": 0}
        
        total_queries = len(self._query_history)
        successful_queries = sum(1 for q in self._query_history if q.success)
        average_execution_time = sum(q.execution_time for q in self._query_history) / total_queries
        
        return {
            "total_queries": total_queries,
            "successful_queries": successful_queries,
            "success_rate": successful_queries / total_queries * 100,
            "average_execution_time": average_execution_time,
            "most_recent_query": self._query_history[-1].sql_query if self._query_history else None
        }


class QueryProcessingFactory:
    """Factory for creating query processing services"""
    
    @staticmethod
    def create_comprehensive_service(
        llm_service: ILLMCommunicationService,
        db_service: IDatabaseConnectionService,
        schema_service: ISchemaIntrospectionService,
        error_service: IErrorHandlingService
    ) -> IQueryProcessingService:
        """Create comprehensive query processing service"""
        return ComprehensiveQueryProcessingService(
            llm_service, db_service, schema_service, error_service
        )
    
    @staticmethod
    def create_service(
        service_type: str,
        llm_service: ILLMCommunicationService,
        db_service: IDatabaseConnectionService,
        schema_service: ISchemaIntrospectionService,
        error_service: IErrorHandlingService
    ) -> IQueryProcessingService:
        """Create query processing service based on type"""
        if service_type.lower() == "comprehensive":
            return ComprehensiveQueryProcessingService(
                llm_service, db_service, schema_service, error_service
            )
        else:
            raise ValueError(f"Unsupported query processing service type: {service_type}")