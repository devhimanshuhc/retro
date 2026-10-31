@../AGENTS.md

# Retro: project plan

The product is called **Retro** (wordmark + glyph in `apps/web/src/components/Mark.tsx`, favicon `apps/web/src/app/icon.svg`).

The shared repo guide (layout, commands, core rules) is imported above from the root `AGENTS.md`. Edit shared facts there, not here. This file holds the plan. App-specific rules live in `.claude/rules/` and load only when you touch files in that app:
- `.claude/rules/backend.md` → `apps/agents/**` (folder plan, resilience rules, backend conventions)
- `.claude/rules/web.md` → `apps/web/**` (folder plan, frontend conventions)

Goal: a production-grade, resume-worthy system. Fault tolerance must be **demonstrable** (chaos demo + live dashboard), not just claimed.

Example workflow: "Write a market report on Nvidia's Q3 earnings" → plan → research → write → critique (loop back to writer until it passes) → done, with live progress over WebSocket.

## Tech stack
**apps/agents (backend)**

| Layer | Choice | Version | Replaces (original NestJS spec) |
|---|---|---|---|
| Language | Python | 3.12 | TypeScript |
| Packaging | uv (`pyproject.toml` + `uv.lock`) | latest | npm |
| API | FastAPI + uvicorn | 0.162 / 0.54 | NestJS |
| Queues / mailboxes | `bullmq` (Python port, same Redis protocol as Node BullMQ) | 3.4 | BullMQ (Node) |
| Broker | Redis, `maxmemory-policy noeviction` (required by BullMQ) | 7 | Redis |
| State store | MongoDB via pymongo async (`AsyncMongoClient`; motor is deprecated) | Mongo 8 / pymongo 4.19 | MongoDB + Mongoose |
| LLM | `claude-agent-sdk` (runs the bundled Claude Code CLI). Auth: `ANTHROPIC_API_KEY` if set, else your local Claude Code login (personal use only; anything deployed or used by others needs a key) | 0.2 | Vercel AI SDK / LangChain |
| Validation | pydantic (comes with FastAPI) | v2 | class-validator |
| Realtime | FastAPI WebSocket, fed by Redis pub/sub | — | Socket.IO |
| Tests | pytest + pytest-asyncio | — | Jest |
| Infra | Docker, Docker Compose (one container per agent type); GitHub Actions CI | — | Docker / AWS ECS |
| Tracing (optional) | OpenTelemetry GenAI semantic conventions | — | — |

**apps/web (frontend)**

| Layer | Choice | Version |
|---|---|---|
| Framework | Next.js, App Router, `src/` dir, Turbopack (Next's bundler, not Turborepo), `cacheComponents` on | 16.4 |
| UI | React | 19.3 |
| Styling | Tailwind CSS | 4 |
| Language | TypeScript | 5 |
| Package manager | npm (Node 25) | 11 |
| Lint / tests | ESLint (`eslint-config-next`); pure logic tested with `node --test` (Node runs `.ts` natively) | — |

**Models** (Anthropic only, no OpenAI key; set per agent in `apps/agents/.env`):
supervisor, research + critic → `claude-haiku-4-5-20251001`, writer → `claude-sonnet-5-5`. Research moved to Haiku after evals showed no drop (answer accuracy 0.857 both, faithfulness 1.0 vs 0.988); the critic runs with thinking off (~30x fewer output tokens).

## Research
Based on Anthropic's multi-agent research system and "Building effective agents", the MAST failure taxonomy (arXiv 2503.13657), AgentScope, and Cognition's "Don't Build Multi-Agents". Full list, what we take from each, and the MAST failure-mode → guard mapping: `docs/research.md`.

## Architecture
```
[ User ] ─POST /workflows─▶ API ──(202 + workflow_run_id, returns instantly)
                             │ creates run doc in Mongo, enqueues to agent.supervisor
                             ▼
                    ┌────────── Redis / BullMQ ──────────┐
                    │ agent.supervisor  agent.research   │
                    │ agent.write       agent.critic     │
                    │ agent.dlq                          │
                    └────────────────────────────────────┘
     Supervisor ─▶ Research ─▶ Writer ─▶ Critic ──pass──▶ run = completed
                                 ▲          │
                                 └─fail+feedback (max MAX_REVISIONS)
  Every worker: reads/writes the run doc in Mongo, publishes events to Redis
  channel `workflow:{id}` → API → WebSocket → apps/web dashboard.
```

- **Messages carry ids only**: `AgentMessage{workflow_run_id, revision}` (`app/models/messages.py`, extra fields rejected). Plan, findings, reports and critic feedback live in Mongo, never in the queue.
- **Every actor loads the full run context** from Mongo (original prompt, plan, prior outputs), never just the message, so no agent works from a lossy summary.
- **Run status** uses A2A task states: `submitted → working → completed | failed | canceled` (`input-required` reserved for a later human-in-the-loop).

### Flow
1. **Supervisor**: plan the task (structured plan of sub-objectives, pydantic-validated), save it, send the message to `agent.research`.
2. **Research**: gather facts (the SDK's `WebSearch`/`WebFetch` tools), save findings with sources, send `{workflow_run_id}` to `agent.write`.
3. **Writer**: read findings (+ any critic feedback) from Mongo, write a markdown report, save it as a new revision, send to `agent.critic`.
4. **Critic**: deterministic checks first (pydantic schema, required sections, citations present), then an LLM rubric (factual accuracy, citation accuracy, completeness, source quality). Pass needs both, plus every number in the report must appear in the findings (code check; the rubric alone passed planted wrong numbers at ~0.85). Fail → save the errors on the run, bump `revision`, send to `agent.write`. Pass, or `MAX_REVISIONS` reached → mark run `completed` (with `warnings` set if the cap was hit).

## Build steps (do in order; verify each before moving on)

**Setup** ✅
1. venv + deps: `fastapi uvicorn bullmq pymongo anthropic pytest pytest-asyncio`.
2. `docker-compose.yml` with Redis 7 (noeviction) and Mongo 8. Verified: both healthy, a BullMQ job enqueues, Mongo pings. Docker Redis is on host port **6380** because a Homebrew Redis owns 6379 on this machine.
3. `.env` (gitignored) + `.env.example`.

**Scaffold** ✅
4. FastAPI template layout: uv project on Python 3.12, `config.py`, `pytest.ini`, `app/main.py` with `/health`, `scripts/`, `tests/`. Verified: tests pass, dev server answers `/health`.
5. Two-app layout: Python moved to `apps/agents`; `apps/web` created with create-next-app 16.4.3 (TS, Tailwind, ESLint, App Router, `src/`); CORS for `localhost:3000` (tested); home page shows API health. Verified: pytest, web lint + build, web → API call with CORS.

**Actor plumbing (no LLM yet)**
6. ✅ `services/state.py` + `models/run.py`: create/get/update a workflow run in Mongo (A2A statuses, validated updates, ms timestamps). 11 tests against real Mongo, throwaway DB each.
7. ✅ `services/queues.py` + `models/messages.py`: queue names, default job options (3 attempts, exponential backoff 2s, keep finished jobs 24h / failed 7d), `enqueue(queue, AgentMessage)` with dedupe by job id `<run>-<step>-<revision>`. 5 tests against real Redis, throwaway prefix each.
8. ✅ `agents/base.py` (`Actor`, `Outcome`, `main`) + 4 stub agents + `steps` duplicate guard (`claim_step`/`finish_step`) + `scripts/submit.py`. Verified: 2 runs completed through 4 separate worker processes; workers stop cleanly on SIGTERM; tests cover duplicate delivery, crash-before-done retry, malformed message, full pipeline (28 tests).

**Real agents**
9. ✅ `services/llm.py`: `complete(agent, prompt, system=, schema=, tools=)` on the Agent SDK; no tools and no repo settings by default; JSON-schema structured output; error mapping (429 → `RateLimited`, 5xx/408/timeouts → retry, other 4xx/auth/billing/missing CLI → `UnrecoverableError`). Verified live via Claude login (text + schema); 13 mocked tests (41 total).
10. ✅ Supervisor: structured `Plan` (2–4 objectives + outline), pydantic-validated; a bad plan raises and retries.
11. ✅ Research as retrieval (RAG without embeddings): (1) one LLM call with `WebSearch` only picks 2–4 candidate URLs per objective (papers > primary > news); (2) `services/sources.py` fetches them (HTML/PDF, public IPs only), splits into sentence passages and ranks them with BM25, keeping 6 per objective (≤2 per page), at zero tokens; (3) one LLM call writes findings from those passages, citing passage ids. Quotes are page text copied by code, so they can't be invented. Dead pages/unanswered objectives → warnings; nothing usable → retry.
12. ✅ Writer: report from findings only, cites `[n]`; code appends the deduped `## Sources` list (no invented URLs); gets the previous draft + critic errors on revisions.
13. ✅ Critic: deterministic `check()` first (sections, citations present and in range, every sentence with a number/date cited; fail skips the LLM), then a rubric judged only against the verified quotes (pass = factual, citation, completeness ≥ 0.7; weak source_quality → warning, not a rewrite); fail → `revision+1` back to the writer; cap → completed + warning.
    Also: **outbox** ordering in `Actor` (save outputs + done + `next` hop in one write, then send; a redelivery re-sends a lost hop), per-step token `usage`, failure logging, and the redis-py 8 `socket_timeout` fix (`worker_url`) that cut idle pickup from ~10–20s to ~10ms. Verified: live run through 4 processes with real web research (8 sources, passed); 58 tests.
13b. ✅ Research evals (`scripts/eval.py`, `evals/`): 14 cases on saved page snapshots (papers, filings, Wikipedia; each with distractor pages), labelled by evidence snippets. Retrieval metrics hit@6 / recall@6 / MRR at 0 tokens, gated in pytest (`tests/test_eval.py`); `--llm` adds answer correctness (expected facts, checked by code) and an LLM judge (claim-level faithfulness, context sufficiency). Results saved to `evals/results/`. Used it to reject two ranking ideas (stopwords, stemming) and keep one (drop reference-list passages).

**Fault tolerance**
14. ✅ Retries + exponential backoff + queue-wide pause on 429: `llm.RateLimited` carries the reset time from the CLI's `RateLimitEvent` (else `RATE_LIMIT_PAUSE_MS`); `Actor` calls `queue.rateLimit(ms)` on its own queue and re-raises so BullMQ retries. Workers need a `limiter` option or BullMQ ignores the pause. Proven with a fake 429 against two real workers (`test_429_pauses_every_worker_of_the_agent_then_retries`; fails if the limiter is removed). 77 tests.
15. ✅ Dead-letter queue: on the last attempt (or `UnrecoverableError`) `Actor._job` saves a `dead_letters` trace (error, stack, last raw LLM output, attempts; API key redacted), copies the job to `agent.dlq` and marks the run `failed`. `GET /dead-letters[?workflow_run_id=]`, `GET /dead-letters/{id}`, `POST /dead-letters/{id}/replay` (202; reopens the run atomically, retries the original job with fresh attempts; 409 if already replayed or run not failed). Tested end to end with a real worker (fail → DLQ → replay → step done).
16. ✅ Idempotency under SIGKILL (`tests/test_chaos.py`, real worker processes via `tests/chaos_worker.py`): a writer killed mid-job → another worker takes the stalled job back after its lock expires → run completes with exactly one revision. Killed twice → BullMQ fails the job itself (maxStalledCount 1, bypassing the processor), so `Actor` also dead-letters on the worker `failed` event (`deferredFailure`); without that the run hung in `working` forever. `Actor(lock_ms=)` sets lockDuration/stalledInterval (30s default). 84 tests.

**API + realtime**
17. ✅ `POST /workflows` → 202 `{workflow_run_id}` (~20ms; creates the run, enqueues to the supervisor); `GET /workflows[?status=&limit=]` (summaries, newest first); `GET /workflows/{id}` (full run); `GET /queues` (waiting/active/delayed/failed/completed per queue). Indexes created on API startup (`state.ensure_indexes`). TS mirror + fetch helpers in `apps/web/src/lib/{types,api}.ts`.
18. ✅ WebSocket `/workflows/{id}/events`: subscribes to Redis `workflow:{id}`, then sends a `run.snapshot` (read after subscribing, so no gap), forwards events, closes after a final `run.status`. Actors publish `step.started/done/failed`, `rate_limited`, `dead_lettered`, `run.status` (best effort; a lost event never fails a job). Origin checked against `WEB_ORIGINS` (CORS doesn't cover WebSockets). Needed the `websockets` package: uvicorn can't upgrade without it, and TestClient hides that. Verified live against the dev server. 97 tests.

**Web dashboard (apps/web)**
19. ✅ Submit page (+ recent runs) and `/runs/[id]` live timeline: `src/lib/timeline.ts` `reduceEvents` (pure; 6 tests via `npm test`), `useRunEvents` (reconnects with backoff; each connect starts with a server snapshot; refetches the run when the socket closes on a final status, so the page gets the final report). Steps show icon + text (pending/working/done/retrying/paused on 429/dead-lettered). Verified: lint, build, WS protocol from a Node client with fake Redis events (no tokens).
19b. ✅ Live sub-steps + chat UI. Backend: `services/progress.report(phase, detail, **data)` from inside handlers (planning, each `WebSearch` query via `llm.complete`, pages found/read/dropped, passages ranked, drafts, code checks, rubric scores, verdict) → `step.progress` events; every event is stored on the run (`events`, last 500) so a reload rebuilds the timeline; worker heartbeats in Redis (`GET /workers`: who is online and what each is doing); `POST /workflows/{id}/cancel` (claimed and in-flight steps are dropped by `claim_step`/`finish_step`). Web: chat layout (run history sidebar, prompt composer, agent activity as one card per agent pass with its sub-steps, workers panel). 103 backend tests, 10 web tests. Verified in headless Chromium (light + dark) by replaying events onto a demo run (0 tokens).
20. ✅ Queue depth (per agent, in the workers panel), final report as markdown (react-markdown, raw HTML off) with clickable citations → source cards, critic verdict + scores per draft (tabs).
20b. ✅ Landing page at `/` in the style of the reference the user chose (griffin.com: warm near-black, serif display, mono uppercase UI labels, pill buttons, dashed grids), original copy and art: hero with live worker status from `/workers`, a canvas of real-format queue message ids, a pinned scroll section where an isometric exploded rack (console → queues → actors → record) comes apart and lights tier by tier with callouts, agents accordion, failure modes, API, measured numbers. The rack is drawn with the Anatomy skill's kit (`apps/web/vendor/anatomy`, MIT) by `npm run build:figure` → `src/components/landing/stack-art.json`. Archival public-domain photos in `public/img` (credits in `credits.json` and the footer). The app moved to `/app` and `/runs/[id]` (route group `(app)`), restyled to match. Skills installed in `.claude/skills/`: `taste-skill`, `anatomy`.
21. ✅ Dead letters page (`/dead-letters[?run=]`): error, stack, last model output (JSON pretty-printed), job data, Replay (409 shown inline); sidebar link with the count waiting; a failed run links to its dead letters. Verified live: a real worker dead-lettered a plan-less run (no LLM call), replay → 202 and re-dead-lettered, second replay → 409.
21b. ✅ Production limits. **Token budget** per run (`RUN_TOKEN_BUDGET`, default 500k): `Actor` checks `run.tokens_used()` before each step and, when spent, stops without calling the LLM: completed with the latest draft + warning, or failed if no draft (a step in flight can overshoot; the check is between steps). **Rate limit** on `POST /workflows`: `RUNS_PER_WINDOW` per client IP per `RUN_WINDOW_S` (fixed window in Redis, `services/limits.py`), 429 + `Retry-After`. 107 backend tests.

21c. ✅ Follow-up edits, artifacts, browser fallback, collapsible timeline. `POST /workflows/{id}/edit {instruction}` reopens a completed run and sends it to the writer (same findings; critic re-reviews, checking the change was made). `GET /artifacts` + `/artifacts` page (open chat / open artifact) + `/artifacts/[id]` full-page report view (route group `(view)`, no app chrome). `services/browser.py`: pages refused with 403/429 or nearly empty (JS-rendered) are re-read once in headless Chromium (public addresses only, no logins; `BROWSER_FALLBACK`); bot-protected sites that block real browsers too still fail, by design. Agent team timeline shows the latest step until expanded. 114 backend tests.

21d. ✅ Stronger sources: source kind by site, OpenAlex papers, a second primary-only search when fewer than half the readable sources are papers/primary, `source_quality` counted in code, SEC contact header (`CONTACT_EMAIL`, sent to sec.gov only). Evals unchanged (hit@6 0.857, recall@6 0.696, MRR 0.702). 128 backend tests.

21e. ✅ Report completeness. End-to-end report eval (`scripts/report_eval.py`, cases in `evals/report_cases.json`, facts hand-checked against a primary source): Nvidia Q2 FY2027 fact recall went 48% → 86% (6/7 in each of 2 runs) by reading short official documents/papers whole (`research.whole_documents`, `WHOLE_CHARS` 30k, cited as `d.N` by any objective); keyword ranking missed their tables and wording ("outlook" vs "guidance"). Retrieval evals unchanged. 134 backend tests.

21f. ✅ (replaced by 22d) Connectors via self-hosted Nango. First: Google Docs. `services/nango.py` (connect session, find connection, Drive multipart upload with a per-request access token from Nango, since Nango's proxy drops non-JSON bodies; HTML from the report's markdown converts to a Google Doc), `routers/connectors.py`: `GET /connectors/google`, `POST /connectors/google/session`, `POST /workflows/{id}/google-doc`. Web: `GoogleDocButton` (panel + artifact page) opens Nango Connect UI the first time. Scope `drive.file` only. Retro holds only `NANGO_SECRET_KEY` (backend .env). 139 backend tests.

21g. ✅ Landing: "Why actors" (typical agent chain vs Retro, six rows) + a second Anatomy figure, `FaultLine` (`scripts/build-faultline.mjs` → `faultline-art.json`): on scroll a crashed station floats with a red lamp, messages wait in its queue, a fresh station drops in, messages move on. "Your report, where you work" (Google Docs, change requests, Artifacts) with an app-fragment mock. `npm run build:figure` rebuilds both figures.

**Ship**
22. ✅ Local install for open source: `apps/agents/Dockerfile` (one image: API + agents, bundled Claude CLI, optional Chromium via `WITH_BROWSER`), `apps/web/Dockerfile` (Next standalone, Node 25), `deploy/compose.yaml` (redis, mongo, api, 4 agents, web; health checks, `restart: unless-stopped`, ports on 127.0.0.1 only), `install.sh` (one command: Docker check, key prompt, start, open localhost:3000), `.github/workflows/release.yml` (multi-arch images to GHCR on tags), README. Verified: images build, whole stack healthy, 4 workers online, Claude CLI 2.1.310 runs in the container. Agents image is ~4 GB (Chromium).
22b. ✅ API keys in the web app, Anthropic **or OpenAI**: `GET /settings/llm`, `PUT/DELETE /settings/llm/{provider}/key`, `PUT /settings/llm/active` (`services/api_keys.py`; key checked with the provider's models endpoint, 0 tokens; stored in Mongo `settings`, never returned; saving a key switches to that provider). Actors set `llm.credentials` per job; `llm.complete` sends OpenAI calls to the Responses API (`web_search` tool, strict `json_schema` via `strict_schema`, `reasoning.effort: low` when `think=False`, 429/insufficient_quota/4xx/5xx mapped like the Claude path). Models `OPENAI_*_MODEL` (luna for planner/research/critic, 6.1-sol for the writer). `POST /workflows` and edits 409 without a key. Card on Connectors + on the new-run page until set. No claude.ai/subscription login option: Anthropic disallows offering it in Agent SDK apps (`USE_CLAUDE_LOGIN=1` is for the developer's own local use only). Dead letters redact any `sk-…` key. OpenAI path tested with a mocked transport only; evals were measured on Claude. 159 backend tests.
22c. ✅ Your own files: Upload `POST /documents` (multipart; text pulled out once, file not kept), `GET /documents`, `DELETE /documents/{id}`; `POST /workflows {document_ids, web}`. Research gives every objective every file (`kind: "file"`, url `doc://<id>`, weighted like primary sources, short files read whole as `d.N`); `web: false` skips web search and OpenAlex and fails without retry when the files don't answer. Composer: attach button, file chips, "Also search the web". Retrieval evals unchanged. Live: a files-only run on the Bitcoin paper passed review on draft 2 (~37k tokens), citing only the file. 166 backend tests.
22d. ✅ Google Docs without Nango: Retro runs the Google sign-in itself (`services/google.py`: OAuth 2.0 + PKCE, state in Redis 10 min, refresh token in Mongo `settings`, access token per export, `drive.file` only). `GET /connectors` never errors on a missing setup; `PUT /connectors/google/client` takes the user's own Google app; `POST /connectors/google/session {return_to}` → Google's URL; `GET /connectors/google/callback` → back to the page with `?google=connected` or to Connectors with `?google_error=`. Web: in-app setup guide (5 steps, redirect URI to copy), the report's Google Docs button goes to the guide when not set up and finishes the export after sign-in. `GOOGLE_CLIENT_ID`/`SECRET` = Retro's own Google app, so users skip the setup (needs a "Desktop app" client registered by the maintainer). Nango, its compose services and the @nangohq/frontend dep are gone. 167 backend tests.
22e. ✅ Router + conversation: a fifth actor, `agent.router` (`agents/router.py`, small model, thinking off, ~a few hundred tokens), reads every message first and decides `chat` (reply, done), `decline` (out of scope, say what Retro does) or `research` (→ planner at revision 0, with a standalone `brief` when a later message started it). The conversation lives in `turns`; a finished chat takes follow-ups via `POST /workflows/{id}/messages` (router revision = user turn index). Attached files skip the model. On a pass the critic adds `summary` (2–3 sentences on the small model, numbers checked against the report, else a plain sentence). `prompt` stays the user's first message; agents read `run.request`. 173 backend tests.
23. GitHub Actions CI: backend pytest + web lint/build/test.
24. Chaos demo (kill workers, inject 429s; fault types from MAS-FIRE), recorded on the dashboard + README with architecture diagram, results, and comparison to AutoGen/Temporal/Dapr.
25. (Optional) Tracing with OpenTelemetry GenAI conventions: trace context travels in job data so one trace spans the whole run.

## Working with Claude Code here
- Skills: `add-agent`, `add-endpoint`, `run-system`, `web-ui` (in `.claude/skills/`). Use them for those tasks.
- All Claude calls go through `services/llm.complete()`; read the Agent SDK Python reference (code.claude.com/docs/en/agent-sdk/python) before changing it. Before writing Next.js code, read the bundled docs (`web-ui` skill).
- Work one step at a time and confirm it runs before starting the next. Mark finished steps ✅ here.
