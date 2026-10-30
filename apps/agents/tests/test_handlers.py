import pytest
from bullmq import UnrecoverableError
from pydantic import ValidationError

from app.agents import critic, research, supervisor, writer
from app.models.messages import AgentMessage
from app.models.run import Critique, Finding, Plan, Revision, WorkflowRun
from app.services import llm, queues, sources
from tests.fakes import CANDIDATES, FINDINGS, GOOD_REPORT, GOOD_SCORES, PAGES, PLAN, fake_fetch, fake_llm


def run_at(stage: str, **kw) -> WorkflowRun:
    run = WorkflowRun(prompt="Nvidia Q3 report")
    if stage in ("research", "write", "critic"):
        run.plan = Plan.model_validate(PLAN)
    if stage in ("write", "critic"):
        run.findings = [Finding.model_validate(f) for f in FINDINGS["findings"]]
    return run.model_copy(update=kw)


@pytest.fixture
def calls(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "complete", fake_llm(calls))
    monkeypatch.setattr(sources, "fetch", fake_fetch)
    return calls


async def test_supervisor_saves_plan(calls):
    out = await supervisor.handle(run_at("supervisor"), AgentMessage(workflow_run_id="r"))
    assert out.next_queue == queues.RESEARCH and out.run_updates["plan"].outline == ["Revenue", "Outlook"]
    assert out.usage.input_tokens == 10


async def test_supervisor_rejects_bad_plan(monkeypatch):
    async def bad(*a, **k):
        return llm.Completion("", {"objectives": [], "outline": []})
    monkeypatch.setattr(llm, "complete", bad)
    with pytest.raises(ValidationError):  # plain error: BullMQ retries
        await supervisor.handle(run_at("supervisor"), AgentMessage(workflow_run_id="r"))


async def test_research_builds_findings_from_fetched_passages(calls):
    out = await research.handle(run_at("research"), AgentMessage(workflow_run_id="r"))
    [f1, f2] = out.run_updates["findings"]
    assert f1.sources[0].quote == PAGES["https://ir.example.com/q3"]  # the quote is the page text, not LLM output
    assert (f2.objective_id, f2.sources[0].url, f2.sources[0].kind) == ("o2", "https://news.example.com/a", "news")
    assert out.usage.input_tokens == 20 and out.run_updates["warnings"] == []
    write_prompt = [p for a, p, kw in calls if a == "research"][1]
    assert PAGES["https://news.example.com/a"] in write_prompt  # the LLM sees the retrieved passage


async def test_research_drops_dead_pages_and_bad_passage_ids(calls, monkeypatch):
    cands = {"candidates": [*CANDIDATES["candidates"],
                            {"objective_id": "o2", "url": "https://dead.example.com", "title": "x", "kind": "paper"}]}
    drafts = {"findings": [{"objective_id": "o1", "summary": "s", "passage_ids": ["o1.1", "o1.9", "o2.1"]},
                           {"objective_id": "o2", "summary": "nothing found", "passage_ids": []}]}

    async def complete(agent, prompt, **kw):
        calls.append((agent, prompt, kw))
        return llm.Completion("", cands if kw.get("tools") else drafts, {"input_tokens": 1, "output_tokens": 1})
    monkeypatch.setattr(llm, "complete", complete)
    out = await research.handle(run_at("research"), AgentMessage(workflow_run_id="r"))
    [f] = out.run_updates["findings"]
    assert [s.url for s in f.sources] == ["https://ir.example.com/q3"]  # o1.9 unknown, o2.1 belongs to o2
    assert out.run_updates["warnings"] == ["dropped source https://dead.example.com: HTTP 404",
                                           "no source answered objectives ['o2']; the report leaves them out"]


async def test_research_retries_when_no_page_is_usable(calls, monkeypatch):
    async def nothing(urls, client=None):
        return {}, ["x: HTTP 403"]
    monkeypatch.setattr(sources, "fetch", nothing)
    with pytest.raises(RuntimeError, match="no usable source pages"):
        await research.handle(run_at("research"), AgentMessage(workflow_run_id="r"))


def test_select_caps_passages_per_source():
    a, b = research.Candidate(objective_id="o1", url="https://a", title="a", kind="news"), \
        research.Candidate(objective_id="o1", url="https://b", title="b", kind="paper")
    pool = [(a, f"revenue growth passage {i}") for i in range(5)] + [(b, "revenue growth from b")]
    assert [c.url for c, _ in research.select("revenue growth", pool)] == ["https://b", "https://a", "https://a"]


async def test_research_without_plan_is_unrecoverable(calls):
    with pytest.raises(UnrecoverableError):
        await research.handle(run_at("supervisor"), AgentMessage(workflow_run_id="r"))


async def test_writer_appends_deduped_sources(calls):
    out = await writer.handle(run_at("write"), AgentMessage(workflow_run_id="r"))
    [rev] = out.run_updates["revisions"]
    assert rev.revision == 0 and rev.report_md.endswith(
        "## Sources\n1. [Q3](https://ir.example.com/q3)\n2. [News](https://news.example.com/a)\n")
    assert out.next_queue == queues.CRITIC


async def test_writer_gets_previous_draft_and_feedback(calls):
    prev = Revision(revision=0, report_md="old draft", critique=Critique(passed=False, errors=["add numbers"]))
    out = await writer.handle(run_at("write", revisions=[prev], revision=1), AgentMessage(workflow_run_id="r", revision=1))
    prompt = calls[-1][1]
    assert "old draft" in prompt and "- add numbers" in prompt
    assert [r.revision for r in out.run_updates["revisions"]] == [0, 1]


@pytest.mark.parametrize("report, errors", [
    (GOOD_REPORT, []),
    ("## Revenue\nNo cites.\n## Outlook\nx", ["no citations: cite the sources like [1]"]),
    ("## Revenue\nx [1] [7]", ['missing section "## Outlook"', "citations [7] match no source (valid: 1-2)"]),
    ("## revenue \nx [1]\n## OUTLOOK\ny [2]", []),  # case and trailing space don't matter
    ("## Revenue\nUp 17% [1]. The plant opens in 2027. Fine.\n## Outlook\n- $5B guide [2]",
     ['every sentence with a number or date needs a citation: "The plant opens in 2027."']),
    ("## Revenue\nRevenue was $35.4B, up 1,200 units [1].\n## Outlook\nx [2]",  # planted wrong number
     ["numbers not stated in the findings (use only the findings' numbers): 1200, 35.4"]),
])
def test_check(report, errors):
    evidence = "Revenue was $35.1B, up 17% to 1,000 units. Plant opens 2027. Guidance $37.5B, $5B."
    assert critic.check(report + "\n\n## Sources\n1. [a](https://a)\n", ["Revenue", "Outlook"], 2, evidence) == errors


async def test_critic_deterministic_fail_skips_llm_and_loops(calls):
    run = run_at("critic", revisions=[Revision(revision=0, report_md="no headings")])
    out = await critic.handle(run, AgentMessage(workflow_run_id="r"))
    assert calls == []
    assert (out.next_queue, out.next_revision, out.run_updates["revision"]) == (queues.WRITE, 1, 1)
    assert out.run_updates["revisions"][0].critique.passed is False


async def test_critic_pass_completes(calls):
    out = await critic.handle(run_at("critic", revisions=[Revision(revision=0, report_md=GOOD_REPORT)]),
                              AgentMessage(workflow_run_id="r"))
    assert out.next_queue is None and out.run_updates["status"] == "completed"
    assert out.run_updates["revisions"][0].critique.scores.completeness == GOOD_SCORES["completeness"]
    assert calls[-1][2]["think"] is False


async def test_critic_low_score_fails(monkeypatch):
    monkeypatch.setattr(llm, "complete", fake_llm([], scores=({**GOOD_SCORES, "factual_accuracy": 0.5},)))
    out = await critic.handle(run_at("critic", revisions=[Revision(revision=0, report_md=GOOD_REPORT)]),
                              AgentMessage(workflow_run_id="r"))
    assert out.next_queue == queues.WRITE and out.run_updates["revisions"][0].critique.errors == ["e"]


async def test_critic_weak_sources_pass_with_warning(monkeypatch):
    monkeypatch.setattr(llm, "complete", fake_llm([], scores=({**GOOD_SCORES, "source_quality": 0.3},)))
    out = await critic.handle(run_at("critic", revisions=[Revision(revision=0, report_md=GOOD_REPORT)]),
                              AgentMessage(workflow_run_id="r"))
    # the LLM said 0.3; the score is counted from the cited sources instead: 1 primary + 1 news = 0.5
    assert out.run_updates["status"] == "completed" and out.run_updates["warnings"] == ["weak sources: source_quality 0.5"]
    assert out.run_updates["revisions"][0].critique.scores.source_quality == 0.5


async def test_writer_and_critic_see_the_verified_quotes(calls):
    await writer.handle(run_at("write"), AgentMessage(workflow_run_id="r"))
    await critic.handle(run_at("critic", revisions=[Revision(revision=0, report_md=GOOD_REPORT)]),
                        AgentMessage(workflow_run_id="r"))
    for _, prompt, _ in calls:
        assert '"Nvidia guided fourth-quarter revenue to $37.5 billion."' in prompt


async def test_critic_cap_completes_with_warning(calls, monkeypatch):
    monkeypatch.setattr(critic.config, "MAX_REVISIONS", 2)
    run = run_at("critic", revision=1, revisions=[Revision(revision=1, report_md="bad")])
    out = await critic.handle(run, AgentMessage(workflow_run_id="r", revision=1))
    assert out.next_queue is None and out.run_updates["status"] == "completed"
    assert "MAX_REVISIONS (2)" in out.run_updates["warnings"][0]
