"""
Schema Introspection Service - Single Responsibility: Handle database schema analysis and context generation
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from .database_connection_service import IDatabaseConnectionService


@dataclass
class ColumnInfo:
    """Information about a database column"""
    name: str
    type: str
    nullable: bool
    primary_key: bool
    description: Optional[str] = None


@dataclass
class TableInfo:
    """Information about a database table"""
    name: str
    columns: List[ColumnInfo]
    sample_data: List[Dict[str, Any]]
    row_count: int


@dataclass
class SchemaContext:
    """Complete schema context for LLM"""
    database_info: str
    tables: List[TableInfo]
    query_examples: List[str]
    important_notes: List[str]
    formatted_context: str


class ISchemaIntrospectionService(ABC):
    """Interface for schema introspection"""
    
    @abstractmethod
    def get_table_info(self, table_name: str) -> TableInfo:
        """Get detailed information about a specific table"""
        pass
    
    @abstractmethod
    def get_schema_context(self) -> SchemaContext:
        """Get complete schema context for LLM queries"""
        pass
    
    @abstractmethod
    def get_sample_data(self, table_name: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Get sample data from a table"""
        pass


class SUSSchemaIntrospectionService(ISchemaIntrospectionService):
    """SUS healthcare database schema introspection service"""
    
    def __init__(self, db_service: IDatabaseConnectionService):
        """
        Initialize schema introspection service
        
        Args:
            db_service: Database connection service
        """
        self._db_service = db_service
        self._cached_context: Optional[SchemaContext] = None
    
    def get_table_info(self, table_name: str) -> TableInfo:
        """Get detailed information about a specific table"""
        conn = self._db_service.get_raw_connection()
        cursor = conn.cursor()
        
        # Get column information
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns_data = cursor.fetchall()
        
        columns = []
        for col in columns_data:
            columns.append(ColumnInfo(
                name=col[1],
                type=col[2],
                nullable=not col[3],
                primary_key=bool(col[5])
            ))
        
        # Get sample data
        sample_data = self.get_sample_data(table_name, limit=3)
        
        # Get row count
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        row_count = cursor.fetchone()[0]
        
        return TableInfo(
            name=table_name,
            columns=columns,
            sample_data=sample_data,
            row_count=row_count
        )
    
    def get_sample_data(self, table_name: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Get sample data from a table"""
        conn = self._db_service.get_raw_connection()
        cursor = conn.cursor()
        
        cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
        rows = cursor.fetchall()
        
        # Get column names
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Convert to list of dictionaries
        return [dict(zip(columns, row)) for row in rows]
    
    def get_schema_context(self) -> SchemaContext:
        """Get complete schema context for SUS healthcare database"""
        if self._cached_context:
            return self._cached_context
        
        # Get table information
        sus_table = self.get_table_info("sus_data")
        
        # Define important notes specific to SUS data
        important_notes = [
            "IMPORTANTE: Para consultas baseadas em cidade, use a coluna CIDADE_RESIDENCIA_PACIENTE",
            "A coluna MUNIC_RES contém códigos numéricos de município, NÃO nomes de cidades",
            "Use MORTE = 1 para consultas sobre óbitos/mortes",
            "Códigos de sexo: 1=Masculino, 3=Feminino (padrão SUS)",
            "Códigos CID-10 estão na coluna DIAG_PRINC",
            "Datas estão no formato AAAAMMDD (DT_INTER, DT_SAIDA)"
        ]
        
        # Define query examples
        query_examples = [
            "-- Mortes em Porto Alegre",
            "SELECT COUNT(*) FROM sus_data WHERE CIDADE_RESIDENCIA_PACIENTE = 'Porto Alegre' AND MORTE = 1",
            "",
            "-- Pacientes por faixa etária",
            "SELECT CASE WHEN IDADE < 18 THEN 'Menor' WHEN IDADE < 65 THEN 'Adulto' ELSE 'Idoso' END as faixa_etaria, COUNT(*) FROM sus_data GROUP BY faixa_etaria",
            "",
            "-- Diagnósticos mais comuns",
            "SELECT DIAG_PRINC, COUNT(*) as total FROM sus_data GROUP BY DIAG_PRINC ORDER BY total DESC LIMIT 10",
            "",
            "-- Custo total por estado",
            "SELECT UF_RESIDENCIA_PACIENTE, SUM(VAL_TOT) as custo_total FROM sus_data GROUP BY UF_RESIDENCIA_PACIENTE"
        ]
        
        # Format complete context
        formatted_context = self._format_context(sus_table, important_notes, query_examples)
        
        self._cached_context = SchemaContext(
            database_info="Sistema Único de Saúde (SUS) - Dados de Hospitalização",
            tables=[sus_table],
            query_examples=query_examples,
            important_notes=important_notes,
            formatted_context=formatted_context
        )
        
        return self._cached_context
    
    def _format_context(
        self, 
        table: TableInfo, 
        notes: List[str], 
        examples: List[str]
    ) -> str:
        """Format complete context for LLM"""
        context = f"""
CONTEXTO DO BANCO DE DADOS - SISTEMA ÚNICO DE SAÚDE (SUS)
========================================================

INFORMAÇÕES DA TABELA: {table.name}
Total de registros: {table.row_count:,}

COLUNAS DISPONÍVEIS:
"""
        
        # Add column descriptions
        column_descriptions = {
            "DIAG_PRINC": "Código do diagnóstico principal (CID-10)",
            "MUNIC_RES": "Código numérico do município de residência (IBGE)",
            "MUNIC_MOV": "Código numérico do município de internação",
            "PROC_REA": "Código do procedimento realizado (SUS)",
            "IDADE": "Idade do paciente em anos",
            "SEXO": "Sexo do paciente (1=Masculino, 3=Feminino)",
            "CID_MORTE": "Código da causa da morte (CID-10)",
            "MORTE": "Indicador de óbito (0=Não, 1=Sim)",
            "CNES": "Código Nacional de Estabelecimento de Saúde",
            "VAL_TOT": "Valor total do procedimento em Reais",
            "UTI_MES_TO": "Total de dias em UTI",
            "DT_INTER": "Data de internação (formato AAAAMMDD)",
            "DT_SAIDA": "Data de saída (formato AAAAMMDD)",
            "UF_RESIDENCIA_PACIENTE": "Estado de residência do paciente",
            "CIDADE_RESIDENCIA_PACIENTE": "Cidade de residência do paciente",
            "LATI_CIDADE_RES": "Latitude da cidade de residência",
            "LONG_CIDADE_RES": "Longitude da cidade de residência"
        }
        
        for col in table.columns:
            description = column_descriptions.get(col.name, "")
            context += f"- {col.name} ({col.type}): {description}\n"
        
        context += "\nNOTAS IMPORTANTES:\n"
        for note in notes:
            context += f"- {note}\n"
        
        context += "\nEXEMPLOS DE CONSULTAS:\n"
        context += "\n".join(examples)
        
        return context
    
    def invalidate_cache(self) -> None:
        """Invalidate cached schema context"""
        self._cached_context = None


class SchemaIntrospectionFactory:
    """Factory for creating schema introspection services"""
    
    @staticmethod
    def create_sus_service(db_service: IDatabaseConnectionService) -> ISchemaIntrospectionService:
        """Create SUS healthcare database schema introspection service"""
        return SUSSchemaIntrospectionService(db_service)
    
    @staticmethod
    def create_service(
        schema_type: str, 
        db_service: IDatabaseConnectionService
    ) -> ISchemaIntrospectionService:
        """Create schema introspection service based on type"""
        if schema_type.lower() == "sus":
            return SUSSchemaIntrospectionService(db_service)
        else:
            raise ValueError(f"Unsupported schema type: {schema_type}")