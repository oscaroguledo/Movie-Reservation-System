from collections.abc import AsyncGenerator

from core.config import get_settings
from models import Base
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

settings = get_settings()

engine = create_async_engine(settings.postgres_url)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def init_models() -> None:
    """Creates the reservation_api schema and any tables that don't exist yet.

    Stands in for real migrations (no Alembic in this project yet) — fine
    for local dev, but it won't pick up schema changes on an existing table.
    """
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS reservation_api"))
        await conn.run_sync(Base.metadata.create_all)
