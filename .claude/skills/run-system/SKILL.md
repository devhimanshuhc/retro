---
name: run-system
description: Start the scheduler locally (Redis, Mongo, API, all agent workers), submit a workflow, and inspect queues, run state and dead letters. Use when the user says "run it", "start the system", "test a workflow end to end", "why is my run stuck", or wants to check queue or DLQ contents.
---

# Run the system locally

Run infra commands from the repo root, Python commands from `apps/agents/`, web commands from `apps/web/`. Parts that don't exist yet (check the build steps in CLAUDE.md) are skipped.

## 1. Infra
```bash
docker compose up -d --wait redis mongo
docker compose exec -T redis redis-cli CONFIG GET maxmemory-policy   # must be noeviction
```
If Docker isn't running: `open -a Docker`, wait until `docker info` succeeds.

Docker's Redis is on host port **6380**: a Homebrew Redis already owns 6379 on this machine. Always connect with `redis://localhost:6380` (as in `.env`). A connection to 6379 silently reaches the wrong Redis.

## 2. API + workers (each agent is its own process)
Run each as a background process so the logs stay separate (in `apps/agents/`):
```bash
uv run --env-file .env python scripts/dev_server.py
uv run --env-file .env python -m app.agents.supervisor
uv run --env-file .env python -m app.agents.research
uv run --env-file .env python -m app.agents.writer
uv run --env-file .env python -m app.agents.critic
```
Real agents call Claude via the Agent SDK: with `ANTHROPIC_API_KEY` empty they use your Claude Code login (`claude auth status`); set the key for anything deployed or shared. Never print its value.

Web UI (in `apps/web/`): `npm run dev` → http://localhost:3000. It calls the API at `NEXT_PUBLIC_API_URL` from `.env.local`.

## 3. Submit and watch a run
Until the API exists (step 17), from `apps/agents/`:
```bash
uv run --env-file .env python -m scripts.submit "Write a short market report on Nvidia Q3 earnings"
# → submitted <id> ... completed: supervisor=done@rev0, research=done@rev0, ...
```
Once the API exists:
```bash
curl -s -X POST localhost:8000/workflows -H 'content-type: application/json' \
  -d '{"prompt": "Write a short market report on Nvidia Q3 earnings"}'   # → 202 + workflow_run_id
curl -s localhost:8000/workflows/<id>
```
Live events: `WS /workflows/<id>/events`.

## 4. Inspect when something is stuck
```bash
# jobs per queue: wait / active / failed / delayed
uv run --env-file .env python -c "
import asyncio
from bullmq import Queue
async def main():
    for n in ['supervisor', 'research', 'write', 'critic', 'dlq']:
        q = Queue(f'agent.{n}', {'connection': 'redis://localhost:6380'})
        print(f'agent.{n}', await q.getJobCounts('wait', 'active', 'failed', 'delayed'))
        await q.close()
asyncio.run(main())"
# run doc and dead letters
docker compose exec -T mongo mongosh scheduler --quiet --eval 'db.workflow_runs.find().sort({_id:-1}).limit(1)'
docker compose exec -T mongo mongosh scheduler --quiet --eval 'db.dead_letters.find().sort({_id:-1}).limit(5)'
```
How to read it: jobs in `wait` with nothing `active` → that agent's worker isn't running. Growing `delayed` → retries with backoff, or the queue was paused on a 429. Anything in `dead_letters` → read the error and the raw LLM output there before changing code.

## 5. Stop
Stop the worker, API and web processes, then `docker compose down`. uvicorn's reloader can outlive a plain `kill`: check `lsof -nP -iTCP:8000 -sTCP:LISTEN` and kill the leftover PIDs. Use `down -v` only when the user asks to wipe the data.
