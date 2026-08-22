from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from core.config import get_settings
from core.encryption import JWTHandler
from core.events import EventType
from models.user import User, UserType
from schemas.user import UserCreate, UserLogin
from services.user import UserService
from sqlalchemy.exc import IntegrityError, OperationalError

VALID_PASSWORD = "StrongPassw0rd!"


def make_service():
    session = AsyncMock()
    session.add = MagicMock()  # AsyncSession.add() is synchronous, unlike the rest of the API
    producer = AsyncMock()
    return UserService(session=session, producer=producer), session, producer


def make_user_create(**overrides):
    defaults = dict(
        email="jane@example.com", first_name="Jane", last_name="Doe", password=VALID_PASSWORD
    )
    defaults.update(overrides)
    return UserCreate(**defaults)


class TestCreate:
    async def test_hashes_password_saves_user_and_publishes_event(self):
        service, session, producer = make_service()

        with patch("services.user.PasswordHandler.encrypt", return_value="hashed") as encrypt:
            user = await service.create(make_user_create())

        encrypt.assert_called_once_with(VALID_PASSWORD)
        assert user.email == "jane@example.com"
        assert user.password_hash == "hashed"
        assert user.type == UserType.CLIENT
        session.add.assert_called_once_with(user)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(user)

        producer.publish.assert_awaited_once()
        topic, event = producer.publish.await_args.args
        assert event.event_type == EventType.USER_CREATED
        assert event.payload["email"] == "jane@example.com"

    async def test_honors_an_explicit_admin_type(self):
        service, session, producer = make_service()

        with patch("services.user.PasswordHandler.encrypt", return_value="hashed"):
            user = await service.create(make_user_create(type="admin"))

        assert user.type == UserType.ADMIN

    async def test_duplicate_email_rolls_back_and_raises_value_error(self):
        service, session, producer = make_service()
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("dup"))

        with patch("services.user.PasswordHandler.encrypt", return_value="hashed"):
            with pytest.raises(ValueError, match="Email already registered"):
                await service.create(make_user_create())

        session.rollback.assert_awaited_once()
        producer.publish.assert_not_called()

    async def test_db_outage_rolls_back_and_reraises(self):
        service, session, producer = make_service()
        session.commit.side_effect = OperationalError("stmt", {}, Exception("down"))

        with patch("services.user.PasswordHandler.encrypt", return_value="hashed"):
            with pytest.raises(OperationalError):
                await service.create(make_user_create())

        session.rollback.assert_awaited_once()
        producer.publish.assert_not_called()

    async def test_kafka_outage_does_not_fail_a_successful_create(self):
        service, session, producer = make_service()
        producer.publish.side_effect = Exception("kafka down")

        with patch("services.user.PasswordHandler.encrypt", return_value="hashed"):
            user = await service.create(make_user_create())

        assert user.email == "jane@example.com"


class TestLogin:
    def make_existing_user(self, **overrides):
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

    async def test_returns_none_when_user_not_found(self):
        service, session, producer = make_service()
        session.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        token = await service.login(UserLogin(email="jane@example.com", password=VALID_PASSWORD))

        assert token is None
        producer.publish.assert_not_called()

    async def test_returns_none_when_password_does_not_match(self):
        service, session, producer = make_service()
        existing = self.make_existing_user()
        session.execute.return_value = MagicMock(scalar_one_or_none=lambda: existing)

        with patch("services.user.PasswordHandler.verify", return_value=False):
            token = await service.login(
                UserLogin(email="jane@example.com", password=VALID_PASSWORD)
            )

        assert token is None
        producer.publish.assert_not_called()

    async def test_returns_a_valid_jwt_and_publishes_event_on_success(self):
        service, session, producer = make_service()
        existing = self.make_existing_user(type=UserType.ADMIN)
        session.execute.return_value = MagicMock(scalar_one_or_none=lambda: existing)

        with patch("services.user.PasswordHandler.verify", return_value=True):
            token = await service.login(
                UserLogin(email="jane@example.com", password=VALID_PASSWORD)
            )

        assert token is not None
        decoded = JWTHandler().decode(token, get_settings().jwt_secret_key)
        assert decoded["sub"] == str(existing.id)
        assert decoded["email"] == "jane@example.com"
        assert decoded["type"] == "admin"

        producer.publish.assert_awaited_once()
        topic, event = producer.publish.await_args.args
        assert event.event_type == EventType.USER_LOGGED_IN

    async def test_db_outage_during_lookup_reraises(self):
        service, session, producer = make_service()
        session.execute.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.login(UserLogin(email="jane@example.com", password=VALID_PASSWORD))
