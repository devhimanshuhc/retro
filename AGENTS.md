# AGENTS.md

Guide for coding agents working in this repo. The full plan, architecture and build steps are in `.claude/CLAUDE.md`. Read it before starting a task.

## What this is
**Retro**: an actor-model multi-agent task scheduler: AI agents are isolated workers that communicate only through BullMQ queues on Redis, with workflow state in MongoDB and a Next.js dashboard showing runs live.

## Repo layout: two independent apps, no monorepo tooling
**No Turborepo, Nx, or npm/pnpm workspaces.** Don't add any. Each app has its own toolchain, dependencies and lock file, and you run commands **inside the app's folder**. There is no root `package.json`.

```
apps/agents/   Python 3.12 · uv · FastAPI · bullmq · pymongo · claude-agent-sdk   (all backend + AI agents)
apps/web/      Node 25 · npm · Next.js 16.4 · React 19 · Tailwind 4 · TS     (dashboard)
docker-compose.yml   Redis 7 (host port 6380) + MongoDB 8
docs/research.md     papers and blogs the design is based on
docs/schema.md       MongoDB data contract (update it with any model change)
```
The two apps share no code and talk only over HTTP + WebSocket (`NEXT_PUBLIC_API_URL`, default `http://localhost:8000`).

("Turbopack" in `apps/web` is Next.js's built-in bundler, not Turborepo. Leave it as is.)

## Commands
| Task | Run in | Command |
|---|---|---|
| Start Redis + Mongo | repo root | `docker compose up -d --wait` |
| Start Nango (connectors) | repo root | `docker compose --profile nango up -d` (dashboard :3003, Connect UI :3009; secrets in the root `.env`) |
| Backend tests | `apps/agents` | `uv run pytest -q` |
| API dev server (:8000) | `apps/agents` | `uv run --env-file .env python scripts/dev_server.py` |
| Agent worker | `apps/agents` | `uv run --env-file .env python -m app.agents.<name>` |
| Research evals | `apps/agents` | `uv run python -m scripts.eval` (0 tokens) · add `--llm` for answer/judge evals |
| Report evals (end to end) | `apps/agents` | `uv run python -m scripts.report_eval` (real runs, ~70k tokens each) · `--score <run_id>… --case <id>` scores past runs at 0 tokens |
| Web dev server (:3000) | `apps/web` | `npm run dev` |
| Web checks | `apps/web` | `npm run lint && npm test && npm run build` |
| Rebuild the landing figure | `apps/web` | `npm run build:figure` (writes `src/components/landing/stack-art.json`) |
| Add a dependency | that app | `uv add <pkg>` / `npm install <pkg>` |

Before saying work is done, run the checks for every app you touched.

## Rules
- Agents (actors) never import or call each other. The only channel between them is a queue message, and messages carry ids, not large payloads.
- `apps/web` talks only to the API. Never to Redis, Mongo, or an LLM provider. No secrets in `apps/web`; only `NEXT_PUBLIC_*` vars reach the browser.
- API contract: pydantic models in `apps/agents/app/models/` are the source of truth, and `apps/web/src/lib/types.ts` mirrors them in the same change.
- Never log, print or commit API keys. `.env` / `.env.local` are gitignored; document new vars in the matching `.env.example`.
- Next.js 16 is newer than most models' training data: read `apps/web/node_modules/next/dist/docs/` before writing web code (see `apps/web/AGENTS.md`).
- Redis is on port **6380**, not 6379 (a different local Redis owns 6379).
