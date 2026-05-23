"""
Enhanced List Tables Tool
Tool customizada para listar tabelas com descrições detalhadas e orientações de uso
"""

from typing import Any

from langchain_community.utilities import SQLDatabase
from langchain_core.tools import BaseTool

# Import table descriptions configuration
from ...application.config.table_descriptions import (
    SELECTION_GUIDES,
    TABLE_DESCRIPTIONS,
    TOOL_CONFIGURATION,
)


class EnhancedListTablesTool(BaseTool):
    """
    Enhanced version of sql_db_list_tables with detailed descriptions

    Provides comprehensive table information including:
    - Detailed descriptions and purposes
    - Use case examples and guidance
    - Value mappings and critical notes
    - Sample queries and selection guidance
    - Smart selection rules for LLM
    """

    name: str = "sql_db_list_tables"
    description: str = """Input is an empty string, output is a comprehensive list of available tables 
    with detailed descriptions, purposes, use cases, and intelligent selection guidance. This enhanced 
    version helps choose the correct table by providing context about what each table contains and 
    when to use it."""

    # Store database and configuration as class attributes
    _db: SQLDatabase | None = None
    _include_samples: bool = True
    _include_mappings: bool = True
    _include_selection_guide: bool = True
    _max_use_cases: int = 3
    _max_samples: int = 2
    _max_sample_length: int = 300

    def __init__(self, db: SQLDatabase, **kwargs):
        """
        Initialize the enhanced list tables tool

        Args:
            db: SQLDatabase instance for database access
            **kwargs: Additional configuration options
        """
        super().__init__(**kwargs)
        # Use class attributes to store configuration
        self.__class__._db = db
        self.__class__._include_samples = TOOL_CONFIGURATION.get("include_samples", True)
        self.__class__._include_mappings = TOOL_CONFIGURATION.get("include_mappings", True)
        self.__class__._include_selection_guide = TOOL_CONFIGURATION.get(
            "include_selection_guide", True
        )
        self.__class__._max_use_cases = TOOL_CONFIGURATION.get("max_use_cases_shown", 3)
        self.__class__._max_samples = TOOL_CONFIGURATION.get("max_sample_queries_shown", 2)
        self.__class__._max_sample_length = TOOL_CONFIGURATION.get("max_sample_length", 100)

    @property
    def db(self) -> SQLDatabase:
        """Get database instance"""
        return self.__class__._db

    @property
    def include_samples(self) -> bool:
        """Get include_samples configuration"""
        return self.__class__._include_samples

    @property
    def include_mappings(self) -> bool:
        """Get include_mappings configuration"""
        return self.__class__._include_mappings

    @property
    def include_selection_guide(self) -> bool:
        """Get include_selection_guide configuration"""
        return self.__class__._include_selection_guide

    @property
    def max_use_cases(self) -> int:
        """Get max_use_cases configuration"""
        return self.__class__._max_use_cases

    @property
    def max_samples(self) -> int:
        """Get max_samples configuration"""
        return self.__class__._max_samples

    @property
    def max_sample_length(self) -> int:
        """Get max_sample_length configuration"""
        return self.__class__._max_sample_length

    def _run(self, tool_input: str = "") -> str:
        """
        Execute the enhanced list tables tool

        Args:
            tool_input: Empty string (tool doesn't need input)

        Returns:
            Comprehensive formatted string with table descriptions and guidance
        """
        try:
            # Validate database is available
            if not self.db:
                return " Database não disponível para enhanced list tables tool."

            # Get available tables from database
            table_names = self.db.get_usable_table_names()

            if not table_names:
                return " Nenhuma tabela encontrada no banco de dados."

            # Build CONCISE output (performance optimized)
            if TOOL_CONFIGURATION.get("concise_mode", False):
                result_parts = []  # No header in concise mode
            else:
                result_parts = [" TABELAS COM DESCRIÇÕES:"]

            # Add detailed information for each table
            for table_name in sorted(table_names):
                table_section = self._format_table_information(table_name)
                result_parts.append(table_section)

            # Add intelligent selection guidance
            if self.include_selection_guide:
                selection_section = self._generate_selection_guidance()
                result_parts.append(selection_section)

            return "\n".join(result_parts)

        except Exception as e:
            # Fallback to basic list if enhanced version fails
            return self._generate_fallback_response(str(e))

    async def _arun(self, tool_input: str = "") -> str:
        """Async version of _run"""
        return self._run(tool_input)

    def _format_table_information(self, table_name: str) -> str:
        """
        Format CONCISE information for a single table (performance optimized)

        Args:
            table_name: Name of the table to format

        Returns:
            Formatted string with essential table information only
        """
        # Get table description or create default
        table_info = TABLE_DESCRIPTIONS.get(table_name, self._get_default_description(table_name))

        # CONCISE MODE: Only essential information
        if TOOL_CONFIGURATION.get("concise_mode", False):
            # Ultra-concise format: 1-2 lines per table
            mappings = table_info.get("value_mappings", {})
            mapping_text = ", ".join([f"{k}={v}" for k, v in mappings.items()]) if mappings else ""

            return f"{table_name}: {table_info['description']} | {mapping_text}"

        # Standard format (if concise_mode is False)
        sections = [f"\n{table_name}:"]
        sections.append(f"  {table_info['title']}")
        sections.append(f"   {table_info['description']}")

        # Only show critical mappings in standard mode
        if self.include_mappings:
            mappings = table_info.get("value_mappings", {})
            if mappings:
                mapping_items = [f"{k}={v}" for k, v in mappings.items()]
                sections.append(f"    {', '.join(mapping_items)}")

        return "\n".join(sections)

    def _get_table_sample(self, table_name: str) -> str:
        """
        Get a sample of data from the table

        Args:
            table_name: Name of the table to sample

        Returns:
            String representation of sample data
        """
        try:
            # Get a small sample to show data structure
            sample_query = f"SELECT * FROM {table_name} LIMIT 1"
            sample_result = self.db.run(sample_query)

            # Format sample for display
            if sample_result and len(str(sample_result)) > 0:
                sample_str = str(sample_result)
                # Truncate if too long
                if len(sample_str) > self.max_sample_length:
                    sample_str = sample_str[: self.max_sample_length] + "..."
                return sample_str
            else:
                return "Dados não disponíveis"

        except Exception as e:
            return f"Erro ao obter amostra: {str(e)[:50]}..."

    def _get_default_description(self, table_name: str) -> dict[str, Any]:
        """
        Generate default description for unknown tables

        Args:
            table_name: Name of the table

        Returns:
            Default table information dictionary
        """
        return {
            "title": f" Tabela: {table_name}",
            "description": f"Tabela de dados {table_name}",
            "purpose": "Análise baseada no schema e conteúdo da tabela",
            "use_cases": [
                "Consultas gerais aos dados",
                "Análise exploratória de dados",
                "Investigação do conteúdo da tabela",
            ],
            "key_columns": ["Analisar schema para identificar colunas"],
            "value_mappings": {},
            "sample_queries": [f"SELECT * FROM {table_name} LIMIT 10", f"DESCRIBE {table_name}"],
            "critical_notes": ["Use sql_db_schema para obter mais informações sobre esta tabela"],
        }

    def _generate_selection_guidance(self) -> str:
        """
        Generate CONCISE selection guidance for the LLM (performance optimized)

        Returns:
            Formatted guidance section (ultra-concise)
        """
        # Use concise guide only (1-2 lines total)
        return SELECTION_GUIDES.get("concise_guide", "")

    def _generate_fallback_response(self, error_msg: str) -> str:
        """
        Generate fallback response if enhanced version fails

        Args:
            error_msg: Error message from the failure

        Returns:
            Basic fallback response
        """
        try:
            # Try to get basic table list
            table_names = self.db.get_usable_table_names()
            basic_list = ", ".join(table_names)

            return f""" Enhanced descriptions failed: {error_msg[:100]}
            
            TABELAS DISPONÍVEIS:
            {basic_list}

            Use sql_db_schema para obter mais informações sobre cada tabela."""

        except Exception:
            return f" Erro ao listar tabelas: {error_msg[:100]}..."


# Factory function for easy instantiation
def create_enhanced_list_tables_tool(db: SQLDatabase) -> EnhancedListTablesTool:
    """
    Factory function to create EnhancedListTablesTool

    Args:
        db: SQLDatabase instance

    Returns:
        Configured EnhancedListTablesTool instance
    """
    return EnhancedListTablesTool(db=db)
