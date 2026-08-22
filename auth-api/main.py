import logging

from core.config import get_settings
from core.kafka import KafkaProducer
from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from routes.health import router as health_router
from routes.user import router as user_router

# Configured at import time, not inside __main__ — uvicorn imports this
# module directly, so a __main__-guarded config would never run.
_settings = get_settings()
logging.basicConfig(level=_settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    producer = KafkaProducer()
    await producer.start()
    app.state.kafka_producer = producer
    try:
        yield
    finally:
        await producer.stop()


app = FastAPI(title="Auth API", lifespan=lifespan)
app.include_router(health_router)
app.include_router(user_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=_settings.auth_api_port, reload=True)
