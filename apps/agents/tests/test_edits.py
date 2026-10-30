"""Follow-up edits to a finished report, and the artifacts list."""
import pytest

from app.agents import critic, writer
from app.models.messages import AgentMessage
from app.models.run import Critique, Finding, Plan, Revision, Scores
from app.services import llm, queues, state
from tests.fakes import FINDINGS, GOOD_REPORT, GOOD_SCORES, PLAN, fake_llm

PASSED = Critique(passed=True, errors=[], scores=Scores(**GOOD_SCORES))


async def finished_run(db, **over):
    run = await state.create_run(db, "Nvidia Q3 report")
    await state.update_run(db, run.id, status="completed", revision=1, plan=Plan.model_validate(PLAN),
                           findings=[Finding.model_validate(f) for f in FINDINGS["findings"]],
                           revisions=[Revision(revision=0, report_md="draft"), Revision(revision=1, report_md=GOOD_REPORT, critique=PASSED)],
                           **over)
    return run


@pytest.fixture
async def cleanup(prefix):
    yield
    for name in queues.ALL_QUEUES:
        q = queues.open_queue(name, prefix=prefix)
        await q.obliterate(force=True)
        await q.close()


async def test_edit_reopens_a_finished_run_and_sends_it_to_the_writer(api, db, prefix, cleanup):
    run = await finished_run(db)
    r = await api.post(f"/workflows/{run.id}/edit", json={"instruction": "Add a risks section"})
    assert r.status_code == 202 and r.json()["status"] == "working" and r.json()["revision"] == 2
    after = await state.get_run(db, run.id)
    assert [(e.revision, e.instruction) for e in after.edits] == [(2, "Add a risks section")]
    q = queues.open_queue(queues.WRITE, prefix=prefix)
    [job] = await q.getJobs(["wait"])
    await q.close()
    assert job.id == f"{run.id}-write-2"
    # while it works, another change has to wait
    assert (await api.post(f"/workflows/{run.id}/edit", json={"instruction": "x"})).status_code == 409


async def test_edit_needs_a_completed_report(api, db):
    run = await state.create_run(db, "p")
    assert (await api.post(f"/workflows/{run.id}/edit", json={"instruction": "x"})).status_code == 409
    assert (await api.post("/workflows/nope/edit", json={"instruction": "x"})).status_code == 404
    assert (await api.post(f"/workflows/{run.id}/edit", json={"instruction": ""})).status_code == 422


async def test_writer_gets_the_current_report_and_the_change(db):
    run = await finished_run(db)
    run = await state.request_edit(db, run.id, "Make it shorter")
    prompt = writer.build_prompt(run, 2)
    assert GOOD_REPORT in prompt and "Make it shorter" in prompt and "A reviewer rejected it" not in prompt


async def test_critic_reviews_the_change_without_the_outline_and_caps_per_edit(db, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "complete", fake_llm(calls, scores=({**GOOD_SCORES, "factual_accuracy": 0.4},)))
    monkeypatch.setattr(critic.config, "MAX_REVISIONS", 2)
    run = await finished_run(db)
    run = await state.request_edit(db, run.id, "Drop the outlook section")
    short = "# Nvidia Q3\n\n## Revenue\nRevenue was $35.1B [1]."
    run = run.model_copy(update={"revisions": [*run.revisions, Revision(revision=2, report_md=short)]})
    out = await critic.handle(run, AgentMessage(workflow_run_id=run.id, revision=2))
    assert 'missing section' not in str(out.run_updates["revisions"][-1].critique.errors)
    assert "Drop the outlook section" in calls[-1][1]  # the rubric checks the change was made
    # rejected: with the cap counted from revision 0 this would end the run (2 + 1 >= 2); counted from the edit it loops
    assert (out.next_queue, out.next_revision) == (queues.WRITE, 3)


async def test_artifacts_list_finished_reports_with_their_titles(api, db):
    await finished_run(db)
    await state.create_run(db, "still working")
    [a] = (await api.get("/artifacts")).json()
    assert (a["title"], a["revision"], a["sources"], a["edits"]) == ("Nvidia Q3", 1, 2, 0)
