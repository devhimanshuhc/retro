"""Retrieval quality gate: the zero-token half of scripts/eval.py on the saved page snapshots.
If a ranking or chunking change lowers these, the change made research worse. Raise the floors when it improves."""
from scripts.eval import load, retrieval, summarize

FLOOR = {"hit@6": 0.85, "mrr": 0.70}  # baseline 2026-10-26: hit@6 0.857, recall@6 0.696, mrr 0.702


def test_retrieval_quality_does_not_regress():
    cases, urls = load()
    rows = [retrieval(c, urls) for c in cases]
    broken = [r["id"] for r in rows if not r["relevant_in_pool"]]
    assert not broken, f"labels match no passage (evidence split across passages or page changed): {broken}"
    s = summarize(rows)
    assert all(s[k] >= v for k, v in FLOOR.items()), s


def test_answer_check_handles_formatting_and_alternatives():
    from scripts.eval import correct
    assert correct(["60.9 billion", "126%"], "Revenue was $60.9 billion, up 126% from a year ago.")
    assert correct(["masked language model|masked lm"], "It uses a masked LM objective.")
    assert not correct(["60.9 billion"], "Revenue was $61.9 billion.")
    assert not correct(["x"], "")
