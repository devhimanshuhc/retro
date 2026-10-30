"""Worker presence: each Actor process keeps a Redis key `<prefix>:workers:<id>` alive with what it is doing.
A killed worker disappears once its key expires (TTL_S), so the dashboard shows who is really up."""
from redis.asyncio import Redis

from app.models.api import WorkerInfo

HEARTBEAT_S = 5
TTL_S = 15  # 3 missed heartbeats
ORDER = {"supervisor": 0, "research": 1, "write": 2, "critic": 3}


def key(prefix: str, worker_id: str) -> str:
    return f"{prefix}:workers:{worker_id}"


async def beat(redis: Redis, prefix: str, info: WorkerInfo) -> None:
    await redis.set(key(prefix, info.id), info.model_dump_json(), ex=TTL_S)


async def leave(redis: Redis, prefix: str, worker_id: str) -> None:
    await redis.delete(key(prefix, worker_id))


async def list_workers(redis: Redis, prefix: str) -> list[WorkerInfo]:
    keys = [k async for k in redis.scan_iter(match=key(prefix, "*"), count=200)]
    vals = await redis.mget(keys) if keys else []
    infos = [WorkerInfo.model_validate_json(v) for v in vals if v]  # a key can expire between scan and get
    return sorted(infos, key=lambda w: (ORDER[w.agent], w.started_at, w.id))
