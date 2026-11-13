"""Асинхронное подключение к PostgreSQL."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

SessionFactory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-зависимость: сессия на запрос."""
    async with SessionFactory() as session:
        yield session


async def init_models() -> None:
    """Создание таблиц (если их ещё нет)."""
    from app import models  # noqa: F401  (регистрация моделей в метаданных)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
