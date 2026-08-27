import logging

from core.db.postgresql import get_session
from core.db.redis import get_redis
from core.response import APIResponse, EResponse, SResponse
from fastapi import APIRouter, Depends, Response
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/health", response_model=APIResponse[dict])
async def healthz(
    response: Response,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> APIResponse:
    checks = {"movie-api": "ok", "postgres": "ok", "redis": "ok"}
    healthy = True

    try:
        await session.execute(text("SELECT 1"))
        logger.debug("Postgres health check passed")
    except OperationalError:
        checks["postgres"] = "unreachable"
        healthy = False
        logger.error("Postgres health check failed", exc_info=True)
    except Exception:
        checks["postgres"] = "unreachable"
        healthy = False
        logger.error("Postgres health check failed", exc_info=True)

    try:
        await redis.ping()
        logger.debug("Redis health check passed")
    except RedisError:
        checks["redis"] = "unreachable"
        healthy = False
        logger.error("Redis health check failed", exc_info=True)
    except Exception:
        checks["redis"] = "unreachable"
        healthy = False
        logger.error("Redis health check failed", exc_info=True)

    if healthy:
        return SResponse(data=checks, message="Service is healthy")

    response.status_code = 503
    return EResponse(data=checks, message="Service is unhealthy", status=503)
