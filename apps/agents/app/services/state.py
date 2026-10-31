import re

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

import config
from app.models.api import ArtifactSummary, RunSummary
from app.models.run import TERMINAL, EditRequest, NextHop, RunUpdate, StepName, StepState, Turn, WorkflowRun, now


def connect(url: str = config.MONGO_URL) -> AsyncMongoClient:
    # tz_aware so datetimes come back as UTC-aware, matching what we store
    return AsyncMongoClient(url, tz_aware=True)


def runs(db: AsyncDatabase):
    return db["workflow_runs"]


async def ensure_indexes(db: AsyncDatabase) -> None:
    """Idempotent; the API runs it on startup (docs/schema.md, Indexes)."""
    await runs(db).create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    await runs(db).create_index([("created_at", DESCENDING)])
    await runs(db).create_index([("status", ASCENDING), ("updated_at", DESCENDING)])  # artifacts list
    await db["dead_letters"].create_index([("workflow_run_id", ASCENDING)])
    await db["dead_letters"].create_index([("created_at", DESCENDING)])


async def list_runs(db: AsyncDatabase, status: str | None = None, limit: int = 50) -> list[RunSummary]:
    fields = {k: 1 for k in RunSummary.model_fields if k != "id"}  # leaves out findings, reports and events
    docs = await runs(db).find({"status": status} if status else {}, fields,
                               sort=[("created_at", -1)], limit=limit).to_list()
    return [RunSummary.model_validate(d) for d in docs]


async def list_artifacts(db: AsyncDatabase, limit: int = 100) -> list[ArtifactSummary]:
    """Completed runs that have a report, newest first, with the report's own title."""
    docs = await runs(db).find(
        {"status": "completed", "revisions.0": {"$exists": True}},
        {"prompt": 1, "revision": 1, "created_at": 1, "updated_at": 1, "edits.revision": 1,
         "findings.sources.url": 1, "revisions": {"$slice": -1}},
        sort=[("updated_at", -1)], limit=limit,
    ).to_list()
    out = []
    for d in docs:
        md = d["revisions"][-1]["report_md"]
        title = m.group(1).strip() if (m := re.search(r"^#\s+(.+)$", md, re.M)) else d["prompt"][:80]
        urls = {s["url"] for f in d.get("findings", []) for s in f.get("sources", [])}
        out.append(ArtifactSummary(run_id=d["_id"], title=title, prompt=d["prompt"], revision=d["revisions"][-1]["revision"],
                                   sources=len(urls), edits=len(d.get("edits", [])), created_at=d["created_at"],
                                   updated_at=d["updated_at"]))
    return out


async def create_run(db: AsyncDatabase, prompt: str, document_ids: list[str] = (), web: bool = True) -> WorkflowRun:
    run = WorkflowRun(prompt=prompt, turns=[Turn(role="user", text=prompt)], document_ids=list(document_ids), web=web)
    await runs(db).insert_one(run.model_dump(by_alias=True))
    return run


async def get_run(db: AsyncDatabase, run_id: str) -> WorkflowRun | None:
    doc = await runs(db).find_one({"_id": run_id})
    return WorkflowRun.model_validate(doc) if doc else None


async def update_run(db: AsyncDatabase, run_id: str, **fields) -> WorkflowRun | None:
    """Set the given fields atomically; returns the updated run, or None if it doesn't exist."""
    changes = RunUpdate(**fields).model_dump(exclude_unset=True)
    doc = await runs(db).find_one_and_update(
        {"_id": run_id},
        {"$set": {**changes, "updated_at": now()}},
        return_document=ReturnDocument.AFTER,
    )
    return WorkflowRun.model_validate(doc) if doc else None


async def cancel_run(db: AsyncDatabase, run_id: str) -> WorkflowRun | None:
    """Atomically cancel a run that isn't finished. None if it's missing or already finished. Workers then skip
    its queued jobs (claim_step) and drop the output of a step in progress (finish_step)."""
    doc = await runs(db).find_one_and_update(
        {"_id": run_id, "status": {"$nin": list(TERMINAL)}},
        {"$set": {"status": "canceled", "updated_at": now()}},
        return_document=ReturnDocument.AFTER,
    )
    return WorkflowRun.model_validate(doc) if doc else None


async def request_edit(db: AsyncDatabase, run_id: str, instruction: str) -> WorkflowRun | None:
    """Reopen a completed run for a follow-up change: bump the revision, record the request and set it working,
    in one conditional write (so two requests can't both take the same revision). None if the run isn't
    completed with a report, or changed under us."""
    run = await get_run(db, run_id)
    if run is None or run.status != "completed" or not run.revisions:
        return None
    rev = run.revision + 1
    t = now()
    doc = await runs(db).find_one_and_update(
        {"_id": run_id, "status": "completed", "revision": run.revision},
        {"$set": {"status": "working", "revision": rev, "updated_at": t},
         "$push": {"edits": EditRequest(revision=rev, instruction=instruction, created_at=t).model_dump()}},
        return_document=ReturnDocument.AFTER,
    )
    return WorkflowRun.model_validate(doc) if doc else None


async def add_message(db: AsyncDatabase, run_id: str, text: str) -> WorkflowRun | None:
    """A follow-up message on a finished chat (no research started): record it and set the run working, in one
    conditional write. None if the run isn't a finished chat."""
    t = now()
    doc = await runs(db).find_one_and_update(
        {"_id": run_id, "status": "completed", "intent": {"$in": ["chat", "decline"]}},
        {"$set": {"status": "working", "updated_at": t}, "$push": {"turns": Turn(role="user", text=text, created_at=t).model_dump()}},
        return_document=ReturnDocument.AFTER,
    )
    return WorkflowRun.model_validate(doc) if doc else None


def user_turn(run: WorkflowRun) -> int:
    """The router's revision for the latest message: 0 for the first, 1 for the next…"""
    return max(0, sum(t.role == "user" for t in run.turns) - 1)


async def claim_step(db: AsyncDatabase, run_id: str, step: StepName, revision: int) -> WorkflowRun | None:
    """Atomically mark `step` working for `revision`. Returns None when the job must be skipped:
    run missing or finished, message is for an older revision, or this step is already done for it.
    A `working` step doesn't block, so a retry after a crash can take the step back."""
    t = now()
    doc = await runs(db).find_one_and_update(
        {
            "_id": run_id,
            "status": {"$nin": list(TERMINAL)},
            "revision": {"$lte": revision},
            "$nor": [{f"steps.{step}.status": "done", f"steps.{step}.revision": {"$gte": revision}}],
        },
        {"$set": {
            f"steps.{step}": StepState(status="working", revision=revision, started_at=t).model_dump(),
            "status": "working",
            "updated_at": t,
        }},
        return_document=ReturnDocument.AFTER,
    )
    return WorkflowRun.model_validate(doc) if doc else None


async def finish_step(db: AsyncDatabase, run_id: str, step: StepName, revision: int, /,
                      next_hop: NextHop | None = None, **fields) -> WorkflowRun | None:  # `/`: fields may hold the run's own `revision`
    """Mark `step` done, apply the run updates and record the next hop (outbox) in one write,
    so a crash leaves either all or none. Returns None if the step isn't ours to finish any more."""
    changes = RunUpdate(**fields).model_dump(exclude_unset=True)
    t = now()
    doc = await runs(db).find_one_and_update(
        # a run canceled (or failed) meanwhile stays that way: the step's outputs and next hop are dropped
        {"_id": run_id, "status": {"$nin": list(TERMINAL)},
         f"steps.{step}.status": "working", f"steps.{step}.revision": revision},
        {"$set": {**changes, f"steps.{step}.status": "done", f"steps.{step}.finished_at": t,
                  f"steps.{step}.next": next_hop.model_dump() if next_hop else None, "updated_at": t}},
        return_document=ReturnDocument.AFTER,
    )
    return WorkflowRun.model_validate(doc) if doc else None
