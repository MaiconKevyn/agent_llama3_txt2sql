"""
Error Handling Service - Single Responsibility: Handle all error management and recovery
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import logging
import traceback
from datetime import datetime


class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories"""
    DATABASE = "database"
    LLM = "llm"
    USER_INPUT = "user_input"
    QUERY_PROCESSING = "query_processing"
    SYSTEM = "system"
    NETWORK = "network"


@dataclass
class ErrorInfo:
    """Complete error information"""
    message: str
    category: ErrorCategory
    severity: ErrorSeverity
    timestamp: datetime
    details: Optional[str] = None
    suggestion: Optional[str] = None
    error_code: Optional[str] = None
    traceback: Optional[str] = None


@dataclass
class ErrorRecoveryAction:
    """Error recovery action"""
    action_type: str
    description: str
    auto_retry: bool = False
    max_retries: int = 0


class IErrorHandlingService(ABC):
    """Interface for error handling"""
    
    @abstractmethod
    def handle_error(self, error: Exception, category: ErrorCategory) -> ErrorInfo:
        """Handle an error and return error information"""
        pass
    
    @abstractmethod
    def log_error(self, error_info: ErrorInfo) -> None:
        """Log error information"""
        pass
    
    @abstractmethod
    def get_user_friendly_message(self, error_info: ErrorInfo) -> str:
        """Get user-friendly error message"""
        pass
    
    @abstractmethod
    def suggest_recovery_action(self, error_info: ErrorInfo) -> Optional[ErrorRecoveryAction]:
        """Suggest recovery action for error"""
        pass


class ComprehensiveErrorHandlingService(IErrorHandlingService):
    """Comprehensive error handling implementation"""
    
    def __init__(self, enable_logging: bool = True):
        """
        Initialize error handling service
        
        Args:
            enable_logging: Whether to enable error logging
        """
        self._enable_logging = enable_logging
        self._error_history: List[ErrorInfo] = []
        self._setup_logging()
    
    def _setup_logging(self) -> None:
        """Setup logging configuration"""
        if self._enable_logging:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler('txt2sql_errors.log'),
                    logging.StreamHandler()
                ]
            )
            self._logger = logging.getLogger(__name__)
        else:
            self._logger = None
    
    def handle_error(self, error: Exception, category: ErrorCategory) -> ErrorInfo:
        """Handle an error and return error information"""
        severity = self._determine_severity(error, category)
        error_info = ErrorInfo(
            message=str(error),
            category=category,
            severity=severity,
            timestamp=datetime.now(),
            details=self._get_error_details(error),
            suggestion=self._get_error_suggestion(error, category),
            error_code=self._generate_error_code(error, category),
            traceback=traceback.format_exc() if severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL] else None
        )
        
        self._error_history.append(error_info)
        self.log_error(error_info)
        
        return error_info
    
    def log_error(self, error_info: ErrorInfo) -> None:
        """Log error information"""
        if not self._logger:
            return
        
        log_message = f"[{error_info.category.value.upper()}] {error_info.message}"
        
        if error_info.severity == ErrorSeverity.CRITICAL:
            self._logger.critical(log_message)
        elif error_info.severity == ErrorSeverity.HIGH:
            self._logger.error(log_message)
        elif error_info.severity == ErrorSeverity.MEDIUM:
            self._logger.warning(log_message)
        else:
            self._logger.info(log_message)
        
        if error_info.details:
            self._logger.debug(f"Details: {error_info.details}")
        
        if error_info.traceback:
            self._logger.debug(f"Traceback: {error_info.traceback}")
    
    def get_user_friendly_message(self, error_info: ErrorInfo) -> str:
        """Get user-friendly error message"""
        category_messages = {
            ErrorCategory.DATABASE: self._get_database_message(error_info),
            ErrorCategory.LLM: self._get_llm_message(error_info),
            ErrorCategory.USER_INPUT: self._get_user_input_message(error_info),
            ErrorCategory.QUERY_PROCESSING: self._get_query_processing_message(error_info),
            ErrorCategory.SYSTEM: self._get_system_message(error_info),
            ErrorCategory.NETWORK: self._get_network_message(error_info)
        }
        
        base_message = category_messages.get(error_info.category, "Ocorreu um erro inesperado.")
        
        if error_info.suggestion:
            return f"{base_message}\n\n💡 Sugestão: {error_info.suggestion}"
        
        return base_message
    
    def suggest_recovery_action(self, error_info: ErrorInfo) -> Optional[ErrorRecoveryAction]:
        """Suggest recovery action for error"""
        recovery_actions = {
            ErrorCategory.DATABASE: ErrorRecoveryAction(
                action_type="database_reconnect",
                description="Tentar reconectar ao banco de dados",
                auto_retry=True,
                max_retries=3
            ),
            ErrorCategory.LLM: ErrorRecoveryAction(
                action_type="llm_retry",
                description="Tentar novamente com o modelo LLM",
                auto_retry=True,
                max_retries=2
            ),
            ErrorCategory.NETWORK: ErrorRecoveryAction(
                action_type="network_retry",
                description="Verificar conexão de rede e tentar novamente",
                auto_retry=False,
                max_retries=0
            )
        }
        
        return recovery_actions.get(error_info.category)
    
    def _determine_severity(self, error: Exception, category: ErrorCategory) -> ErrorSeverity:
        """Determine error severity"""
        critical_errors = [
            "database not found",
            "connection failed",
            "out of memory",
            "disk full"
        ]
        
        high_errors = [
            "permission denied",
            "file not found",
            "authentication failed"
        ]
        
        error_str = str(error).lower()
        
        if any(critical in error_str for critical in critical_errors):
            return ErrorSeverity.CRITICAL
        elif any(high in error_str for high in high_errors):
            return ErrorSeverity.HIGH
        elif category in [ErrorCategory.DATABASE, ErrorCategory.LLM]:
            return ErrorSeverity.MEDIUM
        else:
            return ErrorSeverity.LOW
    
    def _get_error_details(self, error: Exception) -> str:
        """Get detailed error information"""
        return f"Tipo: {type(error).__name__}, Mensagem: {str(error)}"
    
    def _get_error_suggestion(self, error: Exception, category: ErrorCategory) -> str:
        """Get error suggestion based on category"""
        suggestions = {
            ErrorCategory.DATABASE: "Verifique se o banco de dados existe e está acessível.",
            ErrorCategory.LLM: "Verifique se o serviço Ollama está rodando e o modelo está disponível.",
            ErrorCategory.USER_INPUT: "Verifique se a entrada está no formato correto.",
            ErrorCategory.QUERY_PROCESSING: "Tente reformular sua pergunta de forma mais específica.",
            ErrorCategory.SYSTEM: "Verifique os logs do sistema para mais detalhes.",
            ErrorCategory.NETWORK: "Verifique sua conexão de rede."
        }
        
        return suggestions.get(category, "Tente novamente ou contate o suporte.")
    
    def _generate_error_code(self, error: Exception, category: ErrorCategory) -> str:
        """Generate unique error code"""
        category_codes = {
            ErrorCategory.DATABASE: "DB",
            ErrorCategory.LLM: "LLM",
            ErrorCategory.USER_INPUT: "UI",
            ErrorCategory.QUERY_PROCESSING: "QP",
            ErrorCategory.SYSTEM: "SYS",
            ErrorCategory.NETWORK: "NET"
        }
        
        category_code = category_codes.get(category, "UNK")
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        
        return f"{category_code}-{timestamp}"
    
    def _get_database_message(self, error_info: ErrorInfo) -> str:
        """Get database-specific error message"""
        if "no such table" in error_info.message.lower():
            return "❌ Tabela não encontrada no banco de dados. Verifique se o banco foi inicializado corretamente."
        elif "database is locked" in error_info.message.lower():
            return "❌ Banco de dados está bloqueado. Aguarde um momento e tente novamente."
        else:
            return "❌ Erro de conexão com o banco de dados."
    
    def _get_llm_message(self, error_info: ErrorInfo) -> str:
        """Get LLM-specific error message"""
        if "connection" in error_info.message.lower():
            return "❌ Não foi possível conectar ao serviço LLM. Verifique se o Ollama está rodando."
        elif "model not found" in error_info.message.lower():
            return "❌ Modelo LLM não encontrado. Verifique se o modelo está instalado no Ollama."
        else:
            return "❌ Erro no processamento do modelo de linguagem."
    
    def _get_user_input_message(self, error_info: ErrorInfo) -> str:
        """Get user input-specific error message"""
        return "❌ Entrada inválida. Verifique se sua pergunta está bem formulada."
    
    def _get_query_processing_message(self, error_info: ErrorInfo) -> str:
        """Get query processing-specific error message"""
        return "❌ Erro no processamento da consulta. Tente reformular sua pergunta."
    
    def _get_system_message(self, error_info: ErrorInfo) -> str:
        """Get system-specific error message"""
        return "❌ Erro interno do sistema. Verifique os logs para mais detalhes."
    
    def _get_network_message(self, error_info: ErrorInfo) -> str:
        """Get network-specific error message"""
        return "❌ Erro de rede. Verifique sua conexão com a internet."
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics"""
        if not self._error_history:
            return {"total_errors": 0}
        
        total_errors = len(self._error_history)
        errors_by_category = {}
        errors_by_severity = {}
        
        for error in self._error_history:
            category = error.category.value
            severity = error.severity.value
            
            errors_by_category[category] = errors_by_category.get(category, 0) + 1
            errors_by_severity[severity] = errors_by_severity.get(severity, 0) + 1
        
        return {
            "total_errors": total_errors,
            "errors_by_category": errors_by_category,
            "errors_by_severity": errors_by_severity,
            "most_recent_error": self._error_history[-1].timestamp.isoformat()
        }


class ErrorHandlingFactory:
    """Factory for creating error handling services"""
    
    @staticmethod
    def create_comprehensive_service(enable_logging: bool = True) -> IErrorHandlingService:
        """Create comprehensive error handling service"""
        return ComprehensiveErrorHandlingService(enable_logging)
    
    @staticmethod
    def create_service(service_type: str, **kwargs) -> IErrorHandlingService:
        """Create error handling service based on type"""
        if service_type.lower() == "comprehensive":
            return ComprehensiveErrorHandlingService(kwargs.get("enable_logging", True))
        else:
            raise ValueError(f"Unsupported error handling service type: {service_type}")