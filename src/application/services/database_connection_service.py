"""
Database Connection Service - Single Responsibility: Manage database connections
"""
from abc import ABC, abstractmethod
from typing import Optional
from langchain_community.utilities import SQLDatabase
import sqlite3


class IDatabaseConnectionService(ABC):
    """Interface for database connection management"""
    
    @abstractmethod
    def get_connection(self) -> SQLDatabase:
        """Get database connection"""
        pass
    
    @abstractmethod
    def get_raw_connection(self) -> sqlite3.Connection:
        """Get raw SQLite connection for direct queries"""
        pass
    
    @abstractmethod
    def close_connection(self) -> None:
        """Close database connection"""
        pass
    
    @abstractmethod
    def test_connection(self) -> bool:
        """Test if database connection is working"""
        pass


class SQLiteDatabaseConnectionService(IDatabaseConnectionService):
    """SQLite implementation of database connection service"""
    
    def __init__(self, db_path: str = "sus_database.db"):
        """
        Initialize SQLite database connection service
        
        Args:
            db_path: Path to SQLite database file
        """
        self._db_path = db_path
        self._connection: Optional[SQLDatabase] = None
        self._raw_connection: Optional[sqlite3.Connection] = None
    
    def get_connection(self) -> SQLDatabase:
        """Get LangChain SQLDatabase connection"""
        if self._connection is None:
            self._connection = SQLDatabase.from_uri(f"sqlite:///{self._db_path}")
        return self._connection
    
    def get_raw_connection(self) -> sqlite3.Connection:
        """Get raw SQLite connection for direct queries"""
        if self._raw_connection is None:
            self._raw_connection = sqlite3.connect(self._db_path)
        return self._raw_connection
    
    def close_connection(self) -> None:
        """Close database connections"""
        if self._raw_connection:
            self._raw_connection.close()
            self._raw_connection = None
        # LangChain SQLDatabase doesn't need explicit closing
        self._connection = None
    
    def test_connection(self) -> bool:
        """Test if database connection is working"""
        try:
            conn = self.get_raw_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            return result is not None
        except Exception:
            return False
    
    def get_database_path(self) -> str:
        """Get database file path"""
        return self._db_path


class DatabaseConnectionFactory:
    """Factory for creating database connection services"""
    
    @staticmethod
    def create_sqlite_service(db_path: str = "sus_database.db") -> IDatabaseConnectionService:
        """Create SQLite database connection service"""
        return SQLiteDatabaseConnectionService(db_path)
    
    @staticmethod
    def create_service(db_type: str, **kwargs) -> IDatabaseConnectionService:
        """Create database connection service based on type"""
        if db_type.lower() == "sqlite":
            return SQLiteDatabaseConnectionService(kwargs.get("db_path", "sus_database.db"))
        else:
            raise ValueError(f"Unsupported database type: {db_type}")