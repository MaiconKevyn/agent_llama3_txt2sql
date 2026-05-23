from abc import ABC, abstractmethod

from langchain_community.utilities import SQLDatabase


class IDatabaseConnectionService(ABC):
    """Interface for database connection management"""

    @abstractmethod
    def get_connection(self) -> SQLDatabase:
        """Get database connection"""
        pass

    @abstractmethod
    def close_connection(self) -> None:
        """Close database connection"""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Test if database connection is working"""
        pass


class PostgreSQLDatabaseConnectionService(IDatabaseConnectionService):
    """PostgreSQL implementation of database connection service"""

    def __init__(self, db_path: str):
        """
        Initialize PostgreSQL database connection service

        Args:
            db_path: PostgreSQL connection string
        """
        self._db_path = db_path
        self._connection: SQLDatabase | None = None
        self._raw_connection = None

    def get_connection(self) -> SQLDatabase:
        """Get LangChain SQLDatabase connection"""
        if self._connection is None:
            self._connection = SQLDatabase.from_uri(self._db_path)
        return self._connection

    def get_raw_connection(self):
        """Get raw PostgreSQL connection for direct queries"""
        if self._raw_connection is None:
            try:
                import psycopg2

                # Convert sqlalchemy URL to psycopg2 format
                db_url = self._db_path.replace("postgresql+psycopg2://", "postgresql://")
                self._raw_connection = psycopg2.connect(db_url)
            except ImportError:
                raise ImportError("psycopg2 não instalado. Execute: pip install psycopg2-binary")
        return self._raw_connection

    def close_connection(self) -> None:
        """Close database connections"""
        if self._raw_connection:
            self._raw_connection.close()
            self._raw_connection = None
        self._connection = None

    def test_connection(self) -> bool:
        """Test if database connection is working"""
        try:
            import psycopg2

            db_url = self._db_path.replace("postgresql+psycopg2://", "postgresql://")
            conn = psycopg2.connect(db_url)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            conn.close()
            return result is not None
        except Exception:
            return False

    def get_database_path(self) -> str:
        """Get database connection string"""
        return self._db_path


class DatabaseConnectionFactory:
    """Factory for creating database connection services"""

    @staticmethod
    def create_postgresql_service(db_path: str) -> IDatabaseConnectionService:
        """Create PostgreSQL database connection service"""
        return PostgreSQLDatabaseConnectionService(db_path)

    @staticmethod
    def create_service(db_type: str, **kwargs) -> IDatabaseConnectionService:
        """Create database connection service based on type"""
        if db_type.lower() == "postgresql":
            return PostgreSQLDatabaseConnectionService(kwargs.get("db_path"))
        else:
            raise ValueError(f"Unsupported database type: {db_type}")
