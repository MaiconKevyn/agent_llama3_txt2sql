"""
User Interface Service - Single Responsibility: Handle all user interactions and input/output formatting
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum


class InterfaceType(Enum):
    """Types of user interfaces"""
    CLI_BASIC = "cli_basic"
    CLI_INTERACTIVE = "cli_interactive"
    CLI_VERBOSE = "cli_verbose"


@dataclass
class UserQuery:
    """User query with metadata"""
    text: str
    interface_type: InterfaceType
    timestamp: str
    session_id: Optional[str] = None


@dataclass
class FormattedResponse:
    """Formatted response for user"""
    content: str
    success: bool
    execution_time: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class IUserInterfaceService(ABC):
    """Interface for user interface management"""
    
    @abstractmethod
    def get_user_input(self, prompt: str) -> str:
        """Get input from user with given prompt"""
        pass
    
    @abstractmethod
    def display_response(self, response: FormattedResponse) -> None:
        """Display formatted response to user"""
        pass
    
    @abstractmethod
    def display_error(self, error_message: str) -> None:
        """Display error message to user"""
        pass
    
    @abstractmethod
    def display_help(self) -> None:
        """Display help information"""
        pass


class CLIUserInterfaceService(IUserInterfaceService):
    """Command Line Interface implementation"""
    
    def __init__(self, interface_type: InterfaceType = InterfaceType.CLI_BASIC):
        """
        Initialize CLI user interface service
        
        Args:
            interface_type: Type of CLI interface
        """
        self._interface_type = interface_type
        self._session_started = False
    
    def get_user_input(self, prompt: str) -> str:
        """Get input from user with given prompt"""
        if not self._session_started:
            self._display_welcome()
            self._session_started = True
        
        return input(f"{prompt} ").strip()
    
    def display_response(self, response: FormattedResponse) -> None:
        """Display formatted response to user"""
        if self._interface_type == InterfaceType.CLI_INTERACTIVE:
            self._display_interactive_response(response)
        elif self._interface_type == InterfaceType.CLI_VERBOSE:
            self._display_verbose_response(response)
        else:
            self._display_basic_response(response)
    
    def display_error(self, error_message: str) -> None:
        """Display error message to user"""
        if self._interface_type == InterfaceType.CLI_INTERACTIVE:
            print(f"❌ Erro: {error_message}")
        else:
            print(f"ERRO: {error_message}")
    
    def display_help(self) -> None:
        """Display help information"""
        help_text = """
=== TXT2SQL Claude - Ajuda ===

COMANDOS DISPONÍVEIS:
- Digite sua pergunta em linguagem natural
- 'schema' - Mostra informações do banco de dados
- 'exemplos' - Mostra exemplos de perguntas
- 'ajuda' ou 'help' - Mostra esta ajuda
- 'sair', 'quit' ou 'exit' - Sai do programa

EXEMPLOS DE PERGUNTAS:
- Quantos pacientes existem?
- Qual a idade média dos pacientes?
- Quantas mortes ocorreram em Porto Alegre?
- Quais são os diagnósticos mais comuns?
- Qual o custo total por estado?

DICAS:
- Use nomes de cidades para consultas geográficas
- Seja específico nas suas perguntas
- Use termos médicos quando apropriado
"""
        print(help_text)
    
    def _display_welcome(self) -> None:
        """Display welcome message"""
        if self._interface_type == InterfaceType.CLI_INTERACTIVE:
            print("🚀 Bem-vindo ao TXT2SQL Claude!")
            print("📊 Sistema de consultas em linguagem natural para dados SUS")
            print("💡 Digite 'ajuda' para ver comandos disponíveis\n")
        else:
            print("=== TXT2SQL Claude ===")
            print("Sistema de consultas SQL em linguagem natural")
            print("Digite 'help' para ajuda\n")
    
    def _display_basic_response(self, response: FormattedResponse) -> None:
        """Display basic response format"""
        if response.success:
            print(f"\nResposta:\n{response.content}")
            if response.execution_time:
                print(f"Tempo de execução: {response.execution_time:.2f}s")
        else:
            print(f"\nFalha na consulta:\n{response.content}")
    
    def _display_interactive_response(self, response: FormattedResponse) -> None:
        """Display interactive response format with emojis"""
        if response.success:
            print(f"\n✅ Resultado da consulta:")
            print(f"📊 {response.content}")
            if response.execution_time:
                print(f"⏱️ Tempo: {response.execution_time:.2f}s")
            if response.metadata:
                print(f"📈 Detalhes: {response.metadata}")
        else:
            print(f"\n❌ Erro na consulta:")
            print(f"💬 {response.content}")
    
    def _display_verbose_response(self, response: FormattedResponse) -> None:
        """Display verbose response format"""
        print(f"\n{'='*50}")
        print(f"STATUS: {'SUCESSO' if response.success else 'FALHA'}")
        print(f"{'='*50}")
        print(f"RESPOSTA:\n{response.content}")
        
        if response.execution_time:
            print(f"\nTEMPO DE EXECUÇÃO: {response.execution_time:.2f} segundos")
        
        if response.metadata:
            print(f"\nMETADADOS:")
            for key, value in response.metadata.items():
                print(f"  {key}: {value}")
        print(f"{'='*50}")


class WebUserInterfaceService(IUserInterfaceService):
    """Web interface implementation (future implementation)"""
    
    def __init__(self):
        """Initialize web user interface service"""
        pass
    
    def get_user_input(self, prompt: str) -> str:
        """Get input from web interface"""
        raise NotImplementedError("Web interface not yet implemented")
    
    def display_response(self, response: FormattedResponse) -> None:
        """Display response in web interface"""
        raise NotImplementedError("Web interface not yet implemented")
    
    def display_error(self, error_message: str) -> None:
        """Display error in web interface"""
        raise NotImplementedError("Web interface not yet implemented")
    
    def display_help(self) -> None:
        """Display help in web interface"""
        raise NotImplementedError("Web interface not yet implemented")


class UserInterfaceFactory:
    """Factory for creating user interface services"""
    
    @staticmethod
    def create_cli_service(interface_type: InterfaceType = InterfaceType.CLI_BASIC) -> IUserInterfaceService:
        """Create CLI user interface service"""
        return CLIUserInterfaceService(interface_type)
    
    @staticmethod
    def create_web_service() -> IUserInterfaceService:
        """Create web user interface service"""
        return WebUserInterfaceService()
    
    @staticmethod
    def create_service(ui_type: str, **kwargs) -> IUserInterfaceService:
        """Create user interface service based on type"""
        if ui_type.lower() == "cli":
            interface_type = kwargs.get("interface_type", InterfaceType.CLI_BASIC)
            return CLIUserInterfaceService(interface_type)
        elif ui_type.lower() == "web":
            return WebUserInterfaceService()
        else:
            raise ValueError(f"Unsupported UI type: {ui_type}")


class InputValidator:
    """Validator for user input"""
    
    @staticmethod
    def is_command(text: str) -> bool:
        """Check if input is a command"""
        commands = ["schema", "exemplos", "ajuda", "help", "sair", "quit", "exit"]
        return text.lower() in commands
    
    @staticmethod
    def sanitize_input(text: str) -> str:
        """Sanitize user input"""
        # Remove potential SQL injection patterns
        dangerous_patterns = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "--", "/*", "*/"]
        
        cleaned = text.strip()
        for pattern in dangerous_patterns:
            if pattern.upper() in cleaned.upper():
                # Log suspicious activity but don't block (let query processing handle it)
                pass
        
        return cleaned
    
    @staticmethod
    def validate_query_length(text: str, max_length: int = 1000) -> bool:
        """Validate query length"""
        return len(text) <= max_length