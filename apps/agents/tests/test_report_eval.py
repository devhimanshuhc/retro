"""The end-to-end report eval's scoring: facts found, wrong facts, source strength, and its error bars."""
from scripts.report_eval import CASES, score, wilson

RUN = {"id": "r", "status": "completed", "created_at": "2026-10-29T10:00:00+00:00", "updated_at": "2026-10-29T10:02:00+00:00",
       "usage": {"research": {"input_tokens": 900, "output_tokens": 100}},
       "findings": [{"sources": [{"url": "https://www.sec.gov/x", "kind": "primary"}, {"url": "https://news.example/y", "kind": "news"}]}],
       "revisions": [{"report_md": "Revenue was $96.2 billion and Data Center revenue $89.0 billion [1]. A year ago EPS was $1.05.\n\n## Sources\n1. $59.7 billion"}]}


def test_score_counts_facts_wrong_facts_and_sources():
    s = score(next(c for c in CASES if c["id"] == "nvidia-q2-fy27"), RUN)
    assert s["facts_found"] == 2 and "Data Center revenue $89.0B" not in s["missing"]
    assert "GAAP net income $59.7B" in s["missing"]  # text in the Sources list doesn't count
    assert s["wrong"] == ["wrong year-ago EPS $1.05 (an aggregator's error)"]
    assert (s["source_quality"], s["tokens"], s["seconds"], s["drafts"]) == (0.5, 1000, 120, 1)


def test_wilson_interval_is_wide_for_small_samples():
    lo, hi = wilson(3, 7)
    assert lo < 0.2 and hi > 0.7  # 3 of 7 says little
    assert wilson(0, 0) == (0.0, 1.0)
