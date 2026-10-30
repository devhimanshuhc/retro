"""Stronger sources: OpenAlex papers, source kinds decided by site, the SEC contact header, the second search."""
import httpx
import pytest

from app.agents import research
from app.models.messages import AgentMessage
from app.services import llm, scholar, sources
from tests.fakes import CANDIDATES, DRAFTS, USAGE, fake_fetch
from tests.test_handlers import run_at

REAL_SEARCH = scholar.search  # captured at import, before the autouse fixture stubs it for every test


def test_abstract_is_rebuilt_from_the_inverted_index():
    assert scholar.abstract({"batteries": [1], "Solid-state": [0], "scale": [3], "slowly": [2]}) == "Solid-state batteries slowly scale"
    assert scholar.abstract(None) == ""


async def test_search_keeps_relevant_papers_with_abstracts():
    long = {f"w{i}": [i] for i in range(80)}  # an 80-word abstract
    works = [
        {"id": "W1", "doi": "https://doi.org/10.1/a", "title": "Solid-state battery commercialization", "abstract_inverted_index": long},
        {"id": "W2", "doi": None, "title": "Bird migration patterns", "abstract_inverted_index": long},  # off topic
        {"id": "W3", "doi": "https://doi.org/10.1/c", "title": "Solid-state battery costs", "abstract_inverted_index": {"short": [0]}},
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"results": works}))) as c:
        out = await REAL_SEARCH("When will solid-state battery commercialization happen?", c)
    assert [p["url"] for p in out] == ["https://doi.org/10.1/a"]  # W2 off topic, W3 abstract too short


async def test_search_failure_means_no_papers():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as c:
        assert await REAL_SEARCH("solid-state battery commercialization", c) == []


@pytest.mark.parametrize("url, guess, kind", [
    ("https://www.sec.gov/Archives/x.htm", "news", "primary"),
    ("https://investor.nvidia.com/news", "news", "primary"),
    ("https://arxiv.org/abs/2401.1", "other", "paper"),
    ("https://doi.org/10.1/a", "news", "paper"),
    ("https://www.marketbeat.com/earnings/x", "primary", "news"),  # aggregators can't pass as primary
    ("https://finance.yahoo.com/x", "primary", "news"),
    ("https://www.cnbc.com/x", "news", "news"),  # no rule for the site: keep the guess
])
def test_kind_is_decided_by_the_site(url, guess, kind):
    assert sources.kind_of(url, guess) == kind


async def test_contact_email_goes_to_sec_only(monkeypatch):
    monkeypatch.setattr(sources.config, "CONTACT_EMAIL", "me@example.com")
    seen = {}

    def serve(req):
        seen[req.url.host] = req.headers["user-agent"]
        return httpx.Response(200, content=b"<p>" + b"x " * 400 + b"</p>", headers={"content-type": "text/html"})
    async with httpx.AsyncClient(headers=sources.HEADERS, transport=httpx.MockTransport(serve),
                                 event_hooks={"request": [sources._identify]}) as c:
        await sources.fetch(["https://www.sec.gov/a", "https://news.example.com/b"], c)
    assert seen["www.sec.gov"] == "Retro me@example.com"
    assert "me@example.com" not in seen["news.example.com"]


async def test_weak_sources_trigger_one_search_for_primary_sources(monkeypatch):
    """Only news readable: research searches again with the primary-only prompt and uses what it finds."""
    news_only = {"candidates": [{"objective_id": "o1", "url": "https://news.example.com/a", "title": "News", "kind": "news"},
                                {"objective_id": "o2", "url": "https://news.example.com/a", "title": "News", "kind": "news"}]}
    primary = {"candidates": [{"objective_id": "o1", "url": "https://ir.example.com/q3", "title": "Q3", "kind": "primary"}]}
    systems, prompts = [], []

    async def complete(agent, prompt, **kw):
        systems.append(kw.get("system"))
        prompts.append(prompt)
        if kw.get("tools"):
            return llm.Completion("", news_only if len(systems) == 1 else primary, USAGE)
        return llm.Completion("", DRAFTS, USAGE)
    monkeypatch.setattr(llm, "complete", complete)
    monkeypatch.setattr(sources, "fetch", fake_fetch)

    out = await research.handle(run_at("research"), AgentMessage(workflow_run_id="r"))
    assert systems[1] == research.PRIMARY_SEARCH  # the second search asks only for primary sources and papers
    assert "(primary) Q3 — https://ir.example.com/q3" in prompts[-1]  # the primary page reached the findings writer
    assert out.usage.input_tokens == 3 * USAGE["input_tokens"]  # both searches and the write are counted


async def test_strong_sources_need_no_second_search(monkeypatch):
    systems = []

    async def complete(agent, prompt, **kw):
        systems.append(kw.get("system"))
        return llm.Completion("", CANDIDATES if kw.get("tools") else DRAFTS, USAGE)
    monkeypatch.setattr(llm, "complete", complete)
    monkeypatch.setattr(sources, "fetch", fake_fetch)
    await research.handle(run_at("research"), AgentMessage(workflow_run_id="r"))
    assert research.PRIMARY_SEARCH not in systems  # 1 primary + 1 news = 0.5, not below MIN_STRONG


async def test_papers_from_openalex_become_sources(monkeypatch):
    async def papers(question, client, **kw):
        return [{"url": "https://doi.org/10.1/p", "title": "A paper", "year": 2025,
                 "text": "Revenue for the third quarter was a record $35.1 billion according to this study. " * 3}]
    monkeypatch.setattr(scholar, "search", papers)
    monkeypatch.setattr(sources, "fetch", fake_fetch)

    async def complete(agent, prompt, **kw):
        if kw.get("tools"):
            return llm.Completion("", CANDIDATES, USAGE)
        ids = [line[1:5] for line in prompt.splitlines() if line.startswith("[o1.")]
        return llm.Completion("", {"findings": [{"objective_id": "o1", "summary": "s", "passage_ids": ids}]}, USAGE)
    monkeypatch.setattr(llm, "complete", complete)
    out = await research.handle(run_at("research"), AgentMessage(workflow_run_id="r"))
    kinds = {s.url: s.kind for f in out.run_updates["findings"] for s in f.sources}
    assert kinds.get("https://doi.org/10.1/p") == "paper"  # the paper's abstract was a readable, citable source


async def test_no_second_search_when_the_budget_is_mostly_spent(monkeypatch):
    news_only = {"candidates": [{"objective_id": "o1", "url": "https://news.example.com/a", "title": "News", "kind": "news"}]}
    systems = []

    async def complete(agent, prompt, **kw):
        systems.append(kw.get("system"))
        return llm.Completion("", news_only if kw.get("tools") else DRAFTS, USAGE)
    monkeypatch.setattr(llm, "complete", complete)
    monkeypatch.setattr(sources, "fetch", fake_fetch)
    monkeypatch.setattr(research.config, "RUN_TOKEN_BUDGET", 20)  # the first search alone (15) is over half
    await research.handle(run_at("research"), AgentMessage(workflow_run_id="r"))
    assert research.PRIMARY_SEARCH not in systems


def test_short_official_documents_are_read_whole_and_long_ones_ranked():
    c = lambda url, kind: research.Candidate(objective_id="o1", url=url, title=url, kind=kind)
    release = "Second-quarter Edge Computing revenue was $7.2 billion, up 27% from a year ago, the company said. " * 5
    texts = {"https://ir.x.com/pr": release, "https://www.sec.gov/10q": "Long filing sentence about many things here. " * 900,
             "https://news.x.com/a": release}
    whole = research.whole_documents([c("https://ir.x.com/pr", "primary"), c("https://www.sec.gov/10q", "primary"),
                                      c("https://news.x.com/a", "news")], texts)
    assert {cand.url for cand, _ in whole} == {"https://ir.x.com/pr"}  # the 10-Q is too long; news is never read whole
    assert any("$7.2 billion" in p for _, p in whole)


async def test_any_objective_may_cite_a_whole_document():
    cand = research.Candidate(objective_id="o1", url="https://ir.x.com/pr", title="PR", kind="primary")
    passages = {"d.1": (cand, "Revenue for the quarter was $96.2 billion, up 106% from a year ago, NVIDIA said."),
                "o1.1": (cand, "something else entirely that is long enough to be a passage here.")}

    async def complete(agent, prompt, **kw):
        return llm.Completion("", {"findings": [{"objective_id": "o2", "summary": "s", "passage_ids": ["d.1", "o1.1"]}]}, USAGE)
    import app.services.llm as L
    old, L.complete = L.complete, complete
    try:
        findings, _ = await research.write_findings("b", {"o1": "q1", "o2": "q2"}, passages, [])
    finally:
        L.complete = old
    assert [s.quote for s in findings[0].sources] == [passages["d.1"][1]]  # d.1 allowed for o2; o1.1 is not
