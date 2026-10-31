import logging
import re

from bullmq import UnrecoverableError
from pydantic import BaseModel, Field

import config
from app.agents.base import Outcome, main
from app.models.messages import AgentMessage
from app.models.run import Critique, Scores, Usage, WorkflowRun, numbered_sources
from app.services import llm, progress, queues

log = logging.getLogger("agent.critic")

PASS_SCORE = 0.7
GATED = ("factual_accuracy", "citation_accuracy", "completeness")  # what the writer can fix; must all reach PASS_SCORE

SYSTEM = """You review a research report against its research findings. Each quote is a passage that code copied
verbatim from the fetched source page. So judge the report only against the findings and quotes below.
Never speculate about whether a source, site or URL is real, and never ask for sources that aren't listed.

Score each 0.0-1.0, calibrated: 1.0 only if you found no problem at all; 0.7 = acceptable with minor issues.
- factual_accuracy: every claim is supported by the findings/quotes; numbers and dates match exactly
- citation_accuracy: each [n] points to a source whose finding or quote supports that exact claim
- completeness: answers the request, fills every section, says so where evidence is missing
- source_quality: share of sources that are papers or primary sources (by their listed kind)
In errors, list only problems the writer can fix with these findings (wrong number, unsupported claim, citation on
the wrong source, missing section). Quote the offending sentence. Empty list if none. At most 8 errors, one line each.
Answer only with the structured result: no analysis or commentary before it."""


NUM = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")


def numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in NUM.findall(re.sub(r"\[\d+\]", "", text))}


def evidence(run: WorkflowRun) -> str:
    """Everything a report may take numbers from: the request and the findings (summaries, page quotes, titles)."""
    return "\n".join([run.request, *(f.summary for f in run.findings),
                      *(f"{s.title} {s.quote}" for f in run.findings for s in f.sources)])


SUMMARY = """Tell the user their report is ready. In 2-3 plain sentences, under 60 words: what the report covers and its one
or two most important findings. Use only facts and numbers written in the report. No citations, no markdown, no greeting."""


async def summarize(report_md: str) -> tuple[str, Usage | None]:
    """A short reply about a passed report, on the small model. Every number in it must be in the report (checked here);
    otherwise, or if the call fails, a plain sentence instead. Never fails the review it follows."""
    title = next((line[2:].strip() for line in report_md.splitlines() if line.startswith("# ")), "your report")
    fallback = f"Your report is ready: {title}. It passed review, and every claim in it is cited."
    try:
        c = await llm.complete("router", report_md[:8000], system=SUMMARY, think=False)
    except Exception as e:
        log.warning("summary call failed, using the plain sentence: %r", e)
        return fallback, None
    text = c.text.strip()
    if extra := numbers(text) - numbers(report_md):
        log.warning("summary states numbers the report doesn't (%s), using the plain sentence", sorted(extra)[:5])
    elif not text or len(text) > 900:
        log.warning("summary empty or too long (%d chars), using the plain sentence", len(text))
    else:
        return text, Usage(**c.usage)
    return fallback, Usage(**c.usage)


class Rubric(BaseModel):
    scores: Scores
    errors: list[str] = Field(max_length=8)


def check(report_md: str, outline: list[str], n_sources: int, evidence: str) -> list[str]:
    """Deterministic checks, run before the LLM rubric. Returns the errors (empty = passed)."""
    body = report_md.split("\n## Sources\n")[0]
    headings = {h.strip().lower() for h in re.findall(r"^## (.+)$", body, re.M)}
    errors = [f'missing section "## {h}"' for h in outline if h.strip().lower() not in headings]
    uncited = [s.strip() for line in body.splitlines() if not line.lstrip().startswith("#")
               for s in re.split(r"(?<=[.!?])\s+", line)
               if re.search(r"\d", re.sub(r"\[\d+\]", "", s)) and not re.search(r"\[\d+\]", s)]
    if uncited:
        errors.append("every sentence with a number or date needs a citation: " + "; ".join(f'"{s}"' for s in uncited[:5]))
    # A number the findings never state is invented or miscopied; the LLM rubric lets these through (scores ~0.85).
    text = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
    if unknown := sorted(numbers(text) - numbers(evidence)):
        errors.append(f"numbers not stated in the findings (use only the findings' numbers): {', '.join(unknown[:10])}")
    cites = {int(n) for n in re.findall(r"\[(\d+)\]", body)}
    if not cites:
        errors.append("no citations: cite the sources like [1]")
    if bad := sorted(n for n in cites if not 1 <= n <= n_sources):
        errors.append(f"citations {bad} match no source (valid: 1-{n_sources})")
    return errors


async def handle(run: WorkflowRun, msg: AgentMessage) -> Outcome:
    draft = next((r for r in run.revisions if r.revision == msg.revision), None)
    if draft is None or run.plan is None:
        raise UnrecoverableError(f"no report for revision {msg.revision}")
    usage = None
    await progress.report("checking", "Code checks: sections, citations, and every number against the findings")
    edit = run.active_edit(msg.revision)
    outline = [] if edit else run.plan.outline  # a requested change may add, drop or rename sections
    if errors := check(draft.report_md, outline, len(numbered_sources(run.findings)), evidence(run)):
        critique = Critique(passed=False, errors=errors)  # cheap fail: skip the LLM
        await progress.report("checked", f"Code checks found {len(errors)} problems; skipping the LLM review", errors=errors)
    else:
        await progress.report("checked", "Code checks passed")
        await progress.report("judging", "Scoring factual accuracy, citations, completeness and source quality")
        num = {s.url: i for i, s in enumerate(numbered_sources(run.findings), 1)}
        findings = "\n\n".join(f"{f.objective_id}: {f.summary}\n" + "\n".join(
            f'[{num[s.url]}] {s.kind}, {s.title} ({s.url}): "{s.quote}"' for s in f.sources) for f in run.findings)
        change = f"\n\nThe user then asked for this change, which the report must now reflect: {edit.instruction}" if edit else ""
        c = await llm.complete("critic", f"Request: {run.request}{change}\n\nFindings:\n{findings}\n\nReport:\n{draft.report_md}",
                               system=SYSTEM, schema=Rubric.model_json_schema(), think=False)
        rubric = Rubric.model_validate(c.data)
        # source quality is counted, not judged: the share of the report's sources that are papers or primary
        cited = numbered_sources(run.findings)
        scores = {**rubric.scores.model_dump(),
                  "source_quality": round(sum(s.kind in ("file", "paper", "primary") for s in cited) / max(1, len(cited)), 2)}
        critique = Critique(passed=all(scores[k] >= PASS_SCORE for k in GATED), errors=rubric.errors, scores=Scores(**scores))
        usage = Usage(**c.usage)
        await progress.report("judged", " · ".join(f"{k.replace('_', ' ')} {v:.2f}" for k, v in scores.items()), scores=scores)

    summary = None
    if critique.passed:
        summary, su = await summarize(draft.report_md)
        if su:
            usage = Usage(input_tokens=(usage.input_tokens if usage else 0) + su.input_tokens,
                          output_tokens=(usage.output_tokens if usage else 0) + su.output_tokens)
    updates = {"revisions": [r.model_copy(update={"critique": critique, "summary": summary}) if r.revision == msg.revision
                             else r for r in run.revisions]}
    await progress.report("verdict", "Passed review" if critique.passed else
                          f"Sent back to the writer with {len(critique.errors)} points", passed=critique.passed)
    if critique.passed:
        if critique.scores.source_quality < PASS_SCORE:  # the writer can't find new sources, so warn, don't loop
            updates["warnings"] = [*run.warnings, f"weak sources: source_quality {critique.scores.source_quality}"]
        return Outcome(run_updates={**updates, "status": "completed"}, usage=usage)
    if msg.revision + 1 - (edit.revision if edit else 0) >= config.MAX_REVISIONS:  # the cap restarts per change request
        warning = f"MAX_REVISIONS ({config.MAX_REVISIONS}) reached; the last report failed review"
        return Outcome(run_updates={**updates, "status": "completed", "warnings": [*run.warnings, warning]}, usage=usage)
    return Outcome(next_queue=queues.WRITE, next_revision=msg.revision + 1,
                   run_updates={**updates, "revision": msg.revision + 1}, usage=usage)


if __name__ == "__main__":
    main(queues.CRITIC, handle)
