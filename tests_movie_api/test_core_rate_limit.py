from unittest.mock import MagicMock

import pytest
from core.rate_limit import RateLimiter
from fastapi import HTTPException


def make_request(host: str = "1.2.3.4"):
    request = MagicMock()
    request.client.host = host
    return request


class TestRateLimiter:
    async def test_allows_requests_under_the_limit(self, fake_redis):
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        request = make_request()

        await limiter(request)
        await limiter(request)

    async def test_rejects_the_request_that_exceeds_the_limit(self, fake_redis):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        request = make_request()
        await limiter(request)

        with pytest.raises(HTTPException) as exc_info:
            await limiter(request)

        assert exc_info.value.status_code == 429

    async def test_tracks_each_client_separately(self, fake_redis):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        await limiter(make_request("1.1.1.1"))

        await limiter(make_request("2.2.2.2"))

    async def test_falls_back_to_unknown_when_client_is_absent(self, fake_redis):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        request = MagicMock()
        request.client = None

        await limiter(request)

    async def test_reset_clears_recorded_hits(self, fake_redis):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        request = make_request()
        await limiter(request)

        limiter.reset()

        await limiter(request)

    async def test_old_hits_fall_outside_the_window(self, fake_redis):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        request = make_request()
        await limiter(request)
        limiter._hits[request.client.host][0] -= 61

        await limiter(request)
