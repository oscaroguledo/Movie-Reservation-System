from uuid import uuid4

from models.user import User, UserType


def make_user(**overrides):
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


def test_user_type_values():
    assert UserType.ADMIN == "admin"
    assert UserType.REGULAR == "regular"


def test_timestamp_columns_are_timezone_aware():
    """Plain DateTime compiles to Postgres TIMESTAMP WITHOUT TIME ZONE;
    these must be DateTime(timezone=True) so values round-trip correctly
    regardless of client/server timezone."""
    for column_name in ("created_at", "updated_at"):
        column = User.__table__.c[column_name]
        assert column.type.timezone is True, f"User.{column_name} isn't tz-aware"


def test_to_dict_excludes_password_hash():
    user = make_user()

    data = user.to_dict()

    assert "password_hash" not in data
    assert data["email"] == "jane@example.com"
    assert data["first_name"] == "Jane"
    assert data["last_name"] == "Doe"
    assert data["id"] == str(user.id)


def test_to_dict_serializes_type_as_its_string_value():
    user = make_user(type=UserType.ADMIN)

    assert user.to_dict()["type"] == "admin"


def test_to_dict_handles_missing_timestamps():
    user = make_user()

    data = user.to_dict()

    assert data["created_at"] is None
    assert data["updated_at"] is None


def test_repr_includes_id_email_and_type():
    user = make_user(email="jane@example.com", type=UserType.ADMIN)

    text = repr(user)

    assert str(user.id) in text
    assert "jane@example.com" in text
    # f-string rendering of a str-mixed Enum differs across Python versions
    # (e.g. "admin" on 3.10 vs "UserType.ADMIN" on 3.14) — match __repr__'s
    # own formatting rather than hardcoding one version's output.
    assert f"{user.type}" in text
