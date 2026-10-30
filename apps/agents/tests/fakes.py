from app.services.llm import Completion

PLAN = {"objectives": [{"id": "o1", "question": "Revenue?"}, {"id": "o2", "question": "Outlook?"}],
        "outline": ["Revenue", "Outlook"]}
FINDINGS = {"findings": [
    {"objective_id": "o1", "summary": "Revenue was $35B.", "sources": [{"url": "https://ir.example.com/q3", "title": "Q3", "kind": "primary", "quote": "Revenue for the third quarter was a record $35.1 billion."}]},
    {"objective_id": "o2", "summary": "Guidance $37.5B.", "sources": [{"url": "https://ir.example.com/q3", "title": "Q3", "kind": "primary", "quote": "Revenue for the third quarter was a record $35.1 billion."},
                                                                      {"url": "https://news.example.com/a", "title": "News", "kind": "news",
                                                                       "quote": "Nvidia guided fourth-quarter revenue to $37.5 billion."}]},
]}
CANDIDATES = {"candidates": [
    {"objective_id": "o1", "url": "https://ir.example.com/q3", "title": "Q3", "kind": "primary"},
    {"objective_id": "o2", "url": "https://news.example.com/a", "title": "News", "kind": "news"},
]}
PAGES = {"https://ir.example.com/q3": "Revenue for the third quarter was a record $35.1 billion, up 94% from a year ago.",
         "https://news.example.com/a": "Nvidia guided fourth-quarter revenue to $37.5 billion, plus or minus two percent."}
DRAFTS = {"findings": [{"objective_id": "o1", "summary": "Revenue was $35.1B.", "passage_ids": ["o1.1"]},
                       {"objective_id": "o2", "summary": "Guidance $37.5B.", "passage_ids": ["o2.1"]}]}
GOOD_REPORT = "# Nvidia Q3\n\n## Revenue\nRevenue was $35.1B [1].\n\n## Outlook\nGuidance is $37.5B [1][2]."
GOOD_SCORES = {"factual_accuracy": 0.9, "citation_accuracy": 0.9, "completeness": 0.9, "source_quality": 0.8}
USAGE = {"input_tokens": 10, "output_tokens": 5}


async def fake_fetch(urls, client=None):
    """Stands in for sources.fetch: no network in tests."""
    urls = list(urls)
    return {u: PAGES[u] for u in urls if u in PAGES}, [f"{u}: HTTP 404" for u in urls if u not in PAGES]


def fake_llm(calls: list, reports=(GOOD_REPORT,), scores=(GOOD_SCORES,)):
    """Stands in for llm.complete. Writer/critic answers come from the lists in order (last one repeats)."""
    async def complete(agent, prompt, **kw):
        calls.append((agent, prompt, kw))
        if agent == "supervisor":
            return Completion("", PLAN, USAGE)
        if agent == "research":
            return Completion("", CANDIDATES if kw.get("tools") else DRAFTS, USAGE)  # search call, then write call
        n = sum(c[0] == agent for c in calls) - 1
        if agent == "write":
            return Completion(reports[min(n, len(reports) - 1)], None, USAGE)
        return Completion("", {"scores": scores[min(n, len(scores) - 1)], "errors": ["e"]}, USAGE)
    return complete
