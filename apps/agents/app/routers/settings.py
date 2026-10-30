from fastapi import APIRouter, Depends, HTTPException
from pymongo.asynchronous.database import AsyncDatabase

from app.deps import get_db
from app.models.api import ApiKeySet, LlmSettings, Provider, ProviderChoice, ProviderStatus
from app.services import api_keys

router = APIRouter(prefix="/settings/llm", tags=["settings"])
# shortcut: the API has no auth yet, so anyone who can reach it can replace a key (never read one); add auth before
# exposing the API beyond localhost


async def _status(db: AsyncDatabase) -> LlmSettings:
    return LlmSettings(active=await api_keys.active(db), providers=[
        ProviderStatus(id=p, name=api_keys.NAMES[p], source=await api_keys.source(db, p)) for p in api_keys.PROVIDERS])


@router.get("", response_model=LlmSettings)
async def llm_settings(db: AsyncDatabase = Depends(get_db)):
    return await _status(db)


@router.put("/{provider}/key", response_model=LlmSettings)
async def set_key(provider: Provider, body: ApiKeySet, db: AsyncDatabase = Depends(get_db)):
    """Check the key with the provider (no tokens spent), save it and switch the agents to that provider; they use it
    from their next step."""
    key = body.api_key.get_secret_value().strip()
    try:
        await api_keys.verify(provider, key)
    except api_keys.InvalidKey as e:
        raise HTTPException(400, str(e)) from e
    await api_keys.save(db, provider, key)
    return await _status(db)


@router.delete("/{provider}/key", response_model=LlmSettings)
async def remove_key(provider: Provider, db: AsyncDatabase = Depends(get_db)):
    await api_keys.clear(db, provider)
    return await _status(db)


@router.put("/active", response_model=LlmSettings)
async def set_active(body: ProviderChoice, db: AsyncDatabase = Depends(get_db)):
    """Switch the agents to another provider that already has a key."""
    if await api_keys.source(db, body.provider) is None:
        raise HTTPException(409, f"Add an {api_keys.NAMES[body.provider]} API key first")
    await api_keys.choose(db, body.provider)
    return await _status(db)
