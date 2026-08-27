"""initial schema

Revision ID: 5ad267d72058
Revises:
Create Date: 2026-08-27 01:58:44.699628

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5ad267d72058"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE SCHEMA IF NOT EXISTS auth_api")
    op.create_table(
        "revoked_tokens",
        sa.Column("jti", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("jti"),
        schema="auth_api",
    )
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "type",
            sa.Enum("admin", "regular", name="user_type", schema="auth_api"),
            server_default="regular",
            nullable=False,
        ),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="auth_api",
    )
    op.create_index(
        op.f("ix_auth_api_users_email"), "users", ["email"], unique=True, schema="auth_api"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_auth_api_users_email"), table_name="users", schema="auth_api")
    op.drop_table("users", schema="auth_api")
    op.drop_table("revoked_tokens", schema="auth_api")
    # Postgres ENUM types are separate objects from the column that uses
    # them — dropping the table doesn't drop the type, so a later re-upgrade
    # would collide with this orphaned one unless it's dropped explicitly.
    sa.Enum(name="user_type", schema="auth_api").drop(op.get_bind(), checkfirst=True)
