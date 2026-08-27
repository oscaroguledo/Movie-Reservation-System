from datetime import datetime, timezone

from models.revoked_token import RevokedToken


def make_revoked_token(**overrides):
    defaults = dict(jti="a-jti", expires_at=datetime.now(timezone.utc))
    defaults.update(overrides)
    return RevokedToken(**defaults)


def test_timestamp_columns_are_timezone_aware():
    for column_name in ("expires_at", "revoked_at"):
        column = RevokedToken.__table__.c[column_name]
        assert column.type.timezone is True, f"RevokedToken.{column_name} isn't tz-aware"


def test_repr_includes_the_jti():
    assert "a-jti" in repr(make_revoked_token())
