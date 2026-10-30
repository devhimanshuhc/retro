"""Live status: sub-step progress events, stored events, worker heartbeats, cancel."""
import asyncio

import pytest
from redis.asyncio import Redis

import config
from app.agents.base import Actor, Outcome
from app.deps import get_redis
from app.main import app
from app.models.messages import AgentMessage
from app.services import progress, queues, state, workers


@pytest.fixture
async def redis():
    r = Redis.from_url(config.REDIS_URL)
    yield r
    await r.aclose()


@pytest.fixture
async def actor_factory(db, prefix):
    made = []

    def make(handler, queue=queues.WRITE):
        made.append(a := Actor(queue, handler, db, prefix=prefix))
        return a
    yield make
    for a in made:
        for q in a._out.values():
            await q.obliterate(force=True)
            await q.close()


class FakeJob:
    def __init__(self, data):
        self.data, self.attemptsMade, self.opts, self.id = data, 0, {"attempts": 3}, "j"


async def test_progress_is_stored_on_the_run_and_the_worker_shows_it(db, prefix, redis, actor_factory):
    seen = {}

    async def handler(run, msg):
        await progress.report("drafting", "Writing draft 1", words=10)
        seen["during"] = await workers.list_workers(redis, prefix)
        return Outcome(run_updates={"status": "completed"})

    actor = actor_factory(handler)
    run = await state.create_run(db, "p")
    assert await actor._job(FakeJob(AgentMessage(workflow_run_id=run.id).model_dump())) == "done"

    stored = (await state.get_run(db, run.id)).events
    assert [e["type"] for e in stored] == ["step.started", "step.progress", "step.done", "run.status"]
    assert stored[1]["data"] == {"revision": 0, "phase": "drafting", "detail": "Writing draft 1", "words": 10}
    assert len({e["id"] for e in stored}) == 4
    [w] = seen["during"]
    assert (w.agent, w.state, w.run_id, w.activity) == ("write", "busy", run.id, "Writing draft 1")
    [w] = await workers.list_workers(redis, prefix)
    assert (w.state, w.run_id, w.jobs_done) == ("idle", None, 1)


async def test_heartbeat_disappears_on_clean_stop(db, prefix, redis, actor_factory):
    actor = actor_factory(lambda run, msg: None)
    stop = asyncio.Event()
    task = asyncio.create_task(actor.run(stop))
    async with asyncio.timeout(5):
        while not await workers.list_workers(redis, prefix):
            await asyncio.sleep(0.05)
    stop.set()
    await task
    assert await workers.list_workers(redis, prefix) == []


async def test_canceled_run_drops_the_step_in_progress(db, prefix, actor_factory):
    run = await state.create_run(db, "p")

    async def handler(r, msg):
        await state.cancel_run(db, r.id)  # the user cancels while this step runs
        return Outcome(next_queue=queues.CRITIC, run_updates={"warnings": ["x"]})

    actor = actor_factory(handler)
    assert await actor.process(AgentMessage(workflow_run_id=run.id).model_dump()) == "skipped"
    after = await state.get_run(db, run.id)
    assert after.status == "canceled" and after.warnings == [] and after.steps["write"].status == "working"
    assert await actor._queue(queues.CRITIC).getJobCounts("wait") == {"wait": 0}  # no next hop sent


async def test_cancel_endpoint(api, db, redis):
    app.dependency_overrides[get_redis] = lambda: redis
    run = await state.create_run(db, "p")
    r = await api.post(f"/workflows/{run.id}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "canceled"
    assert [e["data"] for e in (await state.get_run(db, run.id)).events] == [{"status": "canceled"}]
    assert (await api.post(f"/workflows/{run.id}/cancel")).status_code == 409
    assert (await api.post("/workflows/nope/cancel")).status_code == 404


async def test_workers_endpoint(api, prefix, redis, actor_factory):
    app.dependency_overrides[get_redis] = lambda: redis
    await actor_factory(lambda r, m: None, queues.CRITIC)._presence()
    await actor_factory(lambda r, m: None, queues.SUPERVISOR)._presence()
    body = (await api.get("/workers")).json()
    assert [w["agent"] for w in body] == ["supervisor", "critic"] and body[0]["state"] == "idle"
