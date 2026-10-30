"""Evals for research: retrieval quality, answer correctness, and an LLM judge. Pages are saved snapshots
(evals/pages/), so runs are repeatable and need no network.

    uv run python -m scripts.eval                       # retrieval only, 0 tokens (pytest runs this too)
    uv run --env-file .env python -m scripts.eval --llm # + findings from Claude, checked by code and by a judge

Retrieval labels are short evidence snippets from the page, not passage ids, so they survive chunking changes.
Each run is saved to evals/results/<UTC time>.json to compare before/after a change.
"""
import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Literal

from pydantic import BaseModel

from app.agents import research
from app.services import llm, sources

EVALS = Path(__file__).parent.parent / "evals"


def norm(text: str) -> str:
    return " " + " ".join(sources._terms(text)).replace("$", "") + " "


def correct(expect: list[str], answer: str) -> bool:
    """Every expected fact is stated; "a|b" accepts either wording."""
    return bool(answer) and all(any(norm(alt) in norm(answer) for alt in x.split("|")) for x in expect)


def load() -> tuple[list[dict], dict[str, str]]:
    cases = json.loads((EVALS / "cases.json").read_text())
    urls = json.loads((EVALS / "pages" / "_urls.json").read_text())
    return cases, urls


def setup(case: dict, urls: dict[str, str]):
    """The case as research sees it: one objective, candidates = the case's pages, texts = the snapshots."""
    cands = [research.Candidate(objective_id="q", url=urls[slug], title=slug, kind=kind)
             for slug, kind in case["pages"].items()]
    texts = {urls[s]: (EVALS / "pages" / f"{s}.txt").read_text() for s in case["pages"]}
    return {"q": case["question"]}, cands, texts


def retrieval(case: dict, urls: dict[str, str]) -> dict:
    objectives, cands, texts = setup(case, urls)
    relevant = lambda p: any(norm(e) in norm(p) for e in case["evidence"])
    pool = [p for u in texts for p in sources.passages(texts[u])]
    passages, blocks = research.retrieve(objectives, cands, texts, case["question"])
    top = [p for _, p in passages.values()]
    hits = [i for i, p in enumerate(top, 1) if relevant(p)]
    total = sum(map(relevant, pool))
    return {"id": case["id"], "relevant_in_pool": total, "pool": len(pool), "hit": bool(hits),
            "recall": len(hits) / min(total, len(top)) if total and top else 0.0,
            "rr": 1 / hits[0] if hits else 0.0, "ranks": hits,
            "_passages": passages, "_blocks": blocks, "_objectives": objectives}


class Claim(BaseModel):
    claim: str
    supported: bool


class Verdict(BaseModel):
    sufficient: Literal["yes", "partly", "no"]
    claims: list[Claim]


JUDGE = """You grade a research step. Given a question, the passages it was answered from, and the answer:
1. sufficient: do the passages contain enough to answer the question fully ("yes"), partly, or not at all ("no")?
2. claims: split the answer into atomic factual claims; for each, supported=true only if the passages state it.
Judge only against the passages; ignore what you know."""


async def answer(case: dict, r: dict) -> dict:
    findings, w = await research.write_findings(research.brief_for(case["question"], r["_objectives"]),
                                                r["_objectives"], r["_passages"], r["_blocks"])
    summary = findings[0].summary if findings else ""
    cited = "\n\n".join(f"{s.title} ({s.url}):\n{s.quote}" for f in findings for s in f.sources)
    out = {"summary": summary, "correct": correct(case["expect"], summary),
           "tokens": w.usage}
    if summary:
        j = await llm.complete("critic", f"Question: {case['question']}\n\nPassages:\n{cited}\n\nAnswer:\n{summary}",
                               system=JUDGE, schema=Verdict.model_json_schema())
        v = Verdict.model_validate(j.data)
        out |= {"sufficient": v.sufficient, "faithfulness": mean(c.supported for c in v.claims) if v.claims else 0.0,
                "unsupported": [c.claim for c in v.claims if not c.supported]}
    return out


def summarize(rows: list[dict]) -> dict:
    s = {"cases": len(rows), "hit@6": mean(r["hit"] for r in rows), "recall@6": mean(r["recall"] for r in rows),
         "mrr": mean(r["rr"] for r in rows)}
    if "correct" in rows[0]:
        judged = [r for r in rows if "faithfulness" in r]
        s |= {"answer_accuracy": mean(r["correct"] for r in rows),
              "faithfulness": mean(r["faithfulness"] for r in judged) if judged else 0.0,
              "context_sufficient": mean(r.get("sufficient") == "yes" for r in rows)}
    return {k: round(v, 3) if isinstance(v, float) else v for k, v in s.items()}


async def run(with_llm: bool) -> dict:
    cases, urls = load()
    rows = [retrieval(c, urls) for c in cases]
    if with_llm:
        for c, r in zip(cases, rows):
            r |= await answer(c, r)
    for r in rows:
        for k in [k for k in r if k.startswith("_")]:
            del r[k]
    return {"at": datetime.now(UTC).isoformat(timespec="seconds"),
            "config": {"per_objective": research.PER_OBJECTIVE, "per_source": research.PER_SOURCE,
                       "weights": research.WEIGHT, "llm": with_llm},
            "summary": summarize(rows), "cases": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="also generate findings and judge them (uses tokens)")
    result = asyncio.run(run(ap.parse_args().llm))
    for r in result["cases"]:
        line = f"{r['id']:<22} hit={'Y' if r['hit'] else 'n'} ranks={r['ranks']} relevant={r['relevant_in_pool']}/{r['pool']}"
        if "correct" in r:
            line += (f"  correct={'Y' if r['correct'] else 'n'} faithful={r.get('faithfulness', '-')}"
                     f" sufficient={r.get('sufficient', '-')}")
        print(line)
    print("summary:", result["summary"])
    out = EVALS / "results" / f"{result['at'].replace(':', '')}.json"
    out.write_text(json.dumps(result, indent=1))
    print("saved", out.relative_to(EVALS.parent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
