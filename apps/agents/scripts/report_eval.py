"""End-to-end report evals: does a finished report contain the facts it must, avoid known wrong ones, and cite
strong sources, at what cost and time. Unlike scripts/eval.py (research retrieval on saved pages, 0 tokens), this
scores whole reports from live runs.

  uv run python -m scripts.report_eval                       # submit every case to the running system and score it
  uv run python -m scripts.report_eval --case nvidia-q2-fy27 --runs 3   # one case, 3 times (to see run-to-run spread)
  uv run python -m scripts.report_eval --score <run_id> [<run_id> ...] --case nvidia-q2-fy27   # score past runs, 0 tokens

Needs the API and all agent workers running. Each case costs a real run (~60-80k tokens). Facts in
evals/report_cases.json must be checked by hand against a primary source; note where in the case.
"""
import argparse
import json
import math
import re
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent.parent / "evals"
CASES = json.loads((HERE / "report_cases.json").read_text())
FINAL = {"completed", "failed", "canceled"}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% interval for a proportion k/n: honest error bars for small samples."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0, c - h), 3), round(min(1, c + h), 3))


def score(case: dict, run: dict) -> dict:
    """Facts found and wrong, source strength, drafts, tokens and time for one finished run."""
    report = run["revisions"][-1]["report_md"] if run["revisions"] else ""
    body = report.split("\n## Sources\n")[0]
    found = [f["label"] for f in case["must_have"] if any(re.search(p, body, re.I) for p in f["any"])]
    wrong = [w["label"] for w in case.get("must_not", []) if re.search(w["regex"], body, re.I)]
    sources = {s["url"]: s["kind"] for f in run["findings"] for s in f["sources"]}
    secs = (datetime.fromisoformat(run["updated_at"]) - datetime.fromisoformat(run["created_at"])).total_seconds()
    return {
        "run_id": run["id"], "status": run["status"], "drafts": len(run["revisions"]),
        "facts_found": len(found), "facts_total": len(case["must_have"]),
        "missing": [f["label"] for f in case["must_have"] if f["label"] not in found], "wrong": wrong,
        "source_quality": round(sum(k in ("paper", "primary") for k in sources.values()) / max(1, len(sources)), 2),
        "sources": len(sources), "tokens": sum(u["input_tokens"] + u["output_tokens"] for u in run["usage"].values()),
        "seconds": round(secs),
    }


def run_case(api: httpx.Client, case: dict, timeout_s: int = 900) -> dict:
    run_id = api.post("/workflows", json={"prompt": case["prompt"]}).raise_for_status().json()["workflow_run_id"]
    print(f"  {case['id']}: run {run_id} submitted", flush=True)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        run = api.get(f"/workflows/{run_id}").raise_for_status().json()
        if run["status"] in FINAL:
            return run
        time.sleep(5)
    raise TimeoutError(f"run {run_id} still {run['status']} after {timeout_s}s")


def summarize(rows: list[dict]) -> dict:
    k, n = sum(r["facts_found"] for r in rows), sum(r["facts_total"] for r in rows)
    return {
        "runs": len(rows), "completed": sum(r["status"] == "completed" for r in rows),
        "fact_recall": round(k / max(1, n), 3), "fact_recall_95ci": wilson(k, n),
        "wrong_facts": sum(len(r["wrong"]) for r in rows),
        "source_quality_mean": round(statistics.mean(r["source_quality"] for r in rows), 2),
        "tokens_mean": round(statistics.mean(r["tokens"] for r in rows)),
        "seconds_median": statistics.median(r["seconds"] for r in rows),
        "drafts_mean": round(statistics.mean(r["drafts"] for r in rows), 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--case", help="only this case id")
    ap.add_argument("--runs", type=int, default=1, help="runs per case")
    ap.add_argument("--score", nargs="+", metavar="RUN_ID", help="score existing runs instead of submitting (needs --case)")
    args = ap.parse_args()
    cases = [c for c in CASES if not args.case or c["id"] == args.case]
    if not cases or (args.score and len(cases) != 1):
        raise SystemExit("pick one existing case with --case when using --score")

    rows = []
    with httpx.Client(base_url=args.api, timeout=30) as api:
        if args.score:
            for rid in args.score:
                rows.append({"case": cases[0]["id"], **score(cases[0], api.get(f"/workflows/{rid}").raise_for_status().json())})
        else:
            for case in cases:
                for _ in range(args.runs):
                    rows.append({"case": case["id"], **score(case, run_case(api, case))})

    for r in rows:
        print(f"{r['case']:<16} {r['status']:<9} facts {r['facts_found']}/{r['facts_total']}  wrong {len(r['wrong'])}  "
              f"sources {r['source_quality']:.2f} ({r['sources']})  drafts {r['drafts']}  {r['tokens']:,} tok  {r['seconds']}s")
        for m in r["missing"]:
            print(f"{'':18}missing: {m}")
        for w in r["wrong"]:
            print(f"{'':18}WRONG:   {w}")
    summary = summarize(rows)
    print("summary:", summary)
    out = HERE / "results" / f"report-{datetime.now(UTC).strftime('%Y-%m-%dT%H%M%S%z')}.json"
    out.write_text(json.dumps({"summary": summary, "runs": rows}, indent=1))
    print("saved", out.relative_to(HERE.parent))


if __name__ == "__main__":
    main()
