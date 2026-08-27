from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from services.token import TokenService
from sqlalchemy.exc import IntegrityError, OperationalError


def make_service():
    session = AsyncMock()
    session.add = MagicMock()
    return TokenService(session), session


class TestRevoke:
    async def test_adds_and_commits_a_revoked_token(self):
        service, session = make_service()

        await service.revoke("a-jti", datetime.now(timezone.utc))

        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    async def test_double_revocation_is_a_no_op(self):
        service, session = make_service()
        session.commit.side_effect = IntegrityError("s", {}, Exception())

        await service.revoke("a-jti", datetime.now(timezone.utc))

        session.rollback.assert_awaited_once()

    async def test_db_outage_rolls_back_and_reraises(self):
        service, session = make_service()
        session.commit.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await service.revoke("a-jti", datetime.now(timezone.utc))


class TestIsRevoked:
    async def test_returns_false_when_not_found(self):
        service, session = make_service()
        session.get.return_value = None

        assert await service.is_revoked("a-jti") is False

    async def test_returns_true_when_found(self):
        service, session = make_service()
        session.get.return_value = MagicMock()

        assert await service.is_revoked("a-jti") is True


class TestPurgeExpired:
    async def test_deletes_and_commits_returning_the_row_count(self):
        service, session = make_service()
        session.execute.return_value = MagicMock(rowcount=3)

        deleted = await service.purge_expired(datetime.now(timezone.utc))

        assert deleted == 3
        session.commit.assert_awaited_once()

    async def test_returns_zero_when_nothing_to_purge(self):
        service, session = make_service()
        session.execute.return_value = MagicMock(rowcount=0)

        assert await service.purge_expired(datetime.now(timezone.utc)) == 0
