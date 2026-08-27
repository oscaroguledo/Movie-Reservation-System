from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .user import Base


class RevokedToken(Base):
    """A logged-out token's jti, kept until its own expiry passes."""

    __tablename__ = "revoked_tokens"
    __table_args__ = {"schema": "auth_api"}

    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<RevokedToken(jti={self.jti})>"
