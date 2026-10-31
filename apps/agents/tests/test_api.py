import asyncio
import time

import pytest

from app.services import queues, state


@pytest.fixture
async def cleanup_queues(prefix):
    yield
    for name in queues.ALL_QUEUES:
        q = queues.open_queue(name, prefix=prefix)
        await q.obliterate(force=True)
        await q.close()


async def test_create_returns_202_at_once_and_enqueues(api, db, prefix, cleanup_queues):
    t = time.monotonic()
    r = await api.post("/workflows", json={"prompt": "Write a report on Nvidia Q3"})
    assert r.status_code == 202 and time.monotonic() - t < 1  # no waiting on agents
    run_id = r.json()["workflow_run_id"]
    assert (await state.get_run(db, run_id)).status == "submitted"

    counts = (await api.get("/queues")).json()
    assert counts["agent.router"]["waiting"] == 1 and set(counts) == set(queues.ALL_QUEUES)
    assert set(counts["agent.write"]) == {"waiting", "active", "delayed", "failed", "completed"}

    run = (await api.get(f"/workflows/{run_id}")).json()
    assert run["id"] == run_id and run["prompt"] == "Write a report on Nvidia Q3" and run["revisions"] == []


@pytest.mark.parametrize("body", [{}, {"prompt": ""}, {"prompt": "x" * 4001}, {"prompt": "x", "admin": True}])
async def test_create_rejects_bad_input(api, body):
    assert (await api.post("/workflows", json=body)).status_code == 422


async def test_get_missing_run_is_404(api):
    assert (await api.get("/workflows/nope")).status_code == 404


async def test_list_is_newest_first_and_filters_by_status(api, db):
    a = await state.create_run(db, "a")
    await asyncio.sleep(0.005)  # created_at has ms resolution
    b = await state.create_run(db, "b")
    await state.update_run(db, a.id, status="failed")
    rows = (await api.get("/workflows")).json()
    assert [r["id"] for r in rows] == [b.id, a.id] and "findings" not in rows[0]
    assert [r["id"] for r in (await api.get("/workflows", params={"status": "failed"})).json()] == [a.id]
    assert (await api.get("/workflows", params={"status": "bogus"})).status_code == 422


async def test_indexes_are_idempotent(db):
    await state.ensure_indexes(db)
    await state.ensure_indexes(db)
    assert "status_1_created_at_-1" in await state.runs(db).index_information()
