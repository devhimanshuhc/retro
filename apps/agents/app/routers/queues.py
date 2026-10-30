from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.deps import get_prefix, get_redis
from app.models.api import JOB_STATES, WorkerInfo
from app.services import queues, workers

router = APIRouter(tags=["queues"])


@router.get("/workers", response_model=list[WorkerInfo])
async def list_workers(redis: Redis = Depends(get_redis), prefix: str = Depends(get_prefix)):
    """Live agent processes (heartbeat within the last 15s) and what each is doing right now."""
    return await workers.list_workers(redis, prefix)


@router.get("/queues", response_model=dict[str, dict[str, int]])
async def queue_counts(prefix: str = Depends(get_prefix)):
    """Job counts per queue, e.g. {"agent.write": {"waiting": 2, "active": 1, ...}}."""
    out = {}
    for name in queues.ALL_QUEUES:
        q = queues.open_queue(name, prefix=prefix)
        try:
            counts = await q.getJobCounts("wait", *JOB_STATES[1:])
        finally:
            await q.close()
        out[name] = {"waiting": counts["wait"], **{s: counts[s] for s in JOB_STATES[1:]}}
    return out
