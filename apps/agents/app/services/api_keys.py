"""The model provider the agents use (Anthropic or OpenAI) and its API key: pasted in the web app (stored in Mongo)
or set in the env (ANTHROPIC_API_KEY / OPENAI_API_KEY).

Only API keys. Anthropic doesn't let apps built on the Agent SDK offer claude.ai (subscription) login to their users,
so the app never asks for one. USE_CLAUDE_LOGIN=1 lets a developer run on their own local login, for personal use.
Keys never leave the backend: the API only says which providers have one and where it came from.
"""
from typing import Literal, get_args

import httpx
from pymongo.asynchronous.database import AsyncDatabase

import config
from app.models.run import now

Provider = Literal["anthropic", "openai"]
Source = Literal["app", "env", "login"]
PROVIDERS: tuple[Provider, ...] = get_args(Provider)
NAMES = {"anthropic": "Anthropic", "openai": "OpenAI"}
CHOICE = "provider"  # the settings doc holding the provider picked last


class InvalidKey(Exception):
    pass


def _settings(db: AsyncDatabase):
    return db["settings"]


def _env(p: Provider) -> str:
    return config.ANTHROPIC_API_KEY if p == "anthropic" else config.OPENAI_API_KEY


async def stored(db: AsyncDatabase, p: Provider) -> str | None:
    doc = await _settings(db).find_one({"_id": p})
    return doc.get("api_key") if doc else None


async def source(db: AsyncDatabase, p: Provider) -> Source | None:
    """Where this provider's key comes from: one saved in the app wins over the env; None = no key."""
    if await stored(db, p):
        return "app"
    if _env(p):
        return "env"
    return "login" if p == "anthropic" and config.USE_CLAUDE_LOGIN else None


async def active(db: AsyncDatabase) -> Provider | None:
    """The provider the agents use: the one picked last (saving a key picks it) while it has a key, else the first
    provider that has one. None = runs can't start."""
    doc = await _settings(db).find_one({"_id": CHOICE})
    for p in ([doc["value"]] if doc else []) + list(PROVIDERS):
        if await source(db, p):
            return p
    return None


async def credentials(db: AsyncDatabase) -> tuple[Provider | None, str | None]:
    """(provider, key saved in the app) for one job; a None key means the env's key (or the local login)."""
    p = await active(db)
    return p, await stored(db, p) if p else None


async def verify(p: Provider, key: str, client: httpx.AsyncClient | None = None) -> None:
    """Ask the provider whether the key works (lists models: no tokens spent). Raises InvalidKey with a reason."""
    ok = key.startswith("sk-ant-api") if p == "anthropic" else key.startswith("sk-") and not key.startswith("sk-ant-")
    if not ok or not 20 <= len(key) <= 300:
        raise InvalidKey(f"That isn't an {NAMES[p]} API key: they start with "
                         + ("sk-ant-api" if p == "anthropic" else "sk- (sk-proj- for project keys)"))
    if p == "anthropic":
        url, headers = "https://api.anthropic.com/v1/models", {"x-api-key": key, "anthropic-version": "2023-06-01"}
    else:
        url, headers = "https://api.openai.com/v1/models", {"authorization": f"Bearer {key}"}
    own = client is None
    client = client or httpx.AsyncClient(timeout=15)
    try:
        r = await client.get(url, params={"limit": 1}, headers=headers)
    except httpx.HTTPError as e:
        raise InvalidKey(f"Couldn't reach {NAMES[p]} to check the key; try again") from e
    finally:
        if own:
            await client.aclose()
    if r.status_code in (401, 403):
        raise InvalidKey(f"{NAMES[p]} rejected this key: check it and paste it again")
    if r.status_code != 200:
        raise InvalidKey(f"{NAMES[p]} couldn't check the key right now (HTTP {r.status_code}); try again")


async def save(db: AsyncDatabase, p: Provider, key: str) -> None:
    """Store the key and switch the agents to this provider."""
    # shortcut: stored as plain text in the local Mongo (reachable only from this machine); encrypt it at rest
    # before the database is ever shared or hosted
    await _settings(db).update_one({"_id": p}, {"$set": {"api_key": key, "updated_at": now()}}, upsert=True)
    await choose(db, p)


async def choose(db: AsyncDatabase, p: Provider) -> None:
    await _settings(db).update_one({"_id": CHOICE}, {"$set": {"value": p, "updated_at": now()}}, upsert=True)


async def clear(db: AsyncDatabase, p: Provider) -> None:
    await _settings(db).delete_one({"_id": p})
