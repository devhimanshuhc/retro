import pytest

from app.agents import critic, router
from app.models.messages import AgentMessage
from app.models.run import Turn
from app.services import llm, queues, state
from tests.fakes import USAGE
from tests.test_api import cleanup_queues  # noqa: F401  (fixture)
from tests.test_handlers import run_at


def route_to(monkeypatch, intent, reply="Hi! I research topics and write cited reports.", request=""):
    seen = []

    async def complete(agent, prompt, **kw):
        seen.append((agent, prompt, kw))
        return llm.Completion("", {"intent": intent, "reply": reply, "research_request": request}, USAGE)
    monkeypatch.setattr(llm, "complete", complete)
    return seen


async def test_chat_is_answered_without_starting_research(monkeypatch):
    seen = route_to(monkeypatch, "chat")
    run = run_at("supervisor").model_copy(update={"prompt": "hey", "turns": [Turn(role="user", text="hey")], "plan": None})
    out = await router.handle(run, AgentMessage(workflow_run_id="r"))
    assert out.next_queue is None and out.run_updates["status"] == "completed" and out.run_updates["intent"] == "chat"
    assert [t.role for t in out.run_updates["turns"]] == ["user", "assistant"]
    [(agent, prompt, kw)] = seen
    assert agent == "router" and kw["think"] is False and "user: hey" in prompt


async def test_research_goes_to_the_planner_at_revision_0_with_a_standalone_request(monkeypatch):
    route_to(monkeypatch, "research", "I'll research solid-state batteries.", "State of solid-state EV batteries in 2026")
    turns = [Turn(role="user", text="hey"), Turn(role="assistant", text="Hi!"), Turn(role="user", text="do batteries")]
    run = run_at("supervisor").model_copy(update={"prompt": "hey", "turns": turns, "plan": None})
    out = await router.handle(run, AgentMessage(workflow_run_id="r", revision=1))
    assert (out.next_queue, out.next_revision) == (queues.SUPERVISOR, 0)
    assert out.run_updates["brief"] == "State of solid-state EV batteries in 2026"   # the follow-up becomes the brief


async def test_a_first_research_message_keeps_the_users_words(monkeypatch):
    route_to(monkeypatch, "research", "On it.", "a rewritten request")
    run = run_at("supervisor").model_copy(update={"turns": [Turn(role="user", text="Nvidia Q3 report")], "plan": None})
    out = await router.handle(run, AgentMessage(workflow_run_id="r"))
    assert "brief" not in out.run_updates            # the agents research the first message as written


async def test_attached_files_skip_the_model(monkeypatch):
    seen = route_to(monkeypatch, "chat")
    run = run_at("supervisor").model_copy(update={"document_ids": ["d1"], "plan": None})
    out = await router.handle(run, AgentMessage(workflow_run_id="r"))
    assert out.next_queue == queues.SUPERVISOR and not seen


async def test_summary_keeps_only_numbers_from_the_report(monkeypatch):
    report = "# Nvidia Q3\n\n## Revenue\nRevenue was $35.1B [1]."
    async def says(text):
        async def complete(agent, prompt, **kw): return llm.Completion(text, None, USAGE)
        monkeypatch.setattr(llm, "complete", complete)
    await says("Revenue was $35.1B, a record.")
    assert (await critic.summarize(report))[0] == "Revenue was $35.1B, a record."
    await says("Revenue was $99B.")                     # a number the report doesn't state
    assert (await critic.summarize(report))[0].startswith("Your report is ready: Nvidia Q3")


async def test_follow_up_messages_only_on_a_finished_chat(api, db, cleanup_queues):  # noqa: F811
    run = await state.create_run(db, "hey")
    assert (await api.post(f"/workflows/{run.id}/messages", json={"message": "x"})).status_code == 409   # still working
    await state.runs(db).update_one({"_id": run.id}, {"$set": {"status": "completed", "intent": "chat"}})
    r = await api.post(f"/workflows/{run.id}/messages", json={"message": "what can you do?"})
    assert r.status_code == 202
    got = await state.get_run(db, run.id)
    assert got.status == "working" and [t.text for t in got.turns] == ["hey", "what can you do?"] and state.user_turn(got) == 1
    await state.runs(db).update_one({"_id": run.id}, {"$set": {"status": "completed", "intent": "research"}})
    assert (await api.post(f"/workflows/{run.id}/messages", json={"message": "x"})).status_code == 409   # has research
    assert (await api.post("/workflows/nope/messages", json={"message": "x"})).status_code == 404


async def test_an_explicit_report_request_is_researched_even_if_the_model_hesitates(monkeypatch):
    route_to(monkeypatch, "chat", "I need to verify real events first. Which incident do you mean?")
    msg = "Deep Investigative Research Report: The October 2026 Binance Heist"
    run = run_at("supervisor").model_copy(update={"prompt": msg, "turns": [Turn(role="user", text=msg)], "plan": None})
    out = await router.handle(run, AgentMessage(workflow_run_id="r"))
    assert out.next_queue == queues.SUPERVISOR and out.run_updates["intent"] == "research"


async def test_a_decline_is_not_overridden(monkeypatch):
    route_to(monkeypatch, "decline", "I write research reports, not code.")
    run = run_at("supervisor").model_copy(update={"turns": [Turn(role="user", text="write a python script to analyze my csv")], "plan": None})
    out = await router.handle(run, AgentMessage(workflow_run_id="r"))
    assert out.next_queue is None and out.run_updates["intent"] == "decline"


async def test_research_over_the_report_limit_is_answered_in_chat(monkeypatch, prefix):
    from redis.asyncio import Redis
    import config
    from app.services import limits
    route_to(monkeypatch, "research", "On it.")
    monkeypatch.setattr(config, "RUNS_PER_WINDOW", 1)
    redis = Redis.from_url(config.REDIS_URL); token = limits.client.set((redis, prefix))
    try:
        run = run_at("supervisor").model_copy(update={"turns": [Turn(role="user", text="Nvidia Q3 report")], "plan": None})
        first = await router.handle(run, AgentMessage(workflow_run_id="r"))
        second = await router.handle(run, AgentMessage(workflow_run_id="r"))
    finally:
        limits.client.reset(token); await redis.delete(f"{prefix}:ratelimit:research"); await redis.aclose()
    assert first.next_queue == queues.SUPERVISOR
    assert second.next_queue is None and "limit" in second.run_updates["turns"][-1].text
