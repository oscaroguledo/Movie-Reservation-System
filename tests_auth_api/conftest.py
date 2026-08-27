import pytest


@pytest.fixture(autouse=True)
def reset_rate_limiters():
    """The rate limiters are module-level singletons shared across every
    test in this process, so each test starts with a clean hit count."""
    from routes.user import login_rate_limiter

    login_rate_limiter.reset()
    yield
    login_rate_limiter.reset()
