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
        type=UserType.REGULAR,
        password_hash="hashed",
    )
    defaults.update(overrides)
    return User(**defaults)


class TestGetCurrentTokenPayload:
    async def test_no_credentials_raises_401(self):
        session = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.get_current_token_payload(credentials=None, session=session)

        assert exc_info.value.status_code == 401

    async def test_invalid_token_raises_401(self):
        session = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.get_current_token_payload(
                credentials=make_credentials("not-a-jwt"), session=session
            )

        assert exc_info.value.status_code == 401

    async def test_revoked_token_raises_401(self):
        session = AsyncMock()
        session.get.return_value = object()  # RevokedToken row found
        token = await make_token()

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.get_current_token_payload(
                credentials=make_credentials(token), session=session
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token has been revoked"

    async def test_returns_the_decoded_payload_when_not_revoked(self):
        session = AsyncMock()
        session.get.return_value = None
        token = await make_token(sub="user-1")

        payload = await auth_module.get_current_token_payload(
            credentials=make_credentials(token), session=session
        )

        assert payload["sub"] == "user-1"
        assert "jti" in payload


class TestGetCurrentUser:
    async def test_non_uuid_subject_raises_401(self):
        session = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.get_current_user(payload={"sub": "not-a-uuid"}, session=session)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid token"

    async def test_user_no_longer_exists_raises_401(self):
        session = AsyncMock()
        session.get.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.get_current_user(payload={"sub": str(uuid4())}, session=session)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "User no longer exists"

    async def test_returns_the_user_on_a_valid_payload(self):
        user = make_user()
        session = AsyncMock()
        session.get.return_value = user

        result = await auth_module.get_current_user(payload={"sub": str(user.id)}, session=session)

        assert result is user


class TestRequireAdmin:
    async def test_rejects_non_admin_user(self):
        user = make_user(type=UserType.REGULAR)

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.require_admin(user=user)

        assert exc_info.value.status_code == 403

    async def test_allows_admin_user(self):
        user = make_user(type=UserType.ADMIN)

        result = await auth_module.require_admin(user=user)

        assert result is user
