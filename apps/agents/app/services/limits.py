"""Request rate limits in Redis: a fixed window per key, shared by every API process."""
from redis.asyncio import Redis


async def hit(redis: Redis, key: str, limit: int, window_s: int) -> int | None:
    """Count one request. Returns the seconds until the window resets when this one is over the limit, else None."""
    async with redis.pipeline(transaction=True) as pipe:
        # NX: the window starts at the first request; one transaction, so a crash can't leave a key without expiry
        count, _, ttl = await pipe.incr(key).expire(key, window_s, nx=True).ttl(key).execute()
    return max(1, ttl) if count > limit else None
