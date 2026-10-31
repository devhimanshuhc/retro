import asyncio
import logging
from collections import Counter

import httpx
from bullmq import UnrecoverableError
from pydantic import BaseModel, Field

import config
from app.agents.base import Outcome, main
from app.models.messages import AgentMessage
from app.models.run import Finding, Source, SourceKind, Usage, WorkflowRun
from app.services import documents, llm, progress, queues, scholar, sources

PER_OBJECTIVE = 6  # passages the LLM sees per objective
PER_SOURCE = 2     # of those, at most this many from one page, so one source can't crowd out the rest
WEIGHT = {"file": 2.0, "paper": 2.0, "primary": 2.0, "news": 0.8, "other": 0.5}  # on equal relevance, prefer stronger sources
log = logging.getLogger("agent.research")

SEARCH = """You find sources for a research brief. For each objective, run 1-2 web searches and pick 2-4 result URLs
that most likely answer it. Do not open pages; the pages are fetched and read for you afterwards.
For every objective, include at least one paper or primary source whenever one exists: search for it directly
(e.g. the company's own press release or investor-relations page, the regulator's data, the paper on arXiv).
Prefer, best first: paper (peer-reviewed journal or conference papers, or arXiv/SSRN preprints); primary (company
filings and investor-relations releases, government, regulator or statistics data, standards bodies, official docs);
news (established outlets with their own reporting). Avoid blogs, SEO/content farms, aggregators and forums
("other": only if nothing better exists). Prefer pages whose text is in the HTML or a PDF (not video, not paywalled).
Use only URLs that appeared in your search results; never build or guess one."""

WRITE = """You write research findings using only the numbered passages below. They were extracted by code, verbatim,
from the pages listed; nothing else is known. For each objective: a factual summary of 3-6 sentences (concrete
numbers, dates, who said it) that states only what the passages say, and passage_ids listing every passage you used.
If good sources disagree, say so. If the passages don't answer the objective, return empty passage_ids.
Never use outside knowledge.
Passages numbered [d.N] are whole official documents, papers or the user's own files, split in order: any objective may cite them, and
they are the most reliable source, so prefer their figures and include every relevant number they state
(e.g. results, segment figures, prior-year comparisons, outlook)."""

NOTHING_IN_FILES = "the attached files don't answer the questions asked; attach other files or search the web too"
STRONG = ("file", "primary", "paper")  # the user's own files count as authoritative, like official sources
WHOLE_CHARS = 30_000  # official documents/papers read in full per run, ~7.5k tokens; longer ones are ranked as usual


def whole_documents(cands: list["Candidate"], texts: dict[str, str]) -> list[tuple["Candidate", str]]:
    """Every passage of the readable primary/paper pages that fit in WHOLE_CHARS, shortest pages first."""
    pages = {c.url: c for c in cands if c.kind in STRONG and c.url in texts}
    out, used = [], 0
    for c in sorted(pages.values(), key=lambda c: len(texts[c.url])):
        if used + len(texts[c.url]) > WHOLE_CHARS:
            continue  # too long to read whole (e.g. a full 10-Q): it still competes in the ranked passages
        used += len(texts[c.url])
        out += [(c, p) for p in sources.passages(texts[c.url])]
    return out


class Candidate(BaseModel):
    objective_id: str
    url: str = Field(pattern=r"^(https?|doc)://")
    title: str
    kind: SourceKind


class Candidates(BaseModel):
    candidates: list[Candidate] = Field(max_length=20)


class Draft(BaseModel):
    objective_id: str
    summary: str
    passage_ids: list[str]


class Drafts(BaseModel):
    findings: list[Draft]


MIN_STRONG = 0.5  # below this share of papers + primary sources among readable pages, search once more for them
RETRY_BUDGET_SHARE = 0.5  # ...but only while the run has used under half its token budget (writing still needs room)
PRIMARY_SEARCH = """You find stronger sources for a research brief whose first search found mostly news.
Run at most 4 web searches in total and pick 1-3 URLs per objective that are ONLY primary sources or papers:
the organisation's own newsroom, press release or investor-relations page; regulator or government data (e.g. SEC
filings on sec.gov, statistics offices); official documentation; peer-reviewed papers or arXiv preprints.
No news outlets, blogs, aggregators or encyclopedias. If a listed page failed to load, look for another copy of the
same document (e.g. the company's own newsroom instead of a filing mirror). Use only URLs from your search results."""


def strong_share(cands: list[Candidate], texts: dict[str, str]) -> float:
    """Share of distinct readable pages that are papers or primary sources."""
    kinds = {c.url: c.kind for c in cands if c.url in texts}
    return sum(k in STRONG for k in kinds.values()) / len(kinds) if kinds else 0.0


async def scholarly(objectives: dict[str, str]) -> list[tuple[Candidate, str]]:
    """Papers from OpenAlex for each objective, with their abstracts as the page text."""
    async with httpx.AsyncClient(headers={"User-Agent": "Retro research"}) as client:
        found = await asyncio.gather(*(scholar.search(q, client) for q in objectives.values()))
    out, seen = [], set()
    for oid, papers in zip(objectives, found):
        for p in papers:
            if p["url"] not in seen:
                seen.add(p["url"])
                out.append((Candidate(objective_id=oid, url=p["url"], title=p["title"], kind="paper"), p["text"]))
    return out


def select(question: str, pool: list[tuple[Candidate, str]]) -> list[tuple[Candidate, str]]:
    """The best PER_OBJECTIVE passages for a question, at most PER_SOURCE from any one page."""
    picked, per = [], {}
    for i in sources.rank(question, [p for _, p in pool], [WEIGHT[c.kind] for c, _ in pool]):
        c = pool[i][0]
        if per.get(c.url, 0) < PER_SOURCE:
            per[c.url] = per.get(c.url, 0) + 1
            picked.append(pool[i])
            if len(picked) == PER_OBJECTIVE:
                break
    return picked


def retrieve(objectives: dict[str, str], cands: list[Candidate], texts: dict[str, str], prompt: str):
    """Top passages per objective, as ({"o1.1": (candidate, passage)}, prompt blocks for the LLM)."""
    passages, blocks = {}, []
    for oid, question in objectives.items():
        pool = [(c, p) for c in cands if c.objective_id == oid and c.url in texts for p in sources.passages(texts[c.url])]
        for n, (c, p) in enumerate(select(f"{question} {prompt}", pool), 1):
            passages[f"{oid}.{n}"] = (c, p)
            blocks.append(f"[{oid}.{n}] ({c.kind}) {c.title} — {c.url}\n{p}")
    return passages, blocks


async def write_findings(brief: str, objectives: dict[str, str], passages: dict, blocks: list[str]):
    """One LLM call: findings from the given passages only. Quotes are the passages themselves."""
    w = await llm.complete("research", f"{brief}\n\nPassages:\n\n" + "\n\n".join(blocks), system=WRITE,
                           schema=Drafts.model_json_schema())
    findings = []
    for d in Drafts.model_validate(w.data).findings:
        used = [passages[i] for i in dict.fromkeys(d.passage_ids)
                if i in passages and (i.startswith(f"{d.objective_id}.") or i.startswith("d."))]  # d.N: any objective
        if d.objective_id in objectives and used and d.objective_id not in {f.objective_id for f in findings}:
            findings.append(Finding(objective_id=d.objective_id, summary=d.summary, sources=[
                Source(url=c.url, title=c.title, kind=c.kind, quote=p) for c, p in used]))
    return findings, w


def web_url(url: str) -> bool:
    return url.startswith(("https://", "http://"))  # a doc:// URL from the model must not pass as the user's file


def brief_for(prompt: str, objectives: dict[str, str]) -> str:
    return f"Request: {prompt}\n\nObjectives:\n" + "\n".join(f"- {k}: {q}" for k, q in objectives.items())


async def handle(run: WorkflowRun, msg: AgentMessage) -> Outcome:
    if run.plan is None:
        raise UnrecoverableError("research needs a plan")
    objectives = {o.id: o.question for o in run.plan.objectives}
    brief = brief_for(run.request, objectives)

    # 0. the user's own files: their text was pulled out on upload, so every objective can read every file
    docs = await documents.load(documents.store.get(), run.document_ids) if run.document_ids else []
    cands, texts, dropped, files = [], {}, [], []
    for d in docs:
        url = documents.SCHEME + d["_id"]
        texts[url] = d["text"]
        files += [Candidate(objective_id=oid, url=url, title=d["name"], kind="file") for oid in objectives]
    cands += files
    if docs:
        await progress.report("files", f"Reading {len(docs)} of your files",
                              pages=[{"url": documents.SCHEME + d["_id"], "title": d["name"], "kind": "file"} for d in docs])

    s = retry = None
    if run.web:
        # 1. search only: small results, no page contents in the LLM context
        await progress.report("searching", f"Searching the web for sources on {len(objectives)} questions")
        s = await llm.complete("research", brief, system=SEARCH, schema=Candidates.model_json_schema(),
                               tools=["WebSearch"], max_turns=10)
        cands += [c.model_copy(update={"kind": sources.kind_of(c.url, c.kind)})  # the site decides the kind, not the guess
                 for c in Candidates.model_validate(s.data).candidates if c.objective_id in objectives and web_url(c.url)]

        found = cands[len(files):]
        kinds = Counter(c.kind for c in found)
        await progress.report("found", f"Picked {len(found)} candidate pages ("
                              + ", ".join(f"{n} {k}" for k, n in kinds.most_common()) + ")",
                              pages=[{"url": c.url, "title": c.title, "kind": c.kind} for c in found])

        # 2. fetch + chunk + rank in code: no tokens
        await progress.report("fetching", f"Reading {len(found)} pages (HTML and PDF)")
        web_texts, dropped = await sources.fetch(c.url for c in found)
        texts.update(web_texts)
        await progress.report("fetched", f"Read {len(web_texts)} of {len(found)} pages"
                              + (f", {len(dropped)} unreachable" if dropped else ""), dropped=dropped)
        log.info("run=%s candidates=%d %s fetched=%d", run.id, len(cands), dict(kinds), len(web_texts))

        # 2b. papers from OpenAlex: real papers with their abstracts, which no publisher wall can block
        papers = await scholarly(objectives)
        for c, text in papers:
            cands.append(c)
            texts[c.url] = text
        if papers:
            await progress.report("papers", f"Added {len(papers)} research papers from OpenAlex",
                                  pages=[{"url": c.url, "title": c.title, "kind": c.kind} for c, _ in papers])

        # 2c. too few papers or official sources made it through: one more search aimed only at those
        spent = run.tokens_used() + s.usage["input_tokens"] + s.usage["output_tokens"]
        if strong_share(cands, texts) < MIN_STRONG and spent < config.RUN_TOKEN_BUDGET * RETRY_BUDGET_SHARE:
            failed = [d for d in dropped]
            await progress.report("searching", f"Only {strong_share(cands, texts):.0%} of readable sources are papers or "
                                  "official; searching again for official sources")
            retry = await llm.complete("research", brief + ("\n\nThese pages failed to load; find other copies of the "
                                       "same documents:\n" + "\n".join(f"- {d}" for d in failed) if failed else ""),
                                       system=PRIMARY_SEARCH, schema=Candidates.model_json_schema(),
                                       tools=["WebSearch"], max_turns=5)  # capped: the first full retry cost ~400k tokens
            seen = {c.url for c in cands}
            more = [c.model_copy(update={"kind": sources.kind_of(c.url, c.kind)})
                    for c in Candidates.model_validate(retry.data).candidates
                    if c.objective_id in objectives and c.url not in seen and web_url(c.url)]
            more_texts, more_dropped = await sources.fetch(c.url for c in more)
            cands += more
            texts.update(more_texts)
            dropped += more_dropped
            await progress.report("fetched", f"Read {len(more_texts)} of {len(more)} more pages; "
                                  f"{strong_share(cands, texts):.0%} of readable sources are now papers or official",
                                  dropped=more_dropped)

    passages, blocks = retrieve(objectives, cands, texts, run.request)
    # short official documents and papers are read whole: keyword ranking misses their tables and wording
    # ("outlook" for "guidance"), and they hold the facts a report most needs
    whole = whole_documents(cands, texts)
    for n, (c, p) in enumerate(whole, 1):
        passages[f"d.{n}"] = (c, p)
        blocks.append(f"[d.{n}] ({c.kind}) {c.title} — {c.url}\n{p}")
    if whole:
        await progress.report("whole", f"Reading {len({c.url for c, _ in whole})} documents in full")
    if not passages:
        if not run.web:
            raise UnrecoverableError(NOTHING_IN_FILES)
        raise RuntimeError(f"no usable source pages: {dropped}")  # retried

    await progress.report("ranked", f"Kept the {len(passages)} most relevant passages, ranked by keyword match (BM25)")

    # 3. write findings from the top passages only
    await progress.report("summarizing", f"Writing findings from {len(passages)} verbatim passages")
    findings, w = await write_findings(brief, objectives, passages, blocks)
    await progress.report("summarized", f"{len(findings)} of {len(objectives)} questions answered with cited sources")
    if not findings:
        if not run.web:
            raise UnrecoverableError(NOTHING_IN_FILES)
        raise RuntimeError("no objective could be answered from the fetched sources")  # retried

    warnings = [f"dropped source {d}" for d in dropped]
    if len(docs) < len(run.document_ids):
        warnings.append(f"{len(run.document_ids) - len(docs)} attached files were deleted before research")
    if missing := [k for k in objectives if k not in {f.objective_id for f in findings}]:
        warnings.append(f"no source answered objectives {missing}; the report leaves them out")
    calls = [c for c in (s, w, retry) if c]
    usage = Usage(input_tokens=sum(c.usage["input_tokens"] for c in calls),
                  output_tokens=sum(c.usage["output_tokens"] for c in calls))
    return Outcome(next_queue=queues.WRITE, run_updates={"findings": findings, "warnings": [*run.warnings, *warnings]},
                   usage=usage)


if __name__ == "__main__":
    main(queues.RESEARCH, handle)
