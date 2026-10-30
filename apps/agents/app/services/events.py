"""Live progress: `emit` stores an event on the run (so a reload can rebuild the timeline) and publishes it on
Redis `workflow:{id}`, which the API forwards to WebSocket clients. Both are best effort."""
import logging

from pymongo.asynchronous.database import AsyncDatabase
from redis.asyncio import Redis

from app.models.events import Event
from app.services import state

log = logging.getLogger("events")
MAX_EVENTS = 500  # per run; older events drop off the stored list (live clients still saw them)


def channel(run_id: str) -> str:
    return f"workflow:{run_id}"


async def publish(redis: Redis, event: Event) -> None:
    """Best effort: a lost event must never fail the job that caused it."""
    try:
        await redis.publish(channel(event.workflow_run_id), event.model_dump_json())
    except Exception as e:
        log.warning("publish %s for run=%s failed: %r", event.type, event.workflow_run_id, e)


async def emit(db: AsyncDatabase, redis: Redis, event: Event) -> None:
    """Store, then publish: a client that subscribes and then reads the run sees the event at least once
    (twice at worst, deduped by event id), never zero times."""
    try:
        await state.runs(db).update_one({"_id": event.workflow_run_id}, {"$push": {"events": {
            "$each": [event.model_dump(mode="json")], "$slice": -MAX_EVENTS}}})
    except Exception as e:
        log.warning("store %s for run=%s failed: %r", event.type, event.workflow_run_id, e)
    await publish(redis, event)
