"""Kill a real worker process (SIGKILL, no cleanup) mid-job and check the run still finishes exactly once."""
import asyncio
import sys
from pathlib import Path

import pytest

from app.agents import critic, research, supervisor
from app.agents.base import Actor
from app.models.messages import AgentMessage
from app.services import dlq, llm, queues, sources, state
from tests.fakes import fake_fetch, fake_llm

LOCK_MS = 1500  # production keeps BullMQ's 30s; short here so recovery takes seconds
ROOT = Path(__file__).parent.parent


@pytest.fixture
async def cleanup_queues(prefix):
    yield
    for name in queues.ALL_QUEUES:
        q = queues.open_queue(name, prefix=prefix)
        await q.obliterate(force=True)
        await q.close()


async def writer_process(prefix, db, delay):
    return await asyncio.create_subprocess_exec(
        sys.executable, "-m", "tests.chaos_worker", "writer", prefix, db.name, str(LOCK_MS), str(delay),
        cwd=ROOT, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)


async def kill_once_started(proc):
    async with asyncio.timeout(20):
        while b"start run=" not in (await proc.stdout.readline()):
            pass
    proc.kill()  # SIGKILL: no finally blocks, no lock release
    await proc.wait()


async def until(predicate, timeout=30):
    async with asyncio.timeout(timeout):
        while not await predicate():
            await asyncio.sleep(0.1)


@pytest.fixture
async def pipeline(db, prefix, cleanup_queues, monkeypatch):
    """Supervisor, research and critic in-process; the writer runs as separate processes the test kills."""
    monkeypatch.setattr(llm, "complete", fake_llm([]))
    monkeypatch.setattr(sources, "fetch", fake_fetch)
    stop = asyncio.Event()
    actors = [Actor(q, h, db, prefix=prefix, lock_ms=LOCK_MS) for q, h in
              ((queues.SUPERVISOR, supervisor.handle), (queues.RESEARCH, research.handle), (queues.CRITIC, critic.handle))]
    tasks = [asyncio.create_task(a.run(stop)) for a in actors]
    entry = queues.open_queue(queues.SUPERVISOR, prefix=prefix)
    procs = []
    run = await state.create_run(db, "Write a report on Nvidia Q3")
    await queues.enqueue(entry, AgentMessage(workflow_run_id=run.id))
    yield run, procs
    for p in procs:
        if p.returncode is None:
            p.kill()
            await p.wait()
    stop.set()
    await asyncio.gather(*tasks)
    await entry.close()


async def test_killed_writer_run_still_finishes_once(db, prefix, pipeline):
    run, procs = pipeline
    procs.append(doomed := await writer_process(prefix, db, delay=60))
    await kill_once_started(doomed)
    procs.append(await writer_process(prefix, db, delay=0.2))  # takes the stalled job back after the lock expires

    await until(lambda: _status(db, run.id, "completed"))
    done = await state.get_run(db, run.id)
    assert [r.revision for r in done.revisions] == [0]  # exactly one draft, no duplicate from the dead worker
    assert done.revisions[0].critique.passed and done.steps["write"].status == "done"
    assert await dlq.list_dead_letters(db) == []


async def test_job_killed_twice_is_dead_lettered(db, prefix, pipeline):
    run, procs = pipeline
    for _ in range(2):  # maxStalledCount is 1: the second stall fails the job inside BullMQ, bypassing the processor
        procs.append(p := await writer_process(prefix, db, delay=60))
        await kill_once_started(p)
    procs.append(await writer_process(prefix, db, delay=0.2))

    await until(lambda: _status(db, run.id, "failed"))
    [dl] = await dlq.list_dead_letters(db, run.id)
    assert dl.queue == queues.WRITE and "stalled more than allowable limit" in dl.error


async def _status(db, run_id, status):
    return (await state.get_run(db, run_id)).status == status
