from uuid import uuid4

import pytest
import httpx
from fastapi.testclient import TestClient

from redis.asyncio import Redis

import config
from app.deps import get_db, get_prefix, get_redis
from app.main import app
from app.services import scholar, state


@pytest.fixture(autouse=True)
def no_real_browser(monkeypatch):
    """Tests never launch Chromium or reach the network; tests of the fallback switch it back on with a fake."""
    monkeypatch.setattr(config, "BROWSER_FALLBACK", False)
    monkeypatch.setattr(config, "USE_CLAUDE_LOGIN", True)  # runs may start; test_claude_key switches it off

    async def no_papers(question, client, **kw):  # OpenAlex is a network call too
        return []
    monkeypatch.setattr(scholar, "search", no_papers)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def db():
    # Real Mongo (docker compose), throwaway database per test
    mongo = state.connect()
    name = f"test_{uuid4().hex}"
    yield mongo[name]
    await mongo.drop_database(name)
    await mongo.close()


@pytest.fixture
def prefix():
    # Throwaway Redis key prefix per test, so tests never touch the real queues
    return f"test-{uuid4().hex}"


@pytest.fixture
async def api(db, prefix):
    """Async client for the API against the throwaway Mongo db and Redis prefix (no lifespan, so no real db)."""
    redis = Redis.from_url(config.REDIS_URL)
    app.dependency_overrides = {get_db: lambda: db, get_prefix: lambda: prefix, get_redis: lambda: redis}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c
    app.dependency_overrides = {}
    await redis.aclose()
