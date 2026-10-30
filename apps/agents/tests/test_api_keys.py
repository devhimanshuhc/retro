import httpx
import pytest

import config
from app.services import api_keys, dlq

ANT = "sk-ant-api03-" + "x" * 40
OAI = "sk-proj-" + "y" * 40


@pytest.fixture
def no_keys(monkeypatch):
    monkeypatch.setattr(config, "USE_CLAUDE_LOGIN", False)
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")


@pytest.fixture
def accept(monkeypatch):
    async def ok(p, key, client=None):
        assert key in (ANT, OAI)
    monkeypatch.setattr(api_keys, "verify", ok)


async def test_no_key_blocks_runs_until_one_is_saved(api, db, no_keys, accept):
    s = (await api.get("/settings/llm")).json()
    assert s["active"] is None and [p["source"] for p in s["providers"]] == [None, None]
    r = await api.post("/workflows", json={"prompt": "Nvidia earnings"})
    assert r.status_code == 409 and "API key" in r.json()["detail"]

    r = await api.put("/settings/llm/openai/key", json={"api_key": f"  {OAI} "})
    assert r.json()["active"] == "openai" and OAI not in r.text
    assert await api_keys.credentials(db) == ("openai", OAI)
    assert (await api.post("/workflows", json={"prompt": "Nvidia earnings"})).status_code == 202


async def test_saving_a_key_switches_provider_and_removing_falls_back(api, db, no_keys, accept):
    await api.put("/settings/llm/openai/key", json={"api_key": OAI})
    assert (await api.put("/settings/llm/anthropic/key", json={"api_key": ANT})).json()["active"] == "anthropic"
    assert (await api.put("/settings/llm/active", json={"provider": "openai"})).json()["active"] == "openai"
    assert (await api.delete("/settings/llm/openai/key")).json()["active"] == "anthropic"
    assert (await api.delete("/settings/llm/anthropic/key")).json()["active"] is None
    r = await api.put("/settings/llm/active", json={"provider": "openai"})
    assert r.status_code == 409


async def test_a_wrong_key_is_not_saved_and_not_echoed(api, db, no_keys):
    for provider, key in [("anthropic", "sk-ant-oat01-" + "y" * 40), ("openai", ANT), ("anthropic", "short")]:
        r = await api.put(f"/settings/llm/{provider}/key", json={"api_key": key})
        assert r.status_code == 400 and key not in r.text
    assert (await api.put("/settings/llm/gemini/key", json={"api_key": OAI})).status_code == 422
    assert await api_keys.active(db) is None


@pytest.mark.parametrize("provider,key,header", [("anthropic", ANT, "x-api-key"), ("openai", OAI, "authorization")])
@pytest.mark.parametrize("status,ok", [(200, True), (401, False), (500, False)])
async def test_verify_asks_the_provider(provider, key, header, status, ok):
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"] = req.headers[header]
        return httpx.Response(status, json={})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        if ok:
            await api_keys.verify(provider, key, c)
        else:
            with pytest.raises(api_keys.InvalidKey):
                await api_keys.verify(provider, key, c)
    assert key in seen["auth"]


async def test_env_keys_and_login_count_and_the_app_key_wins(db, no_keys, monkeypatch):
    monkeypatch.setattr(config, "USE_CLAUDE_LOGIN", True)
    assert await api_keys.credentials(db) == ("anthropic", None)
    monkeypatch.setattr(config, "USE_CLAUDE_LOGIN", False)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-env-openai")
    assert await api_keys.credentials(db) == ("openai", None)  # env key: llm reads it from config
    await api_keys.save(db, "anthropic", ANT)
    assert await api_keys.credentials(db) == ("anthropic", ANT)


def test_dead_letters_redact_any_provider_key():
    assert dlq.redact(f"auth failed for {ANT} and {OAI}.") == "auth failed for [redacted] and [redacted]."
