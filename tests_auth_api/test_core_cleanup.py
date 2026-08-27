import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.cleanup import purge_expired_revoked_tokens_periodically


class StopAfterOne:
    """A fake asyncio.sleep letting the loop body run once, then cancels it —
    the real loop is meant to run forever, until the caller cancels it."""

    def __init__(self):
        self.calls = 0

    async def __call__(self, _seconds):
        self.calls += 1
        if self.calls > 1:
            raise asyncio.CancelledError


def make_session_factory(session):
    """async_session_factory() itself is sync — it just returns a context
    manager — so the factory mock must be a plain callable, not an AsyncMock."""
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


class TestPurgeExpiredRevokedTokensPeriodically:
    async def test_purges_once_per_iteration(self):
        token_service = AsyncMock()
        token_service.purge_expired.return_value = 2
        fake_sleep = StopAfterOne()

        with (
            patch("core.cleanup.asyncio.sleep", fake_sleep),
            patch("core.cleanup.async_session_factory", make_session_factory(AsyncMock())),
            patch("core.cleanup.TokenService", return_value=token_service),
        ):
            with pytest.raises(asyncio.CancelledError):
                await purge_expired_revoked_tokens_periodically(interval_seconds=0)

        token_service.purge_expired.assert_awaited_once()

    async def test_logs_when_rows_were_purged(self, caplog):
        caplog.set_level(logging.INFO)
        token_service = AsyncMock()
        token_service.purge_expired.return_value = 2
        fake_sleep = StopAfterOne()

        with (
            patch("core.cleanup.asyncio.sleep", fake_sleep),
            patch("core.cleanup.async_session_factory", make_session_factory(AsyncMock())),
            patch("core.cleanup.TokenService", return_value=token_service),
        ):
            with pytest.raises(asyncio.CancelledError):
                await purge_expired_revoked_tokens_periodically(interval_seconds=0)

        assert "Purged 2" in caplog.text

    async def test_does_not_log_when_nothing_was_purged(self, caplog):
        token_service = AsyncMock()
        token_service.purge_expired.return_value = 0
        fake_sleep = StopAfterOne()

        with (
            patch("core.cleanup.asyncio.sleep", fake_sleep),
            patch("core.cleanup.async_session_factory", make_session_factory(AsyncMock())),
            patch("core.cleanup.TokenService", return_value=token_service),
        ):
            with pytest.raises(asyncio.CancelledError):
                await purge_expired_revoked_tokens_periodically(interval_seconds=0)

        assert "Purged" not in caplog.text

    async def test_a_failed_purge_is_logged_and_does_not_stop_the_loop(self, caplog):
        fake_sleep = StopAfterOne()

        with (
            patch("core.cleanup.asyncio.sleep", fake_sleep),
            patch("core.cleanup.async_session_factory", side_effect=RuntimeError("db down")),
        ):
            with pytest.raises(asyncio.CancelledError):
                await purge_expired_revoked_tokens_periodically(interval_seconds=0)

        assert fake_sleep.calls == 2
        assert "Failed to purge expired revoked tokens" in caplog.text
