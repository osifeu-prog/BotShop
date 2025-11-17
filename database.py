import logging
from contextlib import contextmanager
from typing import Generator, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool

from config import config

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Connection pooling + simple helpers for Postgres"""

    _instance = None
    _connection_pool: Optional[SimpleConnectionPool] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._initialize_pool()
        return cls._instance

    @classmethod
    def _initialize_pool(cls):
        if not config.DATABASE_URL:
            logger.warning("DATABASE_URL not set – DB will be unavailable")
            return
        try:
            cls._connection_pool = SimpleConnectionPool(
                1,
                config.DATABASE_POOL_SIZE,
                dsn=config.DATABASE_URL,
            )
            logger.info("Database connection pool initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            cls._connection_pool = None

    @contextmanager
    def get_connection(self) -> Generator[Optional[psycopg2.extensions.connection], None, None]:
        conn = None
        if not self._connection_pool:
            yield None
            return
        try:
            conn = self._connection_pool.getconn()
            yield conn
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            if conn:
                self._connection_pool.putconn(conn, close=True)
            raise
        finally:
            if conn:
                self._connection_pool.putconn(conn)

    @contextmanager
    def get_cursor(self, commit: bool = False) -> Generator[Optional[RealDictCursor], None, None]:
        with self.get_connection() as conn:
            if conn is None:
                yield None
                return
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            try:
                yield cursor
                if commit:
                    conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Database cursor error: {e}")
                raise
            finally:
                cursor.close()

    def execute_query(self, query: str, params: tuple = None, commit: bool = False):
        with self.get_cursor(commit=commit) as cursor:
            if cursor is None:
                return []
            cursor.execute(query, params or ())
            try:
                return cursor.fetchall()
            except psycopg2.ProgrammingError:
                return []

    def execute_command(self, command: str, params: tuple = None) -> bool:
        with self.get_cursor(commit=True) as cursor:
            if cursor is None:
                return False
            cursor.execute(command, params or ())
            return True

    def health_check(self) -> bool:
        try:
            with self.get_cursor() as cursor:
                if cursor is None:
                    return False
                cursor.execute("SELECT 1")
                cursor.fetchone()
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

db = DatabaseManager()
