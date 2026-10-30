"""llm.complete on OpenAI's Responses API, against a fake HTTP transport (never the real API)."""
import json

import httpx
import pytest
from bullmq import UnrecoverableError

from app.agents.research import Candidates
from app.services import llm, progress

KEY = "sk-proj-" + "k" * 40


@pytest.fixture
def openai(monkeypatch):
    """Route llm's OpenAI calls to `reply`; returns the list of request bodies sent."""
    sent, reply = [], {}
    real = httpx.AsyncClient

    def handler(req: httpx.Request):
        assert req.headers["authorization"] == f"Bearer {KEY}"
        sent.append(json.loads(req.content))
        return reply["fn"](req)
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler)))
    token = llm.credentials.set(("openai", KEY))
    yield sent, reply
    llm.credentials.reset(token)


def ok(text, **extra):
    return lambda req: httpx.Response(200, json={"status": "completed", "usage": {"input_tokens": 7, "output_tokens": 3},
                                                 "output": [*extra.get("before", []), {"type": "message", "content": [
                                                     {"type": "output_text", "text": text}]}]})


async def test_schema_call_with_web_search_reports_queries_and_parses(openai):
    sent, reply = openai
    data = {"candidates": [{"objective_id": "o1", "url": "https://sec.gov/x", "title": "10-Q", "kind": "primary"}]}
    reply["fn"] = ok(json.dumps(data), before=[{"type": "web_search_call", "action": {"type": "search", "query": "nvidia 10-q"}}])
    seen = []

    async def sink(phase, detail, data):
        seen.append(detail)
    t = progress.sink.set(sink)
    try:
        c = await llm.complete("research", "find", system="sys", schema=Candidates.model_json_schema(),
                               tools=["WebSearch"], max_turns=5)
    finally:
        progress.sink.reset(t)
    assert c.data == data and c.usage == {"input_tokens": 7, "output_tokens": 3}
    assert seen == ["WebSearch: nvidia 10-q"]
    body = sent[0]
    assert body["model"] == llm.OPENAI_MODELS["research"] and body["instructions"] == "sys" and body["store"] is False
    assert body["tools"] == [{"type": "web_search"}] and body["max_tool_calls"] == 5
    fmt = body["text"]["format"]
    assert fmt["strict"] is True and fmt["schema"]["additionalProperties"] is False
    assert "title" in fmt["schema"]["$defs"]["Candidate"]["properties"]  # a field named title survives
    assert "pattern" not in json.dumps(fmt["schema"])


async def test_no_thinking_asks_for_low_effort_and_plain_text(openai):
    sent, reply = openai
    reply["fn"] = ok("# Report")
    c = await llm.complete("critic", "p", system="s", think=False)
    assert c.text == "# Report" and c.data is None
    assert sent[0]["reasoning"] == {"effort": "low"} and "text" not in sent[0] and "tools" not in sent[0]


@pytest.mark.parametrize("status,body,headers,exc", [
    (429, {"error": {"code": "rate_limit_exceeded", "message": "slow down"}}, {"retry-after": "2"}, llm.RateLimited),
    (429, {"error": {"code": "insufficient_quota", "message": "no credit"}}, {}, UnrecoverableError),
    (401, {"error": {"message": "bad key"}}, {}, UnrecoverableError),
    (503, {"error": {"message": "overloaded"}}, {}, RuntimeError),
])
async def test_errors_are_mapped(openai, status, body, headers, exc):
    _, reply = openai
    reply["fn"] = lambda req: httpx.Response(status, json=body, headers=headers)
    with pytest.raises(exc) as e:
        await llm.complete("write", "p", system="s")
    if exc is llm.RateLimited:
        assert e.value.retry_after_ms == 2000


async def test_refusal_bad_json_and_unknown_tools_fail(openai):
    _, reply = openai
    reply["fn"] = lambda req: httpx.Response(200, json={"status": "completed", "output": [
        {"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]})
    with pytest.raises(RuntimeError, match="refused"):
        await llm.complete("write", "p", system="s")
    reply["fn"] = ok("not json")
    with pytest.raises(RuntimeError, match="structured"):
        await llm.complete("supervisor", "p", system="s", schema={"type": "object"})
    with pytest.raises(UnrecoverableError):
        await llm.complete("research", "p", system="s", tools=["WebFetch"])
