import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import Enum, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared registry so foreign keys resolve across model modules."""


class UserType(str, enum.Enum):
    ADMIN = "admin"
    CLIENT = "client"


class User(Base):
    """Movie Reservation System user model."""

    __tablename__ = "users"
    __table_args__ = {"schema": "auth_api"}

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    type: Mapped[UserType] = mapped_column(
        Enum(
            UserType,
            name="user_type",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=UserType.CLIENT,
        server_default=UserType.CLIENT.value,
    )
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', type='{self.type}')>"

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "type": self.type.value if isinstance(self.type, enum.Enum) else self.type,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
