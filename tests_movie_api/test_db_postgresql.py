import pytest
from core.config import get_settings
from core.db.postgresql import engine, get_session
from sqlalchemy.ext.asyncio import AsyncSession


def test_engine_is_configured_from_settings():
    settings = get_settings()

    assert engine.url.drivername == "postgresql+asyncpg"
    assert engine.url.database == settings.postgres_url.rsplit("/", 1)[-1]


async def test_get_session_yields_and_closes_an_async_session():
    agen = get_session()
    session = await agen.__anext__()

    assert isinstance(session, AsyncSession)

    with pytest.raises(StopAsyncIteration):
        await agen.__anext__()
