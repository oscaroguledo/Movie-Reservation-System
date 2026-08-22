import logging
from collections.abc import Sequence

from core.config import get_settings
from core.encryption import JWTHandler, PasswordHandler
from core.events import TOPIC, Event, EventType
from core.kafka import KafkaProducer
from models.user import User, UserType
from schemas.user import UserCreate, UserGet, UserList, UserLogin, UserUpdate
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

settings = get_settings()
jwt_handler = JWTHandler(default_expiration_minutes=settings.jwt_default_expiration_minutes)


class UserService:
    def __init__(self, session: AsyncSession, producer: KafkaProducer):
        self.session = session
        self.producer = producer

    async def create(self, user_create: UserCreate) -> User:
        password_hash = await PasswordHandler.encrypt(user_create.password)
        new_user = User(
            email=user_create.email,
            first_name=user_create.first_name,
            last_name=user_create.last_name,
            type=UserType(user_create.type) if user_create.type else UserType.CLIENT,
            password_hash=password_hash,
        )
        try:
            self.session.add(new_user)
            await self.session.commit()
            await self.session.refresh(new_user)
        except IntegrityError as exc:
            await self.session.rollback()
            logger.warning(
                "User creation failed due to conflict (email already exists): %s",
                user_create.email,
            )
            raise ValueError("Email already registered") from exc
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while creating user %s — safe to retry",
                user_create.email,
            )
            raise
        except Exception:
            await self.session.rollback()
            logger.exception("Failed to create user %s", user_create.email)
            raise
        finally:
            logger.debug("Create attempt finished for %s", user_create.email)

        await self._publish_event(EventType.USER_CREATED, new_user)
        return new_user

    async def login(self, user_login: UserLogin) -> str | None:
        try:
            result = await self.session.execute(select(User).where(User.email == user_login.email))
            user = result.scalar_one_or_none()
        except OperationalError:
            logger.error(
                "Database unavailable while looking up user %s — safe to retry",
                user_login.email,
            )
            raise
        except Exception:
            logger.exception("Failed to look up user %s during login", user_login.email)
            raise
        finally:
            logger.debug("Login lookup finished for %s", user_login.email)

        if not user or not await PasswordHandler.verify(user_login.password, user.password_hash):
            return None

        await self._publish_event(EventType.USER_LOGGED_IN, user)

        return await jwt_handler.encode(
            {
                "sub": str(user.id),
                "email": user.email,
                "type": user.type.value if isinstance(user.type, UserType) else user.type,
            },
            settings.jwt_secret_key,
        )

    async def get(self, user_get: UserGet) -> User | None:
        if not user_get.id and not user_get.email:
            raise ValueError("UserService.get requires id or email to look up a single user")

        filters = [(User.id == user_get.id) if user_get.id else (User.email == user_get.email)]
        if user_get.type:
            filters.append(User.type == user_get.type)

        try:
            result = await self.session.execute(select(User).where(*filters))
            user = result.scalar_one_or_none()
        except OperationalError:
            logger.error(
                "Database unavailable while looking up user %s — safe to retry",
                user_get,
            )
            raise
        except Exception:
            logger.exception("Failed to look up user %s", user_get)
            raise
        finally:
            logger.debug("Get lookup finished for %s", user_get)

        return user

    async def list(self, user_list: UserList, limit: int = 100, offset: int = 0) -> Sequence[User]:
        filters = []
        if user_list.type:
            filters.append(User.type == user_list.type)
        if user_list.first_name:
            filters.append(User.first_name == user_list.first_name)
        if user_list.last_name:
            filters.append(User.last_name == user_list.last_name)

        try:
            result = await self.session.execute(
                select(User).where(*filters).limit(limit).offset(offset)
            )
            users = result.scalars().all()
        except OperationalError:
            logger.error("Database unavailable while listing users — safe to retry")
            raise
        except Exception:
            logger.exception("Failed to list users")
            raise
        finally:
            logger.debug("List attempt finished with limit %d and offset %d", limit, offset)

        return users

    async def update(self, user_id: str, user_update: UserUpdate) -> User | None:
        try:
            result = await self.session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return None

            if user_update.first_name is not None:
                user.first_name = user_update.first_name
            if user_update.last_name is not None:
                user.last_name = user_update.last_name
            if user_update.password is not None:
                user.password_hash = await PasswordHandler.encrypt(user_update.password)
            if user_update.type is not None:
                user.type = UserType(user_update.type)

            await self.session.commit()
            await self.session.refresh(user)
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while updating user %s — safe to retry",
                user_id,
            )
            raise
        except Exception:
            await self.session.rollback()
            logger.exception("Failed to update user %s", user_id)
            raise
        finally:
            logger.debug("Update attempt finished for user %s", user_id)

        await self._publish_event(EventType.USER_UPDATED, user)
        return user

    async def _publish_event(self, event_type: EventType, user: User) -> None:
        """A Kafka outage must never fail a request that already succeeded
        in the database — log and move on rather than let it propagate."""
        try:
            await self.producer.publish(
                TOPIC,
                Event(event_type=event_type, payload=user.to_dict()),
            )
        except Exception:
            logger.exception("Failed to publish %s event for user %s", event_type, user.id)
        finally:
            logger.debug("Publish attempt finished for %s event (user %s)", event_type, user.id)
