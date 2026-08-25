import logging

from core.config import get_settings
from core.db.postgresql import async_session_factory
from core.encryption import PasswordHandler
from models.user import User, UserType
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def seed_initial_admin() -> None:
    """Creates the initial admin from env-configured credentials, if one
    doesn't already exist.

    This is the only way to bootstrap the very first admin: every
    admin-management endpoint (POST /register/admin, promoting a user's
    type) itself requires an existing admin via require_admin, which is a
    deadlock on a fresh system with zero users.
    """
    settings = get_settings()
    if not settings.initial_admin_email or not settings.initial_admin_password:
        return

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == settings.initial_admin_email)
        )
        if result.scalar_one_or_none() is not None:
            return

        password_hash = await PasswordHandler.encrypt(settings.initial_admin_password)
        session.add(
            User(
                email=settings.initial_admin_email,
                first_name=settings.initial_admin_first_name,
                last_name=settings.initial_admin_last_name,
                type=UserType.ADMIN,
                password_hash=password_hash,
            )
        )
        await session.commit()
        logger.info("Seeded initial admin user: %s", settings.initial_admin_email)
