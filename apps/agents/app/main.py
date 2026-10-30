from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

import config
from app.routers import artifacts, connectors, dlq, queues, settings, workflows
from app.services import state


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = state.connect()
    app.state.db = client[config.MONGO_DB]
    await state.ensure_indexes(app.state.db)
    app.state.redis = Redis.from_url(config.REDIS_URL)  # pub/sub for WebSocket events
    yield
    await app.state.redis.aclose()
    await client.close()


app = FastAPI(title="Retro", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.WEB_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.include_router(workflows.router)
app.include_router(queues.router)
app.include_router(dlq.router)
app.include_router(artifacts.router)
app.include_router(connectors.router)
app.include_router(settings.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
