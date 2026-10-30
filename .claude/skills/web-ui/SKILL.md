---
name: web-ui
description: Build or change the Next.js dashboard in apps/web — pages, components, the live run timeline, queue-depth panel, report view. Use when the user says "frontend", "UI", "dashboard", "page", "component", "show X in the web app", or anything under apps/web.
---

# Web UI (apps/web)

Next.js **16.4** (App Router, `src/` dir), React 19, Tailwind v4, TypeScript, npm. Run all commands in `apps/web/`.

## Before writing code
This Next.js is newer than your training data. Read the relevant guide in `apps/web/node_modules/next/dist/docs/` first (`01-app/01-getting-started/` covers server/client components, caching, route handlers). Heed deprecation notices. `apps/web/AGENTS.md` says the same; keep that file.

## Layout
```
src/app/            routes (page.tsx, layout.tsx); runs/[id]/page.tsx for one run
src/components/     UI components (PascalCase.tsx)
src/lib/api.ts      API_URL + fetch helpers (the only place that builds API URLs)
src/lib/types.ts    TS types mirroring the pydantic models in apps/agents/app/models
src/lib/*.ts        pure logic (e.g. reduce events → run timeline), tested
```

## Rules
- **The web app only talks to the FastAPI service**: REST + WebSocket at `NEXT_PUBLIC_API_URL`. Never connect to Redis or Mongo, and never call Anthropic from the web app.
- **No secrets in apps/web.** Only `NEXT_PUBLIC_*` vars reach the browser; the only one we need is `NEXT_PUBLIC_API_URL`. Set in `.env.local` (gitignored); `.env.example` documents it.
- **Live data is client-side.** Run status and events change every second: render them in `"use client"` components fed by the WebSocket. Never put `"use cache"` on run state. `cacheComponents` is on, so a server component that fetches uncached data must sit inside `<Suspense>`.
- **One WebSocket hook**, `useRunEvents(runId)` in `src/lib/`: open on mount, close on unmount, reconnect with backoff, then refetch `GET /workflows/{id}` after reconnecting so missed events aren't lost. Use the plain browser `WebSocket`; the API isn't Socket.IO.
- **Event → UI state is a pure function** (`reduceEvents(events) → timeline`) in `src/lib/`, so it can be tested without a browser.
- **Types follow the backend.** When a pydantic model in `apps/agents/app/models/` changes, update `src/lib/types.ts` in the same change (see the `add-endpoint` skill).
- **Styling**: Tailwind utility classes and the tokens in `globals.css`, with light and dark via `prefers-color-scheme`. No component library or extra CSS framework unless the user asks.
- **Accessibility**: status changes go in an `aria-live="polite"` region (`role="status"`). Never use color alone for state: retrying, failed and DLQ'd steps need text or an icon too. Every control is keyboard-reachable with a visible focus ring.
- **Dependencies**: don't add any for things React/Next/the browser already do (fetch, WebSocket, state). Markdown rendering for the report is the one expected addition: `react-markdown`, with raw HTML left disabled, since the report is LLM output.

## What the dashboard shows (in priority order)
1. Prompt box + submit → `POST /workflows` → go to `/runs/[id]`.
2. Live timeline per run: each agent step with started / done / retrying (attempt n/3) / paused on 429 / dead-lettered.
3. Queue depth per agent queue (wait / active / delayed / failed), which makes `--scale writer=3` visible.
4. Final report (markdown) + critic feedback per revision.
5. Dead letters list with the error and raw LLM output, plus a replay button.

## Verify
```bash
npm run lint && npm run build
node --test src/lib/*.test.ts     # pure logic; Node 25 runs .ts directly — use relative imports with .ts extensions in tested files
```
Then run the API and `npm run dev` (see the `run-system` skill) and check the page in a browser. A passing build doesn't prove the live view works.
