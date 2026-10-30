import asyncio
import json

import pytest
import redis
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from starlette.websockets import WebSocketDisconnect

import config
from app.agents.base import Actor, Outcome
from app.main import app
from app.models.events import Event
from app.models.messages import AgentMessage
from app.services import events, queues, state


@pytest.fixture
def ws_client(db, monkeypatch):
    """TestClient runs the app (and its lifespan) in its own thread and loop, against the test database."""
    monkeypatch.setattr(config, "MONGO_DB", db.name)
    app.dependency_overrides = {}
    with TestClient(app) as c:
        yield c


def publish(run_id, type_, **data):
    with redis.Redis.from_url(config.REDIS_URL) as r:  # sync: the test thread blocks on the socket meanwhile
        r.publish(events.channel(run_id), Event(type=type_, workflow_run_id=run_id, agent="write", data=data).model_dump_json())


async def test_ws_sends_snapshot_then_events_then_closes_on_finish(db, ws_client):
    run = await state.create_run(db, "p")
    with ws_client.websocket_connect(f"/workflows/{run.id}/events",
                                     headers={"origin": config.WEB_ORIGINS[0]}) as ws:
        snap = ws.receive_json()
        assert snap["type"] == "run.snapshot" and snap["data"]["run"]["id"] == run.id and snap["agent"] is None
        publish(run.id, "step.started", revision=0)
        ev = ws.receive_json()
        assert (ev["type"], ev["agent"], ev["data"], ev["workflow_run_id"]) == ("step.started", "write", {"revision": 0}, run.id)
        publish(run.id, "run.status", status="completed")
        assert ws.receive_json()["data"] == {"status": "completed"}
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()  # the server closes once the run is over


async def test_ws_for_finished_run_sends_snapshot_and_closes(db, ws_client):
    run = await state.create_run(db, "p")
    await state.update_run(db, run.id, status="completed")
    with ws_client.websocket_connect(f"/workflows/{run.id}/events") as ws:
        assert ws.receive_json()["data"]["run"]["status"] == "completed"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_ws_unknown_run_closes_4404(ws_client):
    with ws_client.websocket_connect("/workflows/nope/events") as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4404


def test_ws_rejects_foreign_origin(ws_client):
    with pytest.raises(WebSocketDisconnect) as e:
        with ws_client.websocket_connect("/workflows/x/events", headers={"origin": "http://evil.example"}) as ws:
            ws.receive_json()
    assert e.value.code == 1008


async def test_actor_publishes_step_events(db, prefix):
    async def handler(run, msg):
        return Outcome(next_queue=queues.CRITIC, run_updates={"status": "completed"})

    actor = Actor(queues.WRITE, handler, db, prefix=prefix)
    run = await state.create_run(db, "p")
    r = Redis.from_url(config.REDIS_URL)
    async with r.pubsub() as ps:
        await ps.subscribe(events.channel(run.id))
        await ps.get_message(timeout=1)  # the subscribe confirmation
        await actor.process(AgentMessage(workflow_run_id=run.id).model_dump())
        got = []
        async with asyncio.timeout(5):
            while len(got) < 3:
                if m := await ps.get_message(ignore_subscribe_messages=True, timeout=1):
                    got.append(json.loads(m["data"]))
    await r.aclose()
    assert [(e["type"], e["agent"]) for e in got] == [("step.started", "write"), ("step.done", "write"), ("run.status", None)]
    assert got[1]["data"] == {"revision": 0, "next": queues.CRITIC} and got[2]["data"] == {"status": "completed"}
    for q in actor._out.values():
        await q.obliterate(force=True)
        await q.close()
