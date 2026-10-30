"""Dead letters: a trace in Mongo for debugging, a copy on agent.dlq for queue depth, and replay."""
import re
import traceback

from bullmq import Job, Queue
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

import config
from app.models.dead_letter import DeadLetter
from app.models.messages import AgentMessage
from app.models.run import TERMINAL, now
from app.services import queues, state

MAX_RAW = 20_000  # chars of raw LLM output kept per trace


def dead_letters(db: AsyncDatabase):
    return db["dead_letters"]


KEY = re.compile(r"sk-[A-Za-z0-9_\-]{16,}")  # any Anthropic or OpenAI key, wherever it came from


def redact(text: str | None) -> str | None:
    key = config.ANTHROPIC_API_KEY
    text = text.replace(key, "[redacted]") if text and key else text
    return KEY.sub("[redacted]", text) if text else text


async def dead_letter(db: AsyncDatabase, dlq: Queue, queue_name: str, job: Job, err: BaseException,
                      raw_output: str | None = None) -> DeadLetter:
    """Save the trace, copy the job to the DLQ and mark the run failed (unless it already finished)."""
    data = dict(job.data or {})
    run_id = data.get("workflow_run_id") if isinstance(data.get("workflow_run_id"), str) else None
    dl = DeadLetter(queue=queue_name, job_id=job.id, workflow_run_id=run_id,
                    revision=data.get("revision") if isinstance(data.get("revision"), int) else None, data=data,
                    error=redact(f"{type(err).__name__}: {err}"),
                    stack=redact("".join(traceback.format_exception(err))),
                    raw_output=redact(raw_output[:MAX_RAW] if raw_output else None), attempts=job.attemptsMade + 1)
    await dead_letters(db).insert_one(dl.model_dump(by_alias=True))
    await dlq.add("dead", {"dead_letter_id": dl.id, "queue": queue_name, **data},
                  {"jobId": dl.id, "removeOnComplete": True})
    if run_id:
        await state.runs(db).update_one({"_id": run_id, "status": {"$nin": list(TERMINAL)}},
                                        {"$set": {"status": "failed", "updated_at": now()}})
    return dl


async def list_dead_letters(db: AsyncDatabase, workflow_run_id: str | None = None, limit: int = 50) -> list[DeadLetter]:
    query = {"workflow_run_id": workflow_run_id} if workflow_run_id else {}
    docs = await dead_letters(db).find(query, sort=[("created_at", -1)], limit=limit).to_list()
    return [DeadLetter.model_validate(d) for d in docs]


async def get_dead_letter(db: AsyncDatabase, dl_id: str) -> DeadLetter | None:
    doc = await dead_letters(db).find_one({"_id": dl_id})
    return DeadLetter.model_validate(doc) if doc else None


class NotReplayable(Exception):
    pass


async def replay(db: AsyncDatabase, dl_id: str, redis_url: str = config.REDIS_URL, prefix: str = "bull") -> DeadLetter | None:
    """Reopen the run and retry the original job with fresh attempts. None if no such dead letter."""
    dl = await get_dead_letter(db, dl_id)
    if dl is None:
        return None
    if dl.replayed_at:
        raise NotReplayable("already replayed")
    if dl.workflow_run_id is None:
        raise NotReplayable("malformed message: nothing to replay")
    # Reopening is the atomic guard: only one replay can move the run from failed back to working.
    if not (await state.runs(db).update_one({"_id": dl.workflow_run_id, "status": "failed"},
                                            {"$set": {"status": "working", "updated_at": now()}})).modified_count:
        raise NotReplayable("run is not failed")
    agent_q, dlq = queues.open_queue(dl.queue, redis_url, prefix), queues.open_queue(queues.DLQ, redis_url, prefix)
    try:
        if job := await agent_q.getJob(dl.job_id):
            await job.retry("failed", {"resetAttemptsMade": True})
        else:  # failed jobs expire after removeOnFail (7 days); the job id is free again
            await queues.enqueue(agent_q, AgentMessage.model_validate(dl.data))
        if copy := await dlq.getJob(dl.id):
            await copy.remove()
    finally:
        await agent_q.close()
        await dlq.close()
    doc = await dead_letters(db).find_one_and_update({"_id": dl.id}, {"$set": {"replayed_at": now()}},
                                                     return_document=ReturnDocument.AFTER)
    return DeadLetter.model_validate(doc)
