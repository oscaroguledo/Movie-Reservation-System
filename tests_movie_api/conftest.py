from unittest.mock import AsyncMock, MagicMock

import pytest
from fakes import FakeRedis


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """One shared fake store patched into every resource's redis.py, the
    same way one real Redis instance backs all of them in production —
    lets cross-resource tests (e.g. screening's seat map reading
    reservation holds) work without extra wiring."""
    redis = FakeRedis()
    for module in (
        "repository.genre.redis",
        "repository.movie.redis",
        "repository.showroom.redis",
        "repository.screening.redis",
        "repository.reservation.redis",
    ):
        monkeypatch.setattr(f"{module}.redis_client", redis)
    return redis


@pytest.fixture(autouse=True)
def fake_postgres_session(monkeypatch):
    """Every service's Redis-cache-miss fallback opens its own Postgres
    session via async_session_factory(); this patches that factory in
    every service module to hand back one shared AsyncMock session
    (defaulting to "nothing found" — get()/execute() both empty) so
    tests never need a real database. Tests wanting to exercise the
    fallback-with-data path customize this mock's return values."""
    session = AsyncMock()
    session.get.return_value = None
    session.execute.return_value = MagicMock(
        scalars=lambda: MagicMock(all=lambda: []), all=lambda: []
    )

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=ctx)

    for module in (
        "services.genre",
        "services.movie",
        "services.showroom",
        "services.screening",
        "services.reservation",
    ):
        monkeypatch.setattr(f"{module}.async_session_factory", factory)

    return session
