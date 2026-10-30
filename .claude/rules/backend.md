---
paths:
  - "apps/agents/**"
---

# Backend rules (apps/agents)

## Folder plan (follows the team's FastAPI template)
```
apps/agents/              # ALL Python: API + actors (follows the team's FastAPI template)
├── Dockerfile       # (step 22) one image; compose `command` picks API or which agent
├── .env / .env.example
├── config.py        # env settings (Redis, Mongo, models, MAX_REVISIONS, WEB_ORIGINS)
├── pyproject.toml   # deps, managed by uv
├── uv.lock
├── pytest.ini
├── app/
│   ├── main.py      # FastAPI app, CORS for apps/web, includes the routers
│   ├── routers/     # HTTP/WS routes ONLY (not the AI agents)
│   │   ├── workflows.py   # POST /workflows, GET /workflows/{id}, WS /workflows/{id}/events
│   │   ├── queues.py      # GET /queues: job counts per agent queue
│   │   └── dlq.py         # list + replay dead letters
│   ├── models/      # pydantic schemas: run doc, queue messages, events, plan, report, critique
│   ├── services/    # shared infrastructure used by API and agents
│   │   ├── state.py       # Mongo workflow_runs + dead_letters
│   │   ├── queues.py      # queue names, default job opts, enqueue helper
│   │   ├── events.py      # Redis pub/sub publish/subscribe
│   │   └── llm.py         # complete(): Agent SDK call, model per agent, error mapping
│   └── agents/      # the actors; each runs as its own process
│       ├── base.py        # Actor (claim → handler → save outputs+done+next hop → send), Outcome, main(); DLQ in step 15
│       ├── supervisor.py  # `python -m app.agents.supervisor`
│       ├── research.py
│       ├── writer.py
│       └── critic.py
├── scripts/
│   ├── dev_server.py      # uvicorn with reload
│   └── prod_server.py     # uvicorn for production
└── tests/
├── conftest.py
└── test_*.py
```
`app/agents/` is the one addition to the template. Agents import from `services/` and `models/`, never from each other or from `routers/`.

### Resilience rules
- Every job: `attempts: 3`, `backoff: {type: "exponential", delay: 2000}`.
- Retryable errors (429, 5xx, timeouts) → raise normally so BullMQ retries.
- Non-retryable errors (bad input, auth) → raise `bullmq.UnrecoverableError`.
- On a 429, `Actor` pauses its own queue with `queue.rateLimit(ms)` (reset time from `RateLimited.retry_after_ms`, else `RATE_LIMIT_PAUSE_MS`) so every worker of that agent backs off together, then re-raises so the job retries. Workers must keep the `limiter` option in `Actor.run`: without it BullMQ ignores the pause.
- A retry restarts the step from clean, durable inputs in Mongo, never from the failed attempt's partial output.
- **Dead-letter queue**: `Actor._job` (the BullMQ processor) dead-letters a job on its last attempt or an `UnrecoverableError`, before re-raising: `services/dlq.dead_letter()` saves the `dead_letters` trace (error, stack, `llm.last_output`, attempts; any `sk-…` provider key redacted), copies it to `agent.dlq` and marks the run `failed`. A dead-letter failure is logged, never allowed to mask the job's error. Jobs BullMQ fails on its own (stalled more than `maxStalledCount`, i.e. the worker died twice) never reach the processor, so `Actor._on_failed` dead-letters those from the worker `failed` event. Replay goes through `dlq.replay()` only.
- **Token budget**: `Actor.process` checks `run.tokens_used()` against `RUN_TOKEN_BUDGET` before calling the handler; an over-budget step ends the run (completed with the latest draft + warning, else failed) instead of calling the LLM. Every agent must report `Outcome.usage`, or the budget can't see its spend.
- **Outbox order**: an actor saves its outputs, `done` and the next hop (`steps.<step>.next`) in one Mongo write, then sends. Never send first: the next actor could read the run before the outputs exist.
- Workers connect with `worker_url()` (socket_timeout 30s). redis-py 8's 5s default breaks BullMQ's blocking wait and stalls pickup by up to ~20s.
- **Genuine sources only**: quotes come from `sources.fetch()` + `passages()`, never from LLM output. Don't give research `WebFetch` back (it puts whole pages in the LLM context, ~10x the tokens). Fetches go only to public IPs (URLs come from an LLM reading untrusted pages).
- **Source strength**: a source's kind comes from its site (`sources.kind_of`: .gov/IR/newsroom → primary, scholarly hosts → paper, aggregators never primary), not the LLM's guess. Research adds OpenAlex papers (`services/scholar.py`, abstracts as page text) and, when under `MIN_STRONG` of readable pages are papers/primary, runs one more primary-only search. The critic's `source_quality` is counted from the cited sources, never judged. `CONTACT_EMAIL` goes only to hosts in `sources.IDENTIFY` (SEC), never to other sites.
- Jobs are **at-least-once**, so every worker must be idempotent: check the run doc's step status before doing work, and enqueue only via `queues.enqueue()`, which dedupes by job id `<run>-<step>-<revision>` (`-`, not `:`: Node BullMQ rejects `:` in custom ids).

## Conventions
- `app/routers/` is HTTP/WS only, with thin routes that call `app/services/*`. AI agents live in `app/agents/`.
- Every actor loads the full run doc from Mongo before working, never just the queue message.
- Settings come from `config.py` (env vars); add new ones there and in `.env.example`.
- Tests for each service (state, queues, events, llm error mapping) and each agent's logic, with the LLM mocked; `pytest` must never call Claude (monkeypatch `llm.query`).
- Any change to retrieval (`services/sources.py`, `research.select`/`retrieve`, passage size, weights) must be measured with `uv run python -m scripts.eval` before and after; keep it only if the numbers don't drop. Raise `FLOOR` in `tests/test_eval.py` when they improve.
- Agents report sub-steps with `await progress.report(phase, detail, **data)` (`services/progress.py`): one plain-English line per real step, data only what the UI renders (questions, pages, scores). It's a no-op outside an Actor, so handlers stay testable. Tool calls inside `llm.complete` are reported automatically.
- Events go through `events.emit` (store on the run, then publish), never `publish` alone, or a reload loses them.
- `llm.complete(think=False)` for judge-style calls that only fill a schema (the critic): the CLI's default thinking was ~90% of their output tokens.
- Add deps with `uv add`.
