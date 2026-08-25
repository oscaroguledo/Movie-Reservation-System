import pytest
from core.config import get_settings
from core.db.redis import get_redis, redis_client
from redis.asyncio import Redis


def test_redis_client_is_configured_from_settings():
    settings = get_settings()

    assert isinstance(redis_client, Redis)
    assert str(redis_client.connection_pool.connection_kwargs["db"]) == settings.redis_url.rsplit("/", 1)[-1]


async def test_get_redis_yields_the_shared_client():
    agen = get_redis()
    client = await agen.__anext__()

    assert client is redis_client

    with pytest.raises(StopAsyncIteration):
        await agen.__anext__()
