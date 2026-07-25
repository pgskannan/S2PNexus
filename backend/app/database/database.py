"""
Database configuration and session management for S2PNexus.

Uses SQLAlchemy 2.x with async support via asyncpg.
Provides async engine, session factory, and base model.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import MetaData, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, declared_attr

from app.core.config import get_settings, Settings

settings = get_settings()

# Naming convention for constraints (helps with Alembic migrations)
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    metadata = metadata

    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Generate table name from class name (snake_case, plural)."""
        import re

        name = cls.__name__
        # Convert CamelCase to snake_case
        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        snake = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
        # Pluralize (simple heuristic)
        if snake.endswith("y"):
            return snake[:-1] + "ies"
        elif snake.endswith("s"):
            return snake + "es"
        else:
            return snake + "s"


class DatabaseManager:
    """Manages database engine and session lifecycle."""

    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    @property
    def engine(self) -> AsyncEngine:
        """Get or create async engine."""
        if self._engine is None:
            self._engine = create_async_engine(
                self._settings.database_url_async,
                pool_size=self._settings.DATABASE_POOL_SIZE,
                max_overflow=self._settings.DATABASE_MAX_OVERFLOW,
                pool_timeout=self._settings.DATABASE_POOL_TIMEOUT,
                pool_recycle=self._settings.DATABASE_POOL_RECYCLE,
                echo=self._settings.DATABASE_ECHO,
                echo_pool=self._settings.DATABASE_ECHO,
                future=True,
            )
            # Add event listeners for connection lifecycle
            self._setup_event_listeners()
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Get or create async session factory."""
        if self._session_factory is None:
            self._session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False,
            )
        return self._session_factory

    def _setup_event_listeners(self) -> None:
        """Set up SQLAlchemy event listeners."""

        @event.listens_for(self.engine.sync_engine, "connect")
        def set_postgresql_timezone(dbapi_connection, connection_record):
            """Set timezone on connection."""
            cursor = dbapi_connection.cursor()
            cursor.execute("SET TIME ZONE 'UTC'")
            cursor.close()

        @event.listens_for(self.engine.sync_engine, "checkout")
        def check_connection(dbapi_connection, connection_record, connection_proxy):
            """Verify connection is alive on checkout."""
            try:
                cursor = dbapi_connection.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
            except Exception:
                # Connection is dead, raise to trigger reconnect
                raise

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a transactional scope as an async context manager."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def create_all(self) -> None:
        """Create all tables (use with caution in production, prefer Alembic)."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_all(self) -> None:
        """Drop all tables (use with extreme caution)."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def close(self) -> None:
        """Close the engine and all connections."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    async def health_check(self) -> bool:
        """Check database connectivity."""
        try:
            async with self.session_factory() as session:
                await session.execute("SELECT 1")
            return True
        except Exception:
            return False


# Global database manager instance
db_manager = DatabaseManager()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database session."""
    async with db_manager.session() as session:
        yield session


async def init_db() -> None:
    """Initialize database (create tables if not using Alembic)."""
    if settings.is_development:
        await db_manager.create_all()


async def close_db() -> None:
    """Close database connections."""
    await db_manager.close()