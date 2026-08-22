from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.config import get_settings
from core.db.postgresql import engine, get_session, init_models
from models import Base
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


async def test_init_models_creates_schema_and_tables():
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_conn.run_sync = AsyncMock()

    mock_begin_ctx = MagicMock()
    mock_begin_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_begin_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("core.db.postgresql.engine") as mock_engine:
        mock_engine.begin.return_value = mock_begin_ctx
        await init_models()

    mock_conn.execute.assert_awaited_once()
    schema_sql = str(mock_conn.execute.await_args.args[0])
    assert "CREATE SCHEMA IF NOT EXISTS reservation_api" in schema_sql
    mock_conn.run_sync.assert_awaited_once_with(Base.metadata.create_all)
