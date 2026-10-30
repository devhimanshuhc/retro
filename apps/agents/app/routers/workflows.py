import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket
from pymongo.asynchronous.database import AsyncDatabase
from redis.asyncio import Redis

import config
from app.deps import get_db, get_prefix, get_redis
from app.models.api import ArtifactSummary, EditCreate, RunSummary, WorkflowCreate, WorkflowCreated
from app.models.events import Event
from app.models.messages import AgentMessage
from app.models.run import TERMINAL, RunStatus, WorkflowRun
from app.services import api_keys, events, limits, queues, state

router = APIRouter(prefix="/workflows", tags=["workflows"])


async def _rate_limit(request: Request, redis: Redis, prefix: str) -> None:
    """429 + Retry-After once this client has started RUNS_PER_WINDOW runs or edits in the window."""
    # shortcut: keyed by the socket's IP; behind a proxy every client shares one key, so read X-Forwarded-For
    # from a trusted proxy (or key by API user once there is auth) before deploying
    client = request.client.host if request.client else "unknown"
    if retry := await limits.hit(redis, f"{prefix}:ratelimit:runs:{client}", config.RUNS_PER_WINDOW, config.RUN_WINDOW_S):
        raise HTTPException(429, f"too many runs: {config.RUNS_PER_WINDOW} per {config.RUN_WINDOW_S // 60} min; "
                                 f"try again in {retry // 60 + 1} min", headers={"Retry-After": str(retry)})


async def _need_key(db: AsyncDatabase) -> None:
    """409 before any work starts when the agents have no model provider key (else every step would dead-letter)."""
    if await api_keys.active(db) is None:
        raise HTTPException(409, "Add an Anthropic or OpenAI API key in Connectors first")


@router.post("", status_code=202, response_model=WorkflowCreated)
async def create_workflow(body: WorkflowCreate, request: Request, db: AsyncDatabase = Depends(get_db),
                          redis: Redis = Depends(get_redis), prefix: str = Depends(get_prefix)):
    """Returns at once; the agents do the work. Follow it with GET /workflows/{id}.
    429 + Retry-After when this client has started RUNS_PER_WINDOW runs in the current window."""
    await _need_key(db)
    await _rate_limit(request, redis, prefix)
    run = await state.create_run(db, body.prompt)
    q = queues.open_queue(queues.SUPERVISOR, prefix=prefix)
    try:
        # shortcut: if Redis is down here the run stays `submitted` with no job; add a sweeper if that ever matters
        await queues.enqueue(q, AgentMessage(workflow_run_id=run.id))
    finally:
        await q.close()
    return WorkflowCreated(workflow_run_id=run.id)


@router.get("", response_model=list[RunSummary], response_model_by_alias=False)
async def list_workflows(status: RunStatus | None = None, limit: int = Query(50, ge=1, le=200),
                         db: AsyncDatabase = Depends(get_db)):
    return await state.list_runs(db, status, limit)


@router.get("/{run_id}", response_model=WorkflowRun, response_model_by_alias=False)
async def get_workflow(run_id: str, db: AsyncDatabase = Depends(get_db)):
    if run := await state.get_run(db, run_id):
        return run
    raise HTTPException(404, "workflow run not found")


@router.post("/{run_id}/cancel", response_model=RunSummary, response_model_by_alias=False)
async def cancel_workflow(run_id: str, db: AsyncDatabase = Depends(get_db), redis: Redis = Depends(get_redis)):
    """Stops the run after the step in progress: its output is dropped and no further step starts.
    409 if the run already finished."""
    # shortcut: an LLM call already in flight runs to the end (its tokens are spent); abort it via the SDK if that matters
    if (run := await state.cancel_run(db, run_id)) is None:
        if await state.get_run(db, run_id) is None:
            raise HTTPException(404, "workflow run not found")
        raise HTTPException(409, "workflow run already finished")
    await events.emit(db, redis, Event(type="run.status", workflow_run_id=run_id, data={"status": "canceled"}))
    return run


@router.post("/{run_id}/edit", status_code=202, response_model=RunSummary, response_model_by_alias=False)
async def edit_workflow(run_id: str, body: EditCreate, request: Request, db: AsyncDatabase = Depends(get_db),
                        redis: Redis = Depends(get_redis), prefix: str = Depends(get_prefix)):
    """Ask for a change to a finished report. The writer revises the current report (from the same findings) and the
    critic reviews it again. 409 unless the run is completed with a report. Counts toward the run rate limit."""
    await _need_key(db)
    await _rate_limit(request, redis, prefix)
    if (run := await state.request_edit(db, run_id, body.instruction)) is None:
        if await state.get_run(db, run_id) is None:
            raise HTTPException(404, "workflow run not found")
        raise HTTPException(409, "only a completed run with a report can be edited")
    q = queues.open_queue(queues.WRITE, prefix=prefix)
    try:
        await queues.enqueue(q, AgentMessage(workflow_run_id=run.id, revision=run.revision))
    finally:
        await q.close()
    await events.emit(db, redis, Event(type="run.status", workflow_run_id=run.id, data={"status": "working"}))
    return run


@router.websocket("/{run_id}/events")
async def run_events(ws: WebSocket, run_id: str, db: AsyncDatabase = Depends(get_db), redis: Redis = Depends(get_redis)):
    """Sends a run.snapshot first, then every event of the run; closes after the run's final run.status."""
    # CORS doesn't cover WebSockets, so check the browser's Origin here (non-browser clients send none)
    if (origin := ws.headers.get("origin")) is not None and origin not in config.WEB_ORIGINS:
        await ws.close(code=1008)
        return
    await ws.accept()
    async with redis.pubsub() as ps:
        await ps.subscribe(events.channel(run_id))
        run = await state.get_run(db, run_id)  # read after subscribing, so no event falls between the two
        if run is None:
            await ws.close(code=4404, reason="workflow run not found")
            return
        snapshot = Event(type="run.snapshot", workflow_run_id=run_id, data={"run": run.model_dump(mode="json")})
        await ws.send_text(snapshot.model_dump_json())
        if run.status in TERMINAL:
            await ws.close()
            return

        async def forward():
            while True:
                if (m := await ps.get_message(ignore_subscribe_messages=True, timeout=1.0)) is None:
                    continue
                await ws.send_text(m["data"].decode())
                ev = json.loads(m["data"])
                if ev["type"] == "run.status" and ev["data"].get("status") in TERMINAL:
                    return

        async def until_client_leaves():
            while True:
                await ws.receive_text()  # raises WebSocketDisconnect when the client goes

        tasks = [asyncio.create_task(forward()), asyncio.create_task(until_client_leaves())]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if tasks[0] in done and tasks[0].exception() is None:
            await ws.close()
