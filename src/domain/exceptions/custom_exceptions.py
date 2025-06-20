"""
Custom exceptions for the TXT2SQL application.
"""


class TXT2SQLException(Exception):
    """Base exception for TXT2SQL application."""
    
    def __init__(self, message: str, error_code: str = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class LLMCommunicationError(TXT2SQLException):
    """Exception raised when LLM communication fails."""
    
    def __init__(self, message: str, error_code: str = "LLM_COMM_ERROR"):
        super().__init__(message, error_code)


class LLMTimeoutError(LLMCommunicationError):
    """Exception raised when LLM request times out."""
    
    def __init__(self, message: str, timeout_seconds: int = None):
        super().__init__(message, "LLM_TIMEOUT")
        self.timeout_seconds = timeout_seconds


class LLMUnavailableError(LLMCommunicationError):
    """Exception raised when LLM service is unavailable."""
    
    def __init__(self, message: str):
        super().__init__(message, "LLM_UNAVAILABLE")


class DatabaseConnectionError(TXT2SQLException):
    """Exception raised when database connection fails."""
    
    def __init__(self, message: str):
        super().__init__(message, "DB_CONNECTION_ERROR")


class QueryProcessingError(TXT2SQLException):
    """Exception raised during query processing."""
    
    def __init__(self, message: str):
        super().__init__(message, "QUERY_PROCESSING_ERROR")


class ValidationError(TXT2SQLException):
    """Exception raised for validation errors."""
    
    def __init__(self, message: str):
        super().__init__(message, "VALIDATION_ERROR")


class ConfigurationError(TXT2SQLException):
    """Exception raised for configuration errors."""
    
    def __init__(self, message: str):
        super().__init__(message, "CONFIG_ERROR")