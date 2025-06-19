"""
Query Result Entity - Represents the result of a database query with metadata
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime
import statistics


@dataclass(frozen=True)
class QueryResult:
    """
    Query Result entity representing the outcome of a database query
    
    Encapsulates query results with performance metrics, statistical analysis,
    and error handling capabilities for comprehensive query result management.
    """
    sql_query: str
    raw_results: List[Dict[str, Any]]
    execution_time_seconds: float
    timestamp: datetime
    success: bool
    error_message: Optional[str] = None
    row_count: Optional[int] = None
    
    def __post_init__(self):
        """Initialize computed fields after object creation"""
        if self.row_count is None:
            object.__setattr__(self, 'row_count', len(self.raw_results))
        self._validate()
    
    def _validate(self):
        """Validate query result data"""
        if self.execution_time_seconds < 0:
            raise ValueError("Execution time cannot be negative")
        
        if not self.success and not self.error_message:
            raise ValueError("Failed queries must have an error message")
        
        if self.success and self.error_message:
            raise ValueError("Successful queries should not have error messages")
    
    @property
    def performance_category(self) -> str:
        """Categorize query performance based on execution time"""
        if self.execution_time_seconds < 0.1:
            return "Muito rápida"
        elif self.execution_time_seconds < 0.5:
            return "Rápida"
        elif self.execution_time_seconds < 2.0:
            return "Moderada"
        elif self.execution_time_seconds < 5.0:
            return "Lenta"
        else:
            return "Muito lenta"
    
    @property
    def result_size_category(self) -> str:
        """Categorize result size"""
        if self.row_count == 0:
            return "Vazio"
        elif self.row_count == 1:
            return "Resultado único"
        elif self.row_count < 10:
            return "Pequeno"
        elif self.row_count < 100:
            return "Médio"
        elif self.row_count < 1000:
            return "Grande"
        else:
            return "Muito grande"
    
    @property
    def has_numeric_results(self) -> bool:
        """Check if results contain numeric data"""
        if not self.raw_results:
            return False
        
        first_row = self.raw_results[0]
        return any(isinstance(value, (int, float)) for value in first_row.values())
    
    @property
    def query_type(self) -> str:
        """Determine the type of SQL query"""
        query_upper = self.sql_query.upper().strip()
        
        if query_upper.startswith('SELECT'):
            if 'COUNT(' in query_upper:
                return "Contagem"
            elif 'SUM(' in query_upper:
                return "Soma"
            elif 'AVG(' in query_upper:
                return "Média"
            elif 'GROUP BY' in query_upper:
                return "Agrupamento"
            else:
                return "Seleção"
        elif query_upper.startswith('INSERT'):
            return "Inserção"
        elif query_upper.startswith('UPDATE'):
            return "Atualização"
        elif query_upper.startswith('DELETE'):
            return "Exclusão"
        else:
            return "Outro"
    
    def get_numeric_columns(self) -> List[str]:
        """Get list of columns that contain numeric data"""
        if not self.raw_results:
            return []
        
        numeric_columns = []
        first_row = self.raw_results[0]
        
        for column, value in first_row.items():
            if isinstance(value, (int, float)):
                numeric_columns.append(column)
        
        return numeric_columns
    
    def calculate_column_statistics(self, column_name: str) -> Dict[str, Any]:
        """Calculate statistics for a numeric column"""
        if not self.raw_results:
            return {"error": "No results available"}
        
        values = []
        for row in self.raw_results:
            if column_name in row and isinstance(row[column_name], (int, float)):
                values.append(row[column_name])
        
        if not values:
            return {"error": f"Column '{column_name}' not found or not numeric"}
        
        return {
            "count": len(values),
            "sum": sum(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "min": min(values),
            "max": max(values),
            "std_dev": statistics.stdev(values) if len(values) > 1 else 0
        }
    
    def get_sample_results(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get a sample of results for display"""
        return self.raw_results[:limit]
    
    def format_for_display(self) -> str:
        """Format query result for user display"""
        if not self.success:
            return f"❌ Erro na consulta: {self.error_message}"
        
        if self.row_count == 0:
            return "📊 Nenhum resultado encontrado"
        
        if self.row_count == 1 and len(self.raw_results[0]) == 1:
            # Single value result
            value = list(self.raw_results[0].values())[0]
            return f"📊 Resultado: {value}"
        
        # Multiple results
        result_text = f"📊 {self.row_count} resultados encontrados\n"
        result_text += f"⏱️ Tempo de execução: {self.execution_time_seconds:.2f}s\n"
        result_text += f"🔍 Tipo de consulta: {self.query_type}\n"
        
        if self.row_count <= 5:
            result_text += "\n🔢 Resultados:\n"
            for i, row in enumerate(self.raw_results, 1):
                result_text += f"  {i}. {row}\n"
        else:
            result_text += f"\n🔢 Primeiros 5 resultados:\n"
            for i, row in enumerate(self.get_sample_results(), 1):
                result_text += f"  {i}. {row}\n"
            result_text += f"  ... e mais {self.row_count - 5} resultados"
        
        return result_text
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics"""
        return {
            "execution_time": self.execution_time_seconds,
            "performance_category": self.performance_category,
            "row_count": self.row_count,
            "result_size_category": self.result_size_category,
            "query_type": self.query_type,
            "has_numeric_data": self.has_numeric_results,
            "numeric_columns": self.get_numeric_columns(),
            "timestamp": self.timestamp.isoformat(),
            "success": self.success
        }
    
    def export_to_dict(self) -> Dict[str, Any]:
        """Export complete query result to dictionary"""
        return {
            "sql_query": self.sql_query,
            "raw_results": self.raw_results,
            "execution_time_seconds": self.execution_time_seconds,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "error_message": self.error_message,
            "row_count": self.row_count,
            "performance_metrics": self.get_performance_metrics(),
            "formatted_display": self.format_for_display()
        }
    
    def compare_performance_with(self, other_result: 'QueryResult') -> str:
        """Compare performance with another query result"""
        time_diff = self.execution_time_seconds - other_result.execution_time_seconds
        
        if abs(time_diff) < 0.01:  # Less than 10ms difference
            return "Performance similar"
        elif time_diff > 0:
            percentage = (time_diff / other_result.execution_time_seconds) * 100
            return f"{percentage:.1f}% mais lenta"
        else:
            percentage = (abs(time_diff) / self.execution_time_seconds) * 100
            return f"{percentage:.1f}% mais rápida"