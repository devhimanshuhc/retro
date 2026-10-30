<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## This app in this repo
- Standalone npm app, **not** part of a Turborepo or workspace (there is none). Run every command from `apps/web/`; `node_modules/` and `package-lock.json` live here.
- "Turbopack" in `next.config.ts` is Next.js's bundler, unrelated to Turborepo.
- Backend is `apps/agents` (FastAPI). This app reaches it only through `NEXT_PUBLIC_API_URL`. Repo-wide guide: `../../AGENTS.md`.
