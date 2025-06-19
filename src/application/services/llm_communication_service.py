"""
LLM Communication Service - Single Responsibility: Handle all LLM interactions
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from langchain_community.llms import Ollama
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Response from LLM service"""
    content: str
    success: bool
    error_message: Optional[str] = None
    execution_time: Optional[float] = None
    tokens_used: Optional[int] = None


@dataclass
class LLMConfig:
    """Configuration for LLM service"""
    model_name: str = "llama3"
    temperature: float = 0.0
    timeout: int = 120
    max_retries: int = 3


class ILLMCommunicationService(ABC):
    """Interface for LLM communication"""
    
    @abstractmethod
    def send_prompt(self, prompt: str) -> LLMResponse:
        """Send prompt to LLM and get response"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if LLM service is available"""
        pass
    
    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model"""
        pass


class OllamaLLMCommunicationService(ILLMCommunicationService):
    """Ollama implementation of LLM communication service"""
    
    def __init__(self, config: LLMConfig):
        """
        Initialize Ollama LLM communication service
        
        Args:
            config: LLM configuration
        """
        self._config = config
        self._llm: Optional[Ollama] = None
        self._initialize_llm()
    
    def _initialize_llm(self) -> None:
        """Initialize the Ollama LLM instance"""
        try:
            self._llm = Ollama(
                model=self._config.model_name,
                temperature=self._config.temperature
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Ollama LLM: {str(e)}")
    
    def send_prompt(self, prompt: str) -> LLMResponse:
        """Send prompt to Ollama LLM and get response"""
        import time
        
        if not self._llm:
            return LLMResponse(
                content="",
                success=False,
                error_message="LLM not initialized"
            )
        
        start_time = time.time()
        
        for attempt in range(self._config.max_retries):
            try:
                response = self._llm.invoke(prompt)
                execution_time = time.time() - start_time
                
                return LLMResponse(
                    content=response,
                    success=True,
                    execution_time=execution_time
                )
                
            except Exception as e:
                if attempt == self._config.max_retries - 1:
                    execution_time = time.time() - start_time
                    return LLMResponse(
                        content="",
                        success=False,
                        error_message=f"Failed after {self._config.max_retries} attempts: {str(e)}",
                        execution_time=execution_time
                    )
                # Wait before retry
                time.sleep(1)
        
        return LLMResponse(
            content="",
            success=False,
            error_message="Unexpected error in retry loop"
        )
    
    def is_available(self) -> bool:
        """Check if Ollama LLM service is available"""
        try:
            if not self._llm:
                return False
            
            # Test with a simple prompt
            test_response = self._llm.invoke("Test")
            return isinstance(test_response, str)
            
        except Exception:
            return False
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current Ollama model"""
        return {
            "provider": "Ollama",
            "model_name": self._config.model_name,
            "temperature": self._config.temperature,
            "timeout": self._config.timeout,
            "max_retries": self._config.max_retries,
            "available": self.is_available()
        }
    
    def get_llm_instance(self) -> Optional[Ollama]:
        """Get the underlying Ollama LLM instance (for LangChain compatibility)"""
        return self._llm


class LLMCommunicationFactory:
    """Factory for creating LLM communication services"""
    
    @staticmethod
    def create_ollama_service(
        model_name: str = "llama3",
        temperature: float = 0.0,
        timeout: int = 120,
        max_retries: int = 3
    ) -> ILLMCommunicationService:
        """Create Ollama LLM communication service"""
        config = LLMConfig(
            model_name=model_name,
            temperature=temperature,
            timeout=timeout,
            max_retries=max_retries
        )
        return OllamaLLMCommunicationService(config)
    
    @staticmethod
    def create_service(
        provider: str,
        **kwargs
    ) -> ILLMCommunicationService:
        """Create LLM communication service based on provider"""
        if provider.lower() == "ollama":
            return LLMCommunicationFactory.create_ollama_service(**kwargs)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")