from unittest.mock import AsyncMock
from uuid import uuid4

import core.auth as auth_module
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from models.user import User, UserType


def make_credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def make_token(**claims) -> str:
    payload = {"sub": str(uuid4())}
    payload.update(claims)
    return await auth_module.jwt_handler.encode(payload, auth_module.settings.jwt_secret_key)


def make_user(**overrides) -> User:
    defaults = dict(
        id=uuid4(),
        email="jane@example.com",
        first_name="Jane",
        last_name="Doe",
        type=UserType.CLIENT,
        password_hash="hashed",
    )
    defaults.update(overrides)
    return User(**defaults)


class TestGetCurrentUser:
    async def test_no_credentials_raises_401(self):
        session = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.get_current_user(credentials=None, session=session)

        assert exc_info.value.status_code == 401

    async def test_invalid_token_raises_401(self):
        session = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.get_current_user(
                credentials=make_credentials("not-a-jwt"), session=session
            )

        assert exc_info.value.status_code == 401

    async def test_non_uuid_subject_raises_401(self):
        session = AsyncMock()
        token = await make_token(sub="not-a-uuid")

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.get_current_user(credentials=make_credentials(token), session=session)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid token"

    async def test_user_no_longer_exists_raises_401(self):
        session = AsyncMock()
        session.get.return_value = None
        token = await make_token()

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.get_current_user(credentials=make_credentials(token), session=session)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "User no longer exists"

    async def test_returns_the_user_on_a_valid_token(self):
        user = make_user()
        session = AsyncMock()
        session.get.return_value = user
        token = await make_token(sub=str(user.id))

        result = await auth_module.get_current_user(
            credentials=make_credentials(token), session=session
        )

        assert result is user


class TestRequireAdmin:
    async def test_rejects_non_admin_user(self):
        user = make_user(type=UserType.CLIENT)

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.require_admin(user=user)

        assert exc_info.value.status_code == 403

    async def test_allows_admin_user(self):
        user = make_user(type=UserType.ADMIN)

        result = await auth_module.require_admin(user=user)

        assert result is user
