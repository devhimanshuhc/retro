"""Production limits: the per-run token budget and the rate limit on starting runs."""
import pytest

import config
from app.agents.base import Actor, Outcome
from app.models.messages import AgentMessage
from app.models.run import Revision, Usage
from app.services import queues, state


@pytest.fixture
async def over_budget_actor(db, prefix):
    called = []

    async def handler(run, msg):
        called.append(run.id)  # must never run: the budget is spent
        return Outcome(next_queue=queues.CRITIC)
    actor = Actor(queues.WRITE, handler, db, prefix=prefix)
    yield actor, called
    for q in actor._out.values():
        await q.obliterate(force=True)
        await q.close()


async def spent_run(db, budget, **fields):
    run = await state.create_run(db, "p")
    await state.update_run(db, run.id, usage={"research": Usage(input_tokens=budget, output_tokens=1)}, **fields)
    return run


async def test_over_budget_run_completes_with_its_latest_draft(db, over_budget_actor, monkeypatch):
    monkeypatch.setattr(config, "RUN_TOKEN_BUDGET", 1000)
    actor, called = over_budget_actor
    run = await spent_run(db, 1000, revisions=[Revision(revision=0, report_md="# Draft")], revision=1)
    assert await actor.process(AgentMessage(workflow_run_id=run.id, revision=1).model_dump()) == "done"
    after = await state.get_run(db, run.id)
    assert called == [] and after.status == "completed"
    assert after.warnings == ["token budget reached: 1,001 of 1,000 tokens used; stopped before write, the report is draft 1"]
    assert after.steps["write"].next is None  # nothing sent on


async def test_over_budget_before_research_fails(db, prefix, monkeypatch):
    monkeypatch.setattr(config, "RUN_TOKEN_BUDGET", 1000)
    called = []

    async def handler(run, msg):
        called.append(run.id)
        return Outcome()
    actor = Actor(queues.RESEARCH, handler, db, prefix=prefix)
    run = await spent_run(db, 5000)
    await actor.process(AgentMessage(workflow_run_id=run.id).model_dump())
    after = await state.get_run(db, run.id)
    assert called == [] and after.status == "failed" and after.warnings[0].endswith("no report was written")
    for q in actor._out.values():
        await q.close()


async def test_over_budget_still_writes_the_first_draft(db, over_budget_actor, monkeypatch):
    """Research already spent the tokens: the budget stops extra rewrites, never the first report."""
    monkeypatch.setattr(config, "RUN_TOKEN_BUDGET", 1000)
    actor, called = over_budget_actor  # the writer
    run = await spent_run(db, 5000)
    await actor.process(AgentMessage(workflow_run_id=run.id).model_dump())
    assert called == [run.id]


async def test_under_budget_runs_normally(db, over_budget_actor, monkeypatch):
    monkeypatch.setattr(config, "RUN_TOKEN_BUDGET", 1000)
    actor, called = over_budget_actor
    run = await spent_run(db, 500)
    await actor.process(AgentMessage(workflow_run_id=run.id).model_dump())
    assert called == [run.id]


async def test_starting_runs_is_rate_limited_per_client(api, prefix, monkeypatch):
    monkeypatch.setattr(config, "RUNS_PER_WINDOW", 2)
    assert [(await api.post("/workflows", json={"prompt": "p"})).status_code for _ in range(2)] == [202, 202]
    r = await api.post("/workflows", json={"prompt": "p"})
    assert r.status_code == 429 and 0 < int(r.headers["retry-after"]) <= config.RUN_WINDOW_S
    assert "too many runs" in r.json()["detail"]
    for name in queues.ALL_QUEUES:
        q = queues.open_queue(name, prefix=prefix)
        await q.obliterate(force=True)
        await q.close()
