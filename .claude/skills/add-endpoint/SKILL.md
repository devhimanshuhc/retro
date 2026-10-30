---
name: add-endpoint
description: Add or change an API endpoint or WebSocket event end to end — FastAPI route, pydantic model, TypeScript type, and the web client call. Use when the user says "add an endpoint", "new API route", "the UI needs X from the backend", "add an event type", or changes a request/response shape.
---

# Add an endpoint (backend ↔ frontend contract)

The API contract lives in two places that must change together: the pydantic models in `apps/agents/app/models/` (source of truth) and `apps/web/src/lib/types.ts` (mirror). Change both in the same edit, or the UI breaks silently at runtime.

## Checklist
1. **Model** in `apps/agents/app/models/`: request and response pydantic models. Field names are snake_case, and the TS mirror uses the same names (no camelCase mapping).
2. **Route** in `apps/agents/app/routers/<area>.py`; include the router in `app/main.py`. Routes stay thin: call `app/services/*`, no business logic in the route.
   - Starting work → return **202** with the id, and enqueue. Never wait for agents inside a request.
   - Missing run → 404. Bad input → 422 (pydantic does this for you).
   - Never return API keys, raw env, or stack traces. Dead-letter traces are the one deliberate exception (debugging is their purpose) and still must not contain keys.
3. **WebSocket events**: every event is `{type, workflow_run_id, agent, ts, data}`. A new event `type` gets a model, a TS type, and a case in the web's `reduceEvents`.
4. **Test** in `apps/agents/tests/test_<area>.py` using the `client` fixture: happy path, 404, invalid input.
5. **TS mirror**: update `apps/web/src/lib/types.ts`, then the fetch helper in `apps/web/src/lib/api.ts` (the only file that builds API URLs).
6. **CORS**: a new browser origin goes in `WEB_ORIGINS` in `apps/agents/.env`, never `allow_origins=["*"]`.

## Verify
```bash
cd apps/agents && uv run pytest -q
cd apps/web && npm run lint && npm run build     # type errors here mean the mirror is out of sync
```
FastAPI's live schema at http://localhost:8000/docs is the quickest way to compare against `types.ts`.
