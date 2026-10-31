# Data schema (MongoDB)

The contract for what's stored. Each field is built in code (`apps/agents/app/models/`) in the step that first uses it, shown below. Don't add a field before its step, and don't change a shape without updating this file.

Two collections. Everything about one run lives in **one document**, so an actor gets its full context with one read and the dashboard gets everything with one request. Size is bounded: at most `MAX_REVISIONS` (3) reports per run, far below Mongo's 16 MB document limit.

## `workflow_runs` (one doc per run, `_id` = workflow_run_id)

| Field | Type | Step | Notes |
|---|---|---|---|
| `_id` | str (uuid hex) | 6 ✅ | |
| `prompt` | str, non-empty | 6 ✅ | The user's request |
| `turns` | `[{role: user\|assistant, text, created_at}]` | 22e ✅ | The conversation, first message included (empty on older runs). The router appends its reply to each user message |
| `intent` | `chat` \| `decline` \| `research` \| null | 22e ✅ | The router's decision on the latest message. Only `research` reaches the planner; a finished chat takes follow-ups (`POST /workflows/{id}/messages`) |
| `brief` | str \| null | 22e ✅ | The research request in one sentence, when a later message started research; agents read `brief or prompt` (`WorkflowRun.request`). `prompt` never changes |
| `document_ids` | `[str]` | 22c ✅ | The user's files (`documents`) research reads, every objective reading every file |
| `web` | bool (default true) | 22c ✅ | false = research reads only the files: no web search, no OpenAlex |
| `status` | `submitted` \| `working` \| `input-required` \| `completed` \| `failed` \| `canceled` | 6 ✅ | A2A task states. Terminal: completed, failed, canceled |
| `revision` | int ≥ 0 | 6 ✅ | Current report revision; the critic bumps it on fail |
| `created_at`, `updated_at` | UTC datetime, ms precision | 6 ✅ | Mongo stores ms; we truncate so reads equal writes |
| `steps` | `{supervisor\|research\|write\|critic: StepState}` | 8 ✅ | Missing key = pending. The duplicate-delivery guard (below) |
| `plan` | `{objectives: [{id, question}] (1–5), outline: [str] (1–8)}` | 10 ✅ | Written by the supervisor |
| `findings` | `[{objective_id, summary, sources: [{url, title, kind, quote}] (≥1)}]` | 11 ✅ | `kind`: paper \| primary \| news \| other \| file (the user's upload; `url` is `doc://<documents._id>`, listed without a link). `quote` (20–500 chars) is a passage that `services/sources.py` copied from the fetched page or PDF (public addresses only) and ranked as relevant; the LLM picks passages by id and never writes quotes. Objectives with no usable passage are dropped, with a warning | Written by research |
| `revisions` | `[{revision, report_md, created_at, critique, summary}]` | 12–13 ✅ | One per writer pass; `report_md` ends with a code-built `## Sources` list cited as [n]; `critique` filled by the critic; `summary` (22e) a 2–3 sentence reply written on a pass by the small model, every number checked against the report |
| `revisions[].critique` | `{passed, errors: [str], scores: {factual_accuracy, citation_accuracy, completeness, source_quality} \| null}` | 13 ✅ | Scores 0.0–1.0; `scores` is null when deterministic checks failed and the LLM was skipped. Pass = factual_accuracy, citation_accuracy, completeness all ≥ 0.7; low source_quality only adds a warning (the writer can't change sources) |
| `events` | `[{id, type, workflow_run_id, agent, ts, data}]` (JSON) | 19b ✅ | Last 500 events (`models/events.Event`), oldest first, pushed by `services/events.emit` before it publishes on Redis `workflow:{id}`. Includes `step.progress` sub-steps. A reload rebuilds the timeline from them; clients dedupe live events by `id`. Not in `RunUpdate`: only `emit` writes it, with `$push`/`$slice` |
| `edits` | `[{revision, instruction, created_at}]` | 21c ✅ | Follow-up changes asked for after the report was done (`POST /workflows/{id}/edit`). Each reopens the run (completed → working) at `revision`; the writer applies the latest edit at or before its revision to the previous report, the critic reviews it with the outline check off, and `MAX_REVISIONS` counts from the edit's revision |
| `warnings` | `[str]` | 11–13 ✅ | Dropped sources/objectives (research), weak sources or MAX_REVISIONS (critic) | e.g. "MAX_REVISIONS reached" |
| `error` | `{agent, message}` \| null | 15 | Set when a job dead-letters and the run fails |
| `usage` | `{<step>: {input_tokens, output_tokens}}` | 10 ✅ | Summed across revisions; a failed attempt's tokens aren't counted | Cost per run for the README |

### `StepState`
| Field | Type | Notes |
|---|---|---|
| `status` | `working` \| `done` | Absent step = pending. A failure shows on the run (`error`) and in `dead_letters` |
| `revision` | int | Which revision this step last worked on |
| `started_at`, `finished_at` | datetime \| null | |
| `next` | `{queue, revision}` \| null | Outbox: the message to send after done. Saved in the same write as the outputs, then sent; a redelivered job for a done step re-sends it (deduped) |

Attempts aren't stored here: BullMQ counts them per job (`attemptsMade`), and `dead_letters` records the final count.

**Duplicate guard** (`state.claim_step`): one atomic update sets `steps.<step>` to `working` **only if** the run isn't terminal and that step isn't already `done` for this revision or a later one. If the claim fails, the job is a duplicate (or the run is over) and the worker skips it. A `working` step doesn't block a claim, so a retry after a crash can always take the step back.

## `dead_letters` (one doc per job that ran out of attempts or failed unrecoverably, step 15 ✅)
Model: `app/models/dead_letter.py`. Written by `services/dlq.dead_letter()` from `Actor._job` on the last attempt.

| Field | Type | Notes |
|---|---|---|
| `_id` | str | uuid; also the job id of its copy on `agent.dlq` |
| `queue` | str | agent queue it failed on, e.g. `agent.research` |
| `job_id` | str | original BullMQ job id `<run>-<step>-<revision>` (replay retries this job) |
| `workflow_run_id`, `revision` | str \| null, int \| null | null when the message itself was malformed |
| `data` | dict | job data as received |
| `attempts` | int | attempts made, including the final one |
| `error`, `stack` | str | `Type: message` and the formatted traceback |
| `raw_output` | str \| null | last LLM output the job got (≤20k chars), e.g. a plan that failed validation |
| `created_at`, `replayed_at` | datetime, datetime \| null | a dead letter replays once |

Never contains API keys (`ANTHROPIC_API_KEY` is redacted from error, stack and raw output). Dead-lettering also sets the run's `status` to `failed` (unless it already finished); replay sets it back to `working` atomically (only from `failed`, so two replays can't both run) and retries the original job with `attemptsMade` reset.

## `documents` (the user's uploaded files, step 22c ✅)
`{_id, name, size, chars, text, created_at}`. `text` is pulled out once on upload (`services/documents.py`: PDF up to
400 pages, HTML, text, Markdown, CSV, JSON; ≤20 MB, ≤2M chars); the file itself isn't kept. `GET /documents` never
returns `text`. Deleting a file doesn't change reports that already quote it.

## `settings` (app settings, one doc per setting)
- `_id: "anthropic"` / `"openai"`: `{api_key, updated_at}`: a provider's API key pasted in the web app
  (`services/api_keys.py`). Checked with the provider before saving; wins over `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`;
  actors load it per job. Never returned by the API (`GET /settings/llm` gives only `active` and each provider's
  `source`: `app` | `env` | `login` | null). Plain text on the local Mongo for now.
- `_id: "google_client"`: `{client_id, client_secret, updated_at}`: the user's own Google app (OAuth client) for Google
  Docs, pasted in Connectors; wins over `GOOGLE_CLIENT_ID`. Replacing it drops the account below. Never returned.
- `_id: "google"`: `{refresh_token, email, updated_at}`: the connected Google account (`services/google.py`, scope
  `drive.file`). Access tokens are fetched per export and never stored. Never returned (only `email`).
- `_id: "provider"`: `{value, updated_at}`: the provider the agents use (set by saving a key or `PUT /settings/llm/active`).

## Worker presence (Redis, not Mongo)
`<prefix>:workers:<worker id>` → `WorkerInfo` JSON (`app/models/api.py`), TTL 15s, refreshed every 5s and on every state change by each `Actor` process (`services/workers.py`): agent, host, pid, `idle|busy`, current run/revision, latest sub-step (`activity`), jobs done. A killed worker drops out when its key expires; a clean stop deletes it. `GET /workers` lists them.

## Queue message (Redis, not Mongo)
`AgentMessage{workflow_run_id, revision}` (step 7 ✅). Ids only; extra fields are rejected.

## Indexes (created on API startup by `state.ensure_indexes`, step 17 ✅)
- `workflow_runs`: `{status: 1, created_at: -1}`, `{created_at: -1}`, `{status: 1, updated_at: -1}` (artifacts list)
- `dead_letters`: `{workflow_run_id: 1}`, `{created_at: -1}`
