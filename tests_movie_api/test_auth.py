from uuid import uuid4

import core.auth as auth_module
import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from models import ReservationUserType


def make_credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def make_token(**claims) -> str:
    payload = {"sub": str(uuid4()), "type": "regular"}
    payload.update(claims)
    return jwt.encode(payload, auth_module.settings.jwt_secret_key, algorithm="HS256")


class TestGetCurrentPrincipal:
    async def test_no_credentials_returns_guest(self):
        principal = await auth_module.get_current_principal(credentials=None)

        assert principal.user_id is None
        assert principal.type == ReservationUserType.GUEST

    async def test_invalid_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            await auth_module.get_current_principal(credentials=make_credentials("not-a-jwt"))

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid token"

    async def test_expired_token_raises_401(self):
        token = jwt.encode(
            {"sub": str(uuid4()), "type": "regular", "exp": 0},
            auth_module.settings.jwt_secret_key,
            algorithm="HS256",
        )

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.get_current_principal(credentials=make_credentials(token))

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token has expired"

    async def test_non_uuid_subject_raises_401(self):
        token = make_token(sub="not-a-uuid")

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.get_current_principal(credentials=make_credentials(token))

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid token"

    async def test_unknown_type_claim_raises_401(self):
        token = make_token(type="superuser")

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.get_current_principal(credentials=make_credentials(token))

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid token"

    async def test_missing_type_claim_raises_401(self):
        token = jwt.encode(
            {"sub": str(uuid4())}, auth_module.settings.jwt_secret_key, algorithm="HS256"
        )

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.get_current_principal(credentials=make_credentials(token))

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid token"

    async def test_returns_principal_from_valid_token(self):
        user_id = uuid4()
        token = make_token(sub=str(user_id), type="admin")

        principal = await auth_module.get_current_principal(credentials=make_credentials(token))

        assert principal.user_id == user_id
        assert principal.type == ReservationUserType.ADMIN


class TestRequireAdmin:
    async def test_rejects_guest(self):
        principal = auth_module.Principal(user_id=None, type=ReservationUserType.GUEST)

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.require_admin(principal=principal)

        assert exc_info.value.status_code == 403

    async def test_rejects_regular_user(self):
        principal = auth_module.Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.require_admin(principal=principal)

        assert exc_info.value.status_code == 403

    async def test_allows_admin(self):
        principal = auth_module.Principal(user_id=uuid4(), type=ReservationUserType.ADMIN)

        result = await auth_module.require_admin(principal=principal)

        assert result is principal


class TestRequireAuthenticated:
    async def test_rejects_guest(self):
        principal = auth_module.Principal(user_id=None, type=ReservationUserType.GUEST)

        with pytest.raises(HTTPException) as exc_info:
            await auth_module.require_authenticated(principal=principal)

        assert exc_info.value.status_code == 401

    async def test_allows_authenticated_user(self):
        principal = auth_module.Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)

        result = await auth_module.require_authenticated(principal=principal)

        assert result is principal
