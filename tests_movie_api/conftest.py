import pytest
from fakes import FakeRedis


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """One shared fake store patched into every resource's redis.py,
    the same way one real Redis instance backs all of them in production."""
    redis = FakeRedis()
    for module in (
        "repository.genre.redis",
        "repository.movie.redis",
        "repository.showroom.redis",
        "repository.screening.redis",
        "repository.reservation.redis",
        "repository.payment.redis",
    ):
        monkeypatch.setattr(f"{module}.redis_client", redis)
    return redis
