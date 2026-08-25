from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from core.seed import seed_initial_admin
from models.user import UserType


def make_settings(**overrides):
    defaults = dict(
        initial_admin_email=None,
        initial_admin_password=None,
        initial_admin_first_name="Admin",
        initial_admin_last_name="User",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_session_factory(session):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=ctx)
    return factory


class TestSeedInitialAdmin:
    async def test_does_nothing_when_not_configured(self):
        session = AsyncMock()

        with (
            patch("core.seed.get_settings", return_value=make_settings()),
            patch("core.seed.async_session_factory", make_session_factory(session)),
        ):
            await seed_initial_admin()

        session.execute.assert_not_called()

    async def test_does_nothing_when_admin_already_exists(self):
        session = AsyncMock()
        session.execute.return_value = MagicMock(scalar_one_or_none=lambda: object())
        settings = make_settings(
            initial_admin_email="admin@example.com", initial_admin_password="Str0ngPass!"
        )

        with (
            patch("core.seed.get_settings", return_value=settings),
            patch("core.seed.async_session_factory", make_session_factory(session)),
        ):
            await seed_initial_admin()

        session.add.assert_not_called()
        session.commit.assert_not_called()

    async def test_creates_the_admin_when_none_exists(self):
        session = AsyncMock()
        session.add = MagicMock()  # AsyncSession.add() is synchronous
        session.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)
        settings = make_settings(
            initial_admin_email="admin@example.com",
            initial_admin_password="Str0ngPass!",
            initial_admin_first_name="Root",
            initial_admin_last_name="Admin",
        )

        with (
            patch("core.seed.get_settings", return_value=settings),
            patch("core.seed.async_session_factory", make_session_factory(session)),
            patch("core.seed.PasswordHandler.encrypt", return_value="hashed"),
        ):
            await seed_initial_admin()

        session.add.assert_called_once()
        (created_user,) = session.add.call_args.args
        assert created_user.email == "admin@example.com"
        assert created_user.first_name == "Root"
        assert created_user.last_name == "Admin"
        assert created_user.type == UserType.ADMIN
        assert created_user.password_hash == "hashed"
        session.commit.assert_awaited_once()
