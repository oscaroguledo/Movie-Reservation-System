import logging

from core.config import get_settings
from core.db.postgresql import init_models
from core.kafka import KafkaProducer
from core.seed import seed_initial_admin
from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from routes.health import router as health_router
from routes.user import router as user_router

# Configured at import time, not inside __main__ — uvicorn imports this
# module directly, so a __main__-guarded config would never run.
_settings = get_settings()
logging.basicConfig(level=_settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_models()
    await seed_initial_admin()
    producer = KafkaProducer()
    await producer.start()
    app.state.kafka_producer = producer
    try:
        yield
    finally:
        await producer.stop()


app = FastAPI(title="Auth API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in _settings.cors_allowed_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(user_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=_settings.auth_api_port, reload=True)
