"""
Dependency Injection Container - Single Responsibility: Manage all service dependencies
"""
from typing import Dict, Any, Optional, Type, TypeVar
from dataclasses import dataclass

# Import all service interfaces and implementations
from ..services.database_connection_service import (
    IDatabaseConnectionService, 
    DatabaseConnectionFactory
)
from ..services.llm_communication_service import (
    ILLMCommunicationService, 
    LLMCommunicationFactory,
    LLMConfig
)
from ..services.schema_introspection_service import (
    ISchemaIntrospectionService, 
    SchemaIntrospectionFactory
)
from ..services.user_interface_service import (
    IUserInterfaceService, 
    UserInterfaceFactory,
    InterfaceType
)
from ..services.error_handling_service import (
    IErrorHandlingService, 
    ErrorHandlingFactory
)
from ..services.query_processing_service import (
    IQueryProcessingService, 
    QueryProcessingFactory
)

T = TypeVar('T')


@dataclass
class ServiceConfig:
    """Configuration for services"""
    # Database configuration
    database_type: str = "sqlite"
    database_path: str = "sus_database.db"
    
    # LLM configuration
    llm_provider: str = "ollama"
    llm_model: str = "llama3"
    llm_temperature: float = 0.0
    llm_timeout: int = 120
    llm_max_retries: int = 3
    
    # Schema configuration
    schema_type: str = "sus"
    
    # UI configuration
    ui_type: str = "cli"
    interface_type: InterfaceType = InterfaceType.CLI_INTERACTIVE
    
    # Error handling configuration
    error_handling_type: str = "comprehensive"
    enable_error_logging: bool = True
    
    # Query processing configuration
    query_processing_type: str = "comprehensive"


class DependencyContainer:
    """Dependency injection container for managing all services"""
    
    def __init__(self, config: Optional[ServiceConfig] = None):
        """
        Initialize dependency container
        
        Args:
            config: Service configuration
        """
        self._config = config or ServiceConfig()
        self._services: Dict[Type, Any] = {}
        self._singletons: Dict[Type, Any] = {}
        self._initialized = False
    
    def initialize(self) -> None:
        """Initialize all services with proper dependencies"""
        if self._initialized:
            return
        
        try:
            # Initialize services in dependency order
            self._initialize_database_service()
            self._initialize_error_handling_service()
            self._initialize_llm_service()
            self._initialize_schema_service()
            self._initialize_query_processing_service()
            self._initialize_ui_service()
            
            self._initialized = True
            
        except Exception as e:
            raise RuntimeError(f"Failed to initialize dependency container: {str(e)}")
    
    def get_service(self, service_type: Type[T]) -> T:
        """
        Get service instance by type
        
        Args:
            service_type: Service interface type
            
        Returns:
            Service instance
        """
        if not self._initialized:
            self.initialize()
        
        if service_type not in self._singletons:
            raise ValueError(f"Service {service_type.__name__} not registered")
        
        return self._singletons[service_type]
    
    def _get_registered_service(self, service_type: Type[T]) -> T:
        """
        Get service instance by type during initialization (avoid recursion)
        
        Args:
            service_type: Service interface type
            
        Returns:
            Service instance
        """
        if service_type not in self._singletons:
            raise ValueError(f"Service {service_type.__name__} not registered yet")
        
        return self._singletons[service_type]
    
    def register_service(self, service_type: Type[T], instance: T) -> None:
        """
        Register service instance
        
        Args:
            service_type: Service interface type
            instance: Service instance
        """
        self._singletons[service_type] = instance
    
    def _initialize_database_service(self) -> None:
        """Initialize database connection service"""
        db_service = DatabaseConnectionFactory.create_service(
            self._config.database_type,
            db_path=self._config.database_path
        )
        self.register_service(IDatabaseConnectionService, db_service)
    
    def _initialize_error_handling_service(self) -> None:
        """Initialize error handling service"""
        error_service = ErrorHandlingFactory.create_service(
            self._config.error_handling_type,
            enable_logging=self._config.enable_error_logging
        )
        self.register_service(IErrorHandlingService, error_service)
    
    def _initialize_llm_service(self) -> None:
        """Initialize LLM communication service"""
        llm_service = LLMCommunicationFactory.create_service(
            self._config.llm_provider,
            model_name=self._config.llm_model,
            temperature=self._config.llm_temperature,
            timeout=self._config.llm_timeout,
            max_retries=self._config.llm_max_retries
        )
        self.register_service(ILLMCommunicationService, llm_service)
    
    def _initialize_schema_service(self) -> None:
        """Initialize schema introspection service"""
        db_service = self._get_registered_service(IDatabaseConnectionService)
        schema_service = SchemaIntrospectionFactory.create_service(
            self._config.schema_type,
            db_service
        )
        self.register_service(ISchemaIntrospectionService, schema_service)
    
    def _initialize_query_processing_service(self) -> None:
        """Initialize query processing service"""
        llm_service = self._get_registered_service(ILLMCommunicationService)
        db_service = self._get_registered_service(IDatabaseConnectionService)
        schema_service = self._get_registered_service(ISchemaIntrospectionService)
        error_service = self._get_registered_service(IErrorHandlingService)
        
        query_service = QueryProcessingFactory.create_service(
            self._config.query_processing_type,
            llm_service,
            db_service,
            schema_service,
            error_service
        )
        self.register_service(IQueryProcessingService, query_service)
    
    def _initialize_ui_service(self) -> None:
        """Initialize user interface service"""
        ui_service = UserInterfaceFactory.create_service(
            self._config.ui_type,
            interface_type=self._config.interface_type
        )
        self.register_service(IUserInterfaceService, ui_service)
    
    def get_configuration(self) -> ServiceConfig:
        """Get current service configuration"""
        return self._config
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check on all services"""
        if not self._initialized:
            return {"status": "not_initialized", "services": {}}
        
        health_status = {
            "status": "healthy",
            "services": {},
            "timestamp": None
        }
        
        try:
            # Check database service
            db_service = self.get_service(IDatabaseConnectionService)
            health_status["services"]["database"] = {
                "healthy": db_service.test_connection(),
                "type": self._config.database_type
            }
            
            # Check LLM service
            llm_service = self.get_service(ILLMCommunicationService)
            health_status["services"]["llm"] = {
                "healthy": llm_service.is_available(),
                "model_info": llm_service.get_model_info()
            }
            
            # Check other services existence
            health_status["services"]["schema"] = {
                "healthy": self.get_service(ISchemaIntrospectionService) is not None
            }
            health_status["services"]["query_processing"] = {
                "healthy": self.get_service(IQueryProcessingService) is not None
            }
            health_status["services"]["ui"] = {
                "healthy": self.get_service(IUserInterfaceService) is not None
            }
            health_status["services"]["error_handling"] = {
                "healthy": self.get_service(IErrorHandlingService) is not None
            }
            
            # Determine overall health
            all_healthy = all(
                service_health.get("healthy", False) 
                for service_health in health_status["services"].values()
            )
            health_status["status"] = "healthy" if all_healthy else "degraded"
            
        except Exception as e:
            health_status["status"] = "unhealthy"
            health_status["error"] = str(e)
        
        from datetime import datetime
        health_status["timestamp"] = datetime.now().isoformat()
        
        return health_status
    
    def shutdown(self) -> None:
        """Shutdown all services gracefully"""
        try:
            # Close database connections
            if IDatabaseConnectionService in self._singletons:
                db_service = self._singletons[IDatabaseConnectionService]
                db_service.close_connection()
            
            # Clear all services
            self._singletons.clear()
            self._initialized = False
            
        except Exception as e:
            # Log error but don't raise - we're shutting down anyway
            print(f"Warning: Error during shutdown: {str(e)}")


class ContainerFactory:
    """Factory for creating dependency containers"""
    
    @staticmethod
    def create_default_container() -> DependencyContainer:
        """Create container with default configuration"""
        return DependencyContainer()
    
    @staticmethod
    def create_container_with_config(config: ServiceConfig) -> DependencyContainer:
        """Create container with custom configuration"""
        return DependencyContainer(config)
    
    @staticmethod
    def create_test_container() -> DependencyContainer:
        """Create container for testing with minimal configuration"""
        test_config = ServiceConfig(
            database_path=":memory:",  # In-memory database for testing
            llm_model="llama3",
            interface_type=InterfaceType.CLI_BASIC,
            enable_error_logging=False
        )
        return DependencyContainer(test_config)
    
    @staticmethod
    def create_production_container() -> DependencyContainer:
        """Create container for production with optimized configuration"""
        prod_config = ServiceConfig(
            database_path="sus_database.db",
            llm_model="llama3",
            llm_timeout=180,
            llm_max_retries=5,
            interface_type=InterfaceType.CLI_INTERACTIVE,
            enable_error_logging=True
        )
        return DependencyContainer(prod_config)


# Global container instance (optional - for simple usage)
_global_container: Optional[DependencyContainer] = None


def get_global_container() -> DependencyContainer:
    """Get global container instance"""
    global _global_container
    if _global_container is None:
        _global_container = ContainerFactory.create_default_container()
        _global_container.initialize()
    return _global_container


def set_global_container(container: DependencyContainer) -> None:
    """Set global container instance"""
    global _global_container
    _global_container = container