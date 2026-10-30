---
name: add-agent
description: Add a new actor (AI agent worker) to the scheduler, or change how an existing one is wired. Use when the user says "add an agent", "new actor", "add a step to the workflow", or wants an agent like a fact-checker or summarizer added to the pipeline.
---

# Add an agent (actor)

An agent is a worker process that consumes one BullMQ queue and sends messages to the next. Follow every step; skipping one breaks fault tolerance. All paths below are relative to `apps/agents/`.

## Checklist
1. **Queue name** in `app/services/queues.py`: `agent.<name>`, added to `AGENT_QUEUES`. Reuse the default job options (`attempts: 3`, exponential backoff 2000ms). Never set custom options without a reason in a comment.
2. **Message**: reuse `AgentMessage{workflow_run_id, revision}` from `app/models/messages.py`. Anything else the agent needs goes on the run doc in Mongo, not in the message.
3. **Agent file** `app/agents/<name>.py`: copy a stub (e.g. `research.py`): `async def handle(run, msg) -> Outcome` plus `main(queues.<NAME>, handle)`. The `Actor` in `app/agents/base.py` already does the plumbing. Don't redo it in the handler:
   - claims the step atomically, so duplicate, stale or finished-run jobs are skipped (`state.claim_step`);
   - hands the handler the **full run doc** (`run`), already loaded;
   - enqueues `Outcome.next_queue` (deduped), then marks the step done together with `Outcome.run_updates`.

   The handler itself must:
   - work only from `run` (clean, durable inputs), never from a previous attempt's leftovers;
   - validate LLM output with a pydantic model, then return it in `run_updates` (add the field to `RunUpdate`/`WorkflowRun` and `docs/schema.md`);
   - return `Outcome(next_queue=..., next_revision=..., run_updates={...})`. Don't write to Mongo or enqueue directly.
4. **Errors**: let 429/5xx/timeouts raise (BullMQ retries; on 429 the base pauses the queue for `retry-after`). Raise `bullmq.UnrecoverableError` for bad input or auth. Never catch-and-swallow: a swallowed error skips the DLQ.
5. **Wire it in**: the previous agent enqueues to the new queue, and the new agent enqueues to what came next. Agents never import each other.
6. **Model**: add `<NAME>_MODEL` to `config.py`, `.env.example` and `.env`. Call Claude only through `services/llm.complete()`.
7. **Compose**: add a service running `python -m app.agents.<name>` (same image as the others).
8. **Tests** in `tests/test_agent_<name>.py`, with the LLM mocked:
   - happy path: saves output, enqueues the next step;
   - idempotency: running the same job twice saves once and enqueues once;
   - invalid LLM output → raises (so it retries and eventually reaches the DLQ).
9. **UI**: add the new step to the run timeline in `apps/web` (see the `web-ui` skill), so it shows up live.

## Verify
`uv run pytest` (in `apps/agents/`), then start the system (see the `run-system` skill), submit one workflow, and confirm the run doc shows the new step completed.
