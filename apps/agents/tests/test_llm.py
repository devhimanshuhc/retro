import time

import pytest
from bullmq import UnrecoverableError
from claude_agent_sdk import (AssistantMessage, CLINotFoundError, RateLimitEvent, RateLimitInfo, ResultError,
                              ResultMessage)

from app.services import llm


def result(**kw):
    return ResultMessage(**{"subtype": "success", "duration_ms": 1, "duration_api_ms": 1, "is_error": False,
                            "num_turns": 1, "session_id": "s", **kw})


def fake_query(monkeypatch, *messages, raises=None):
    seen = {}

    async def q(prompt, options):
        seen["options"] = options
        for m in messages:
            yield m
        if raises:
            raise raises

    monkeypatch.setattr(llm, "query", q)
    return seen


async def test_success_returns_text_data_and_usage(monkeypatch):
    seen = fake_query(monkeypatch, result(result="hi", structured_output={"a": 1},
                                          usage={"input_tokens": 3, "output_tokens": 4, "cache_read_input_tokens": 9}))
    r = await llm.complete("critic", "p", system="s", schema={"type": "object"}, think=False)
    assert (r.text, r.data, r.usage) == ("hi", {"a": 1}, {"input_tokens": 12, "output_tokens": 4})
    o = seen["options"]
    assert o.model == llm.MODELS["critic"] and o.tools == [] and o.setting_sources == []
    assert o.thinking == {"type": "disabled"}  # thinking was ~90% of the critic's output tokens


@pytest.mark.parametrize("status, exc", [
    (429, llm.RateLimited), (529, RuntimeError), (500, RuntimeError), (408, RuntimeError), (None, RuntimeError),
    (400, UnrecoverableError), (401, UnrecoverableError),
])
async def test_error_result_is_mapped(monkeypatch, status, exc):
    fake_query(monkeypatch, result(is_error=True, subtype="error_during_execution", api_error_status=status))
    with pytest.raises(exc):
        await llm.complete("research", "p", system="s")


async def test_raised_result_error_is_mapped(monkeypatch):
    fake_query(monkeypatch, raises=ResultError("x", {"api_error_status": 429}))
    with pytest.raises(llm.RateLimited):
        await llm.complete("research", "p", system="s")


@pytest.mark.parametrize("error, exc", [("rate_limit", llm.RateLimited), ("authentication_failed", UnrecoverableError)])
async def test_assistant_error_is_mapped(monkeypatch, error, exc):
    fake_query(monkeypatch, AssistantMessage(content=[], model="m", error=error))
    with pytest.raises(exc):
        await llm.complete("research", "p", system="s")


async def test_missing_cli_is_unrecoverable(monkeypatch):
    fake_query(monkeypatch, raises=CLINotFoundError())
    with pytest.raises(UnrecoverableError):
        await llm.complete("research", "p", system="s")


async def test_schema_without_structured_output_retries(monkeypatch):
    fake_query(monkeypatch, result(result="not json"))
    with pytest.raises(RuntimeError):
        await llm.complete("critic", "p", system="s", schema={"type": "object"})


async def test_rate_limit_carries_reset_time(monkeypatch):
    info = RateLimitInfo(status="rejected", resets_at=int(time.time()) + 60)
    fake_query(monkeypatch, RateLimitEvent(rate_limit_info=info, uuid="u", session_id="s"),
               AssistantMessage(content=[], model="m", error="rate_limit"))
    with pytest.raises(llm.RateLimited) as e:
        await llm.complete("research", "p", system="s")
    assert 55_000 < e.value.retry_after_ms <= 60_000


async def test_tool_calls_are_reported_as_progress(monkeypatch):
    from claude_agent_sdk import ToolUseBlock

    from app.services import progress
    got = []

    async def sink(phase, detail, data):
        got.append((phase, detail, data))
    fake_query(monkeypatch, AssistantMessage(content=[ToolUseBlock(id="t", name="WebSearch", input={"query": "nvidia q3"})],
                                             model="m"), result(result="ok"))
    token = progress.sink.set(sink)
    try:
        await llm.complete("research", "p", system="s", tools=["WebSearch"])
    finally:
        progress.sink.reset(token)
    assert got == [("tool", "WebSearch: nvidia q3", {"tool": "WebSearch"})]


async def test_no_provider_key_fails_without_retry(monkeypatch):
    seen = fake_query(monkeypatch, result(result="never"))
    token = llm.credentials.set((None, None))
    try:
        with pytest.raises(UnrecoverableError, match="No model API key"):
            await llm.complete("writer", "p", system="s")
    finally:
        llm.credentials.reset(token)
    assert "options" not in seen  # no model call was made
