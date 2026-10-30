import asyncio
import time

import pytest

import config
from bullmq import UnrecoverableError

from app.agents import critic, research, supervisor, writer
from app.agents.base import Actor, Outcome
from app.models.messages import AgentMessage
from app.services import llm, queues, sources, state
from tests.fakes import GOOD_REPORT, fake_fetch, fake_llm


@pytest.fixture
async def cleanup_queues(prefix):
    yield
    for name in queues.ALL_QUEUES:
        q = queues.open_queue(name, prefix=prefix)
        await q.obliterate(force=True)
        await q.close()


async def test_duplicate_delivery_runs_handler_once_and_enqueues_once(db, prefix, cleanup_queues):
    calls = []

    async def handler(run, msg):
        calls.append(run.id)
        return Outcome(next_queue=queues.WRITE)

    actor = Actor(queues.RESEARCH, handler, db, prefix=prefix)
    run = await state.create_run(db, "p")
    msg = AgentMessage(workflow_run_id=run.id).model_dump()

    assert await actor.process(msg) == "done"
    assert await actor.process(msg) == "skipped"  # BullMQ is at-least-once
    assert calls == [run.id]
    assert await actor._queue(queues.WRITE).getJobCounts("wait") == {"wait": 1}
    assert (await state.get_run(db, run.id)).steps["research"].status == "done"
    for q in actor._out.values():
        await q.close()


async def test_crash_after_enqueue_is_safe_to_retry(db, prefix, cleanup_queues, monkeypatch):
    # handler succeeds, but the process dies before the step is marked done
    async def handler(run, msg):
        return Outcome(next_queue=queues.WRITE)

    actor = Actor(queues.RESEARCH, handler, db, prefix=prefix)
    run = await state.create_run(db, "p")
    msg = AgentMessage(workflow_run_id=run.id).model_dump()

    async def crash(*a, **k):
        raise RuntimeError("crash")

    with monkeypatch.context() as m:
        m.setattr(state, "finish_step", crash)
        with pytest.raises(RuntimeError):
            await actor.process(msg)

    assert await actor.process(msg) == "done"  # the retry takes the step back
    assert await actor._queue(queues.WRITE).getJobCounts("wait") == {"wait": 1}  # no duplicate next message
    for q in actor._out.values():
        await q.close()


async def test_crash_after_save_before_send_is_healed_by_redelivery(db, prefix, cleanup_queues, monkeypatch):
    async def handler(run, msg):
        return Outcome(next_queue=queues.WRITE)

    actor = Actor(queues.RESEARCH, handler, db, prefix=prefix)
    run = await state.create_run(db, "p")
    msg = AgentMessage(workflow_run_id=run.id).model_dump()

    async def crash(*a, **k):
        raise RuntimeError("crash")

    with monkeypatch.context() as m:
        m.setattr(actor, "_send", crash)
        with pytest.raises(RuntimeError):
            await actor.process(msg)  # step saved as done, next message never sent

    assert await actor.process(msg) == "skipped"  # the redelivery doesn't redo the work...
    assert await actor._queue(queues.WRITE).getJobCounts("wait") == {"wait": 1}  # ...but sends the lost message
    assert await actor.process(msg) == "skipped"
    assert await actor._queue(queues.WRITE).getJobCounts("wait") == {"wait": 1}  # once
    for q in actor._out.values():
        await q.close()


async def test_malformed_message_is_unrecoverable(db, prefix):
    actor = Actor(queues.RESEARCH, research.handle, db, prefix=prefix)
    with pytest.raises(UnrecoverableError):
        await actor.process({"workflow_run_id": "r1", "report": "big payload"})


async def test_pipeline_completes_through_four_actors(db, prefix, cleanup_queues, monkeypatch):
    calls = []  # first draft has no citations, so the critic sends it back once
    monkeypatch.setattr(llm, "complete", fake_llm(calls, reports=("## Revenue\nno cites", GOOD_REPORT)))
    monkeypatch.setattr(sources, "fetch", fake_fetch)
    stop = asyncio.Event()
    actors = [
        Actor(queues.SUPERVISOR, supervisor.handle, db, prefix=prefix),
        Actor(queues.RESEARCH, research.handle, db, prefix=prefix),
        Actor(queues.WRITE, writer.handle, db, prefix=prefix),
        Actor(queues.CRITIC, critic.handle, db, prefix=prefix),
    ]
    tasks = [asyncio.create_task(a.run(stop)) for a in actors]
    entry = queues.open_queue(queues.SUPERVISOR, prefix=prefix)
    try:
        run = await state.create_run(db, "Write a report on Nvidia Q3")
        await queues.enqueue(entry, AgentMessage(workflow_run_id=run.id))
        async with asyncio.timeout(15):
            while (run := await state.get_run(db, run.id)).status != "completed":
                await asyncio.sleep(0.1)
        assert {k: v.status for k, v in run.steps.items()} == {
            "supervisor": "done", "research": "done", "write": "done", "critic": "done",
        }
        assert run.revision == 1 and [r.critique.passed for r in run.revisions] == [False, True]
        assert [c[0] for c in calls] == ["supervisor", "research", "research", "write", "write", "critic"]
        assert run.usage["write"].input_tokens == 20 and run.plan and len(run.findings) == 2
        assert run.usage["research"].input_tokens == 20  # search + write calls
    finally:
        stop.set()
        await asyncio.gather(*tasks)
        await entry.close()


async def test_worker_socket_timeout_outlasts_bullmq_block(prefix):
    from bullmq import Worker
    from app.agents.base import worker_url
    w = Worker("probe", lambda job, token: None, {"connection": worker_url(config.REDIS_URL), "prefix": prefix,
                                                  "autorun": False})
    try:
        timeout = w.backend.bclient.connection_pool.connection_kwargs["socket_timeout"]
        assert timeout > w.maximumBlockTimeout  # else idle workers miss jobs for ~20s (see worker_url)
    finally:
        await w.close()


async def test_429_pauses_every_worker_of_the_agent_then_retries(db, prefix, cleanup_queues):
    pause_ms, started, hit = 3000, [], []

    async def handler(run, msg):
        started.append((run.id, time.monotonic()))
        if not hit:  # fake 429 on the very first call
            hit.append(time.monotonic())
            raise llm.RateLimited("fake 429", retry_after_ms=pause_ms)
        return Outcome()

    stop = asyncio.Event()
    actors = [Actor(queues.RESEARCH, handler, db, prefix=prefix) for _ in range(2)]  # two workers, one agent
    tasks = [asyncio.create_task(a.run(stop)) for a in actors]
    q = queues.open_queue(queues.RESEARCH, prefix=prefix)
    try:
        a, b = await state.create_run(db, "a"), await state.create_run(db, "b")
        await queues.enqueue(q, AgentMessage(workflow_run_id=a.id))
        async with asyncio.timeout(5):
            while not hit:
                await asyncio.sleep(0.02)
        assert await q.getRateLimitTtl() > 0
        await queues.enqueue(q, AgentMessage(workflow_run_id=b.id))  # the idle second worker must not take it
        async with asyncio.timeout(15):
            while not all([(s := (await state.get_run(db, r.id)).steps.get("research")) and s.status == "done"
                           for r in (a, b)]):
                await asyncio.sleep(0.1)
        later = started[1:]
        assert sorted(r for r, _ in later) == sorted([a.id, b.id])  # a retried once, b ran once
        assert all(t - hit[0] >= pause_ms / 1000 - 0.1 for _, t in later)  # nobody started during the pause
    finally:
        stop.set()
        await asyncio.gather(*tasks)
        await q.close()
