"""
Gestión de conexión y sesiones asíncronas de SQLAlchemy.
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str, echo: bool = False) -> AsyncEngine:
    """Crea una instancia configurada de AsyncEngine."""
    return create_async_engine(
        database_url,
        echo=echo,
        future=True,
        pool_pre_ping=True,
    )


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Crea una factoría de sesiones asíncronas."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def get_db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Generador de contexto para sesiones de base de datos."""
    async with session_factory() as session:
        yield session
