import logging

from core.config import get_settings
from core.db.postgresql import init_models
from core.kafka import KafkaProducer
from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from routes.genre import router as genre_router

# Configured at import time, not inside __main__ — uvicorn imports this
# module directly, so a __main__-guarded config would never run.
_settings = get_settings()
logging.basicConfig(level=_settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_models()
    async with KafkaProducer() as producer:
        app.state.kafka_producer = producer
        yield


app = FastAPI(title="Movie API", lifespan=lifespan)
app.include_router(genre_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=_settings.movie_api_port, reload=True)
