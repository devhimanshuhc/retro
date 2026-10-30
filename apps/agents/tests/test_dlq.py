import asyncio
from types import SimpleNamespace

import pytest
from bullmq import UnrecoverableError

import config
from app.agents.base import Actor, Outcome
from app.models.messages import AgentMessage
from app.services import dlq, llm, queues, state


@pytest.fixture
async def cleanup_queues(prefix):
    yield
    for name in queues.ALL_QUEUES:
        q = queues.open_queue(name, prefix=prefix)
        await q.obliterate(force=True)
        await q.close()


def fake_job(run_id, attempts_made, attempts=3):
    return SimpleNamespace(id=f"{run_id}-research-0", data={"workflow_run_id": run_id, "revision": 0},
                           attemptsMade=attempts_made, opts={"attempts": attempts})


async def boom(run, msg):
    llm.last_output.set('{"objectives": "not a list"}')
    raise RuntimeError(f"model said no, key {config.ANTHROPIC_API_KEY}")


async def dlq_count(actor):
    return (await actor._queue(queues.DLQ).getJobCounts("wait"))["wait"]


async def test_only_the_last_attempt_is_dead_lettered(db, prefix, cleanup_queues, monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-ant-secret")
    actor = Actor(queues.RESEARCH, boom, db, prefix=prefix)
    run = await state.create_run(db, "p")
    with pytest.raises(RuntimeError):
        await actor._job(fake_job(run.id, attempts_made=1))  # attempt 2 of 3: BullMQ will retry
    assert await dlq.list_dead_letters(db) == [] and (await state.get_run(db, run.id)).status == "working"

    with pytest.raises(RuntimeError):
        await actor._job(fake_job(run.id, attempts_made=2))  # attempt 3 of 3
    [dl] = await dlq.list_dead_letters(db, run.id)
    assert (dl.queue, dl.attempts, dl.revision) == (queues.RESEARCH, 3, 0)
    assert "model said no" in dl.error and "sk-ant-secret" not in dl.error + dl.stack and "[redacted]" in dl.error
    assert dl.raw_output == '{"objectives": "not a list"}'
    assert (await state.get_run(db, run.id)).status == "failed" and await dlq_count(actor) == 1
    for q in actor._out.values():
        await q.close()


async def test_unrecoverable_is_dead_lettered_at_once(db, prefix, cleanup_queues):
    actor = Actor(queues.RESEARCH, boom, db, prefix=prefix)
    with pytest.raises(UnrecoverableError):
        await actor._job(SimpleNamespace(id="x", data={"bad": 1}, attemptsMade=0, opts={"attempts": 3}))
    [dl] = await dlq.list_dead_letters(db)
    assert dl.workflow_run_id is None and "bad message" in dl.error
    for q in actor._out.values():
        await q.close()


async def test_dead_letter_then_replay_finishes_the_run(db, prefix, cleanup_queues, api):
    broken = [True]

    async def handler(run, msg):
        if broken[0]:
            raise UnrecoverableError("bad plan")  # skips retries, straight to the DLQ
        return Outcome()

    stop = asyncio.Event()
    actor = Actor(queues.RESEARCH, handler, db, prefix=prefix)
    task = asyncio.create_task(actor.run(stop))
    q = queues.open_queue(queues.RESEARCH, prefix=prefix)
    try:
        run = await state.create_run(db, "p")
        await queues.enqueue(q, AgentMessage(workflow_run_id=run.id))
        async with asyncio.timeout(10):
            while (await state.get_run(db, run.id)).status != "failed" or not await q.getJobCounts("failed") == {"failed": 1}:
                await asyncio.sleep(0.05)
        [dl] = (await api.get("/dead-letters", params={"workflow_run_id": run.id})).json()
        assert dl["error"] == "UnrecoverableError: bad plan" and dl["replayed_at"] is None
        assert (await api.get(f"/dead-letters/{dl['id']}")).json()["id"] == dl["id"]

        broken[0] = False  # the bug is fixed; replay
        r = await api.post(f"/dead-letters/{dl['id']}/replay")
        assert r.status_code == 202 and r.json()["replayed_at"]
        async with asyncio.timeout(10):
            while (s := (await state.get_run(db, run.id)).steps["research"]).status != "done":
                await asyncio.sleep(0.05)
        assert (await state.get_run(db, run.id)).status == "working" and await dlq_count(actor) == 0
        assert (await api.post(f"/dead-letters/{dl['id']}/replay")).status_code == 409  # once only
    finally:
        stop.set()
        await task
        await q.close()


async def test_unknown_dead_letter_is_404(api):
    assert (await api.get("/dead-letters/nope")).status_code == 404
    assert (await api.post("/dead-letters/nope/replay")).status_code == 404
