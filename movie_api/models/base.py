from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared registry so foreign keys resolve across model modules."""
