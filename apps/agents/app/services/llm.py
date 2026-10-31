"""The one place that calls a model. Anthropic runs on the Claude Agent SDK (the bundled Claude Code CLI); OpenAI on its
Responses API. The provider and key come per job from `credentials`, which the actor sets (services/api_keys.py).

Anthropic auth: the key saved in the web app, else ANTHROPIC_API_KEY, else (only with USE_CLAUDE_LOGIN=1, personal
development) the local Claude login. OpenAI: the saved key, else OPENAI_API_KEY.
"""
import json
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

import httpx
from bullmq import UnrecoverableError
from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKError, CLINotFoundError,
                              RateLimitEvent, ResultError, ResultMessage, ServerToolUseBlock, ToolUseBlock, query)

import config
from app.services import progress

MODELS = {"router": config.ROUTER_MODEL, "supervisor": config.SUPERVISOR_MODEL, "research": config.RESEARCH_MODEL,
          "write": config.WRITER_MODEL, "critic": config.CRITIC_MODEL}
IN_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")  # the CLI caches prompts
OPENAI_MODELS = {"router": config.OPENAI_ROUTER_MODEL, "supervisor": config.OPENAI_SUPERVISOR_MODEL, "research": config.OPENAI_RESEARCH_MODEL,
                 "write": config.OPENAI_WRITER_MODEL, "critic": config.OPENAI_CRITIC_MODEL}
OPENAI_URL = "https://api.openai.com/v1/responses"
OPENAI_TOOLS = {"WebSearch": {"type": "web_search"}}
# Validation keywords left out of OpenAI's strict schemas (not all are accepted there); pydantic checks every result
LOOSE = {"title", "minLength", "maxLength", "pattern", "minItems", "maxItems", "minimum", "maximum", "default"}
NO_KEY = "No model API key: add an Anthropic or OpenAI API key in Connectors, then replay"
FATAL = ("authentication_failed", "billing_error", "invalid_request")
# The last output complete() received in this job (each BullMQ job runs in its own task), kept for dead-letter traces
last_output: ContextVar[str | None] = ContextVar("last_output", default=None)
# (provider, key saved in the web app) for this job, set by the actor; a None key = the env's key (or the local login)
credentials: ContextVar[tuple[str | None, str | None]] = ContextVar("credentials", default=("anthropic", None))


class RateLimited(Exception):
    """429: the actor pauses its whole queue for retry_after_ms (None = unknown), then the job retries."""

    def __init__(self, detail: str, retry_after_ms: int | None = None):
        super().__init__(detail)
        self.retry_after_ms = retry_after_ms


@dataclass
class Completion:
    text: str
    data: Any = None  # parsed JSON when a schema was given
    usage: dict = field(default_factory=dict)  # {input_tokens, output_tokens}


def _fail(status: int | None, detail: str, retry_after_ms: int | None = None):
    if status == 429:
        raise RateLimited(detail, retry_after_ms)
    if status is not None and 400 <= status < 500 and status != 408:
        raise UnrecoverableError(f"LLM {status}: {detail}")  # bad request or auth: retrying won't help
    raise RuntimeError(f"LLM error {status}: {detail}")  # 5xx, overloaded, timeouts: BullMQ retries


async def complete(agent: str, prompt: str, *, system: str, schema: dict | None = None,
                   tools: list[str] = (), max_turns: int = 3, think: bool = True) -> Completion:
    provider, key = credentials.get()
    if provider is None:
        raise UnrecoverableError(NO_KEY)  # the key was removed after the run started; retrying can't help
    if provider == "openai":
        return await _openai(agent, prompt, system=system, schema=schema, tools=tools, max_turns=max_turns,
                             think=think, key=key or config.OPENAI_API_KEY)
    options = ClaudeAgentOptions(
        model=MODELS[agent], system_prompt=system,
        tools=list(tools), allowed_tools=list(tools),  # no tools unless asked; never a file or shell tool
        setting_sources=[],  # don't load this repo's CLAUDE.md, skills or settings into the agent
        # No MCP servers at all: without these the CLI loads the logged-in user's claude.ai connectors (Docs, Gmail,
        # Drive, ...) and a research call once invoked one. Agents must never reach the user's accounts.
        mcp_servers={}, strict_mcp_config=True,
        env={"ENABLE_CLAUDEAI_MCP_SERVERS": "false", **({"ANTHROPIC_API_KEY": key} if key else {})},
        max_turns=max_turns,
        output_format={"type": "json_schema", "schema": schema} if schema else None,
        thinking=None if think else {"type": "disabled"},  # None = the CLI default, which thinks (most of the output tokens)
    )
    res = None
    retry_after = None  # ms until the limit resets, when the CLI reports it
    try:
        async for m in query(prompt=prompt, options=options):
            if isinstance(m, RateLimitEvent) and m.rate_limit_info.status == "rejected" and m.rate_limit_info.resets_at:
                retry_after = max(0, int((m.rate_limit_info.resets_at - time.time()) * 1000))
            if isinstance(m, AssistantMessage) and m.error in FATAL:
                raise UnrecoverableError(f"LLM {m.error}")
            if isinstance(m, AssistantMessage) and m.error == "rate_limit":
                raise RateLimited("rate_limit", retry_after)
            if isinstance(m, AssistantMessage):
                for b in m.content:  # show each tool call live, e.g. the web searches research runs
                    if isinstance(b, ToolUseBlock) and b.name not in (*tools, "StructuredOutput"):
                        # a tool it wasn't given (e.g. a user's connector): stop the call rather than let it run
                        raise RuntimeError(f"model tried to use a tool it wasn't given: {b.name}")
                    if isinstance(b, (ToolUseBlock, ServerToolUseBlock)) and b.name != "StructuredOutput":  # internal
                        arg = (b.input or {}).get("query") or (b.input or {}).get("url") or ""
                        await progress.report("tool", f"{b.name}: {arg}".rstrip(": "), tool=b.name)
            if isinstance(m, ResultMessage):
                res = m  # keep reading so the CLI stream closes cleanly
    except ResultError as e:
        _fail(e.api_error_status, e.result or e.subtype or str(e), retry_after)
    except CLINotFoundError as e:
        raise UnrecoverableError(str(e)) from e
    except ClaudeSDKError as e:
        raise RuntimeError(str(e)) from e
    if res is None:
        raise RuntimeError("LLM returned no result")
    last_output.set(res.result if res.structured_output is None else json.dumps(res.structured_output))
    if res.is_error:
        _fail(res.api_error_status, res.result or res.subtype, retry_after)
    if schema and res.structured_output is None:
        raise RuntimeError(f"no structured output ({res.subtype})")
    u = res.usage or {}
    return Completion(res.result or "", res.structured_output,
                      {"input_tokens": sum(u.get(k) or 0 for k in IN_KEYS), "output_tokens": u.get("output_tokens") or 0})


def strict_schema(s: Any) -> Any:
    """A pydantic JSON schema as OpenAI's strict mode wants it: every object closed, validation keywords dropped."""
    if isinstance(s, list):
        return [strict_schema(v) for v in s]
    if not isinstance(s, dict):
        return s
    out = {k: ({n: strict_schema(d) for n, d in v.items()} if k in ("properties", "$defs") else strict_schema(v))
           for k, v in s.items() if k not in LOOSE}  # property names are kept: only keywords are dropped
    if out.get("type") == "object":
        out["additionalProperties"] = False
    return out


async def _openai(agent: str, prompt: str, *, system: str, schema: dict | None, tools: list[str], max_turns: int,
                  think: bool, key: str) -> Completion:
    """The same call on OpenAI's Responses API: web search is OpenAI's own tool, the schema is enforced strictly."""
    if unknown := set(tools) - OPENAI_TOOLS.keys():
        raise UnrecoverableError(f"no OpenAI equivalent for tools {sorted(unknown)}")
    body: dict[str, Any] = {"model": OPENAI_MODELS[agent], "instructions": system, "input": prompt, "store": False}
    if tools:
        body |= {"tools": [OPENAI_TOOLS[t] for t in tools], "max_tool_calls": max_turns}
    if schema:
        body["text"] = {"format": {"type": "json_schema", "name": "output", "schema": strict_schema(schema), "strict": True}}
    if not think:
        body["reasoning"] = {"effort": "low"}  # the lowest every current model accepts
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            r = await client.post(OPENAI_URL, json=body, headers={"authorization": f"Bearer {key}"})
    except httpx.HTTPError as e:
        raise RuntimeError(f"OpenAI unreachable: {type(e).__name__}") from e
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200:
        err = data.get("error") or {}
        if err.get("code") == "insufficient_quota":  # a 429 that waiting won't fix
            raise UnrecoverableError(f"LLM 429: {err.get('message', 'insufficient quota')}")
        retry = r.headers.get("retry-after")
        _fail(r.status_code, err.get("message") or r.text[:300],
              int(float(retry) * 1000) if retry and retry.replace(".", "", 1).isdigit() else None)
    text, refusal = "", None
    for item in data.get("output") or []:
        if item.get("type") == "web_search_call":
            q = (item.get("action") or {}).get("query") or ""
            await progress.report("tool", f"WebSearch: {q}".rstrip(": "), tool="WebSearch")
        for part in (item.get("content") or []) if item.get("type") == "message" else []:
            text += part.get("text", "") if part.get("type") == "output_text" else ""
            refusal = part.get("refusal") if part.get("type") == "refusal" else refusal
    last_output.set(text or refusal)
    if refusal:
        raise RuntimeError(f"model refused: {refusal[:200]}")
    if data.get("status") != "completed":
        raise RuntimeError(f"OpenAI response {data.get('status')}: {data.get('incomplete_details')}")
    parsed = None
    if schema:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise RuntimeError("no structured output") from e
    u = data.get("usage") or {}
    return Completion(text, parsed, {"input_tokens": u.get("input_tokens") or 0, "output_tokens": u.get("output_tokens") or 0})
