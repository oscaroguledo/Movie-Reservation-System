import asyncio
import logging
from datetime import datetime, timezone

from core.db.postgresql import async_session_factory
from services.token import TokenService

logger = logging.getLogger(__name__)


async def purge_expired_revoked_tokens_periodically(interval_seconds: int) -> None:
    """Runs until cancelled, deleting revoked_tokens rows whose own token
    has already expired — harmless to keep, but they'd grow forever."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            async with async_session_factory() as session:
                deleted = await TokenService(session).purge_expired(datetime.now(timezone.utc))
            if deleted:
                logger.info("Purged %d expired revoked-token row(s)", deleted)
        except Exception:
            logger.exception("Failed to purge expired revoked tokens")
