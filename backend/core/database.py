"""Database connection and schema management for Zoria.

Uses PostgreSQL with pgvector extension for vector storage.
Simplified from zbot-backend - removed device/session management.
"""

import asyncio
import logging
import os
from typing import Optional
import asyncpg
from asyncpg import Pool, Connection

logger = logging.getLogger(__name__)


class Database:
    """PostgreSQL database connection manager with pgvector support."""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "zoria",
        user: str = "zoria",
        password: str = "",
        min_size: int = 5,
        max_size: int = 20
    ):
        """Initialize database connection pool.
        
        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            min_size: Minimum pool size
            max_size: Maximum pool size
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.min_size = min_size
        self.max_size = max_size
        self.pool: Optional[Pool] = None
        self._pool_loop_id: Optional[int] = None
    
    async def connect(self) -> None:
        """Create database connection pool in the current event loop."""
        try:
            loop = asyncio.get_running_loop()
            self._pool_loop_id = id(loop)
            
            self.pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                min_size=self.min_size,
                max_size=self.max_size,
                command_timeout=10,  # Reduced from 60s to 10s for faster failure detection
                max_queries=50000,  # Maximum queries per connection before recycling
                max_inactive_connection_lifetime=300.0  # Close idle connections after 5 minutes
            )
            logger.info(f"Database connection pool created: {self.database}@{self.host}:{self.port}")
            
            # Verify pgvector extension
            await self.ensure_pgvector()
            
        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            raise
    
    async def close(self) -> None:
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")
    
    async def ensure_pgvector(self) -> None:
        """Ensure pgvector extension is installed."""
        self._check_pool()
        async with self.pool.acquire() as conn:
            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                logger.info("pgvector extension verified")
            except Exception as e:
                logger.warning(f"pgvector extension check failed: {e}")
                logger.warning("Vector search may not work. Install pgvector: https://github.com/pgvector/pgvector")
    
    def _check_pool(self) -> None:
        """Check if pool is available and not closed."""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        if self.pool.is_closing():
            raise RuntimeError("Database pool is closing or closed. Cannot execute queries.")
    
    async def execute(self, query: str, *args) -> str:
        """Execute a query and return result."""
        self._check_pool()
        try:
            async with self.pool.acquire() as conn:
                return await conn.execute(query, *args)
        except Exception as e:
            logger.error(f"Database execute error: {e}")
            raise
    
    async def fetch(self, query: str, *args) -> list:
        """Fetch rows from database."""
        self._check_pool()
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except Exception as e:
            logger.error(f"Database fetch error: {e}")
            raise
    
    async def fetchrow(self, query: str, *args) -> Optional[dict]:
        """Fetch a single row from database."""
        self._check_pool()
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, *args)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Database fetchrow error: {e}")
            raise
    
    async def fetchval(self, query: str, *args) -> Optional[any]:
        """Fetch a single value from database."""
        self._check_pool()
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchval(query, *args)
        except Exception as e:
            logger.error(f"Database fetchval error: {e}")
            raise


# Global database instance
_db_instance: Optional[Database] = None


def get_db() -> Database:
    """Get the global database instance.
    
    Returns:
        Database instance
    """
    global _db_instance
    if _db_instance is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db_instance


def init_db() -> Database:
    """Initialize global database instance from environment variables.
    
    Returns:
        Database instance
    """
    global _db_instance
    
    # Get database URL or individual components
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # Parse DATABASE_URL: postgresql://user:password@host:port/database
        from urllib.parse import urlparse
        parsed = urlparse(database_url)
        host = parsed.hostname or os.getenv("DB_HOST", "localhost")
        port = parsed.port or int(os.getenv("DB_PORT", "5432"))
        database = parsed.path.lstrip('/') or os.getenv("DB_NAME", "zoria")
        user = parsed.username or os.getenv("DB_USER", "zoria")
        password = parsed.password or os.getenv("DB_PASSWORD", "")
    else:
        host = os.getenv("DB_HOST", "localhost")
        port = int(os.getenv("DB_PORT", "5432"))
        database = os.getenv("DB_NAME", "zoria")
        user = os.getenv("DB_USER", "zoria")
        password = os.getenv("DB_PASSWORD", "")
    
    _db_instance = Database(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        min_size=int(os.getenv("DB_POOL_MIN_SIZE", "5")),
        max_size=int(os.getenv("DB_POOL_MAX_SIZE", "20"))
    )
    
    return _db_instance
