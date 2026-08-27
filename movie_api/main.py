import logging

from core.config import get_settings
from core.kafka import KafkaProducer
from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from routes.genre import router as genre_router
from routes.health import router as health_router
from routes.movie import router as movie_router
from routes.payment import router as payment_router
from routes.report import router as report_router
from routes.reservation import router as reservation_router
from routes.screening import router as screening_router
from routes.showroom import router as showroom_router

# Configured at import time, not inside __main__ — uvicorn imports this
# module directly, so a __main__-guarded config would never run.
_settings = get_settings()
logging.basicConfig(level=_settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is owned by Alembic migrations (see migrations/), applied by
    # the movie-migrate service before this container starts — not here.
    async with KafkaProducer() as producer:
        app.state.kafka_producer = producer
        yield


app = FastAPI(title="Movie API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in _settings.cors_allowed_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(genre_router)
app.include_router(movie_router)
app.include_router(showroom_router)
app.include_router(screening_router)
app.include_router(reservation_router)
app.include_router(payment_router)
app.include_router(report_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=_settings.movie_api_port, reload=True)
