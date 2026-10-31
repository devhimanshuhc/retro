import re

from bullmq import UnrecoverableError

from app.agents.base import Outcome, main
from app.models.messages import AgentMessage
from app.models.run import Revision, Usage, WorkflowRun, numbered_sources
from app.services import llm, progress, queues

SYSTEM = """You write markdown reports using only the research findings you are given, no outside facts.
- Start with "# <title>", then use exactly the given section headings as "## " headings, in the given order.
- Cite every factual claim with the given source numbers, like [1] or [2][3]. Never invent a source number.
- Every sentence that contains a number or date must carry a citation.
- Use only numbers and dates the findings state, written as they appear there. Don't compute new ones (sums, shares, growth).
- Each quote was copied by code, verbatim, from the fetched source page. Claims must be backed by the findings and quotes.
- If a section has no supporting findings, keep the heading and say no verified source was found. Don't fill gaps.
- Don't add a sources list; it is appended for you.
- 400-900 words. Output only the report."""


def build_prompt(run: WorkflowRun, revision: int) -> str:
    sources = numbered_sources(run.findings)
    num = {s.url: i for i, s in enumerate(sources, 1)}
    questions = {o.id: o.question for o in run.plan.objectives}
    findings = "\n\n".join(
        f"{questions.get(f.objective_id, f.objective_id)}\n{f.summary}\n"
        + "\n".join(f'[{num[s.url]}] ({s.kind}) "{s.quote}"' for s in f.sources)
        for f in run.findings)
    parts = [f"Request: {run.request}",
             "Section headings:\n" + "\n".join(f"## {h}" for h in run.plan.outline),
             f"Findings:\n{findings}",
             "Sources:\n" + "\n".join(f"[{i}] {s.title} ({s.url})" for i, s in enumerate(sources, 1))]
    prev = next((r for r in run.revisions if r.revision == revision - 1), None)
    edit = run.active_edit(revision)
    if edit and edit.revision == revision and prev:
        parts.append(f"The current report:\n{prev.report_md}\n\nThe user asked for this change:\n{edit.instruction}\n\n"
                     "Rewrite the report with the change made. Keep everything the change doesn't touch. You may add, drop "
                     "or rename sections if the change asks for it. Still use only the findings; if the change needs facts "
                     "the findings don't have, say the sources read don't cover it.")
    elif prev and prev.critique:
        parts.append(f"Your previous draft:\n{prev.report_md}\n\nA reviewer rejected it. Fix every point:\n"
                     + "\n".join(f"- {e}" for e in prev.critique.errors))
        if edit:
            parts.append(f"Keep the change the user asked for: {edit.instruction}")
    return "\n\n".join(parts)


async def handle(run: WorkflowRun, msg: AgentMessage) -> Outcome:
    if run.plan is None or not run.findings:
        raise UnrecoverableError("writer needs a plan and findings")
    prev = next((r for r in run.revisions if r.revision == msg.revision - 1), None)
    edit = run.active_edit(msg.revision)
    fixes = len(prev.critique.errors) if prev and prev.critique and not prev.critique.passed else 0
    await progress.report("drafting", f"Applying your change: {edit.instruction[:80]}" if edit and edit.revision == msg.revision
                          else f"Writing draft {msg.revision + 1} from {len(run.findings)} findings"
                          + (f", fixing {fixes} reviewer points" if fixes else ""))
    c = await llm.complete("write", build_prompt(run, msg.revision), system=SYSTEM)
    sources = "\n".join(f"{i}. {s.title} (your file)" if s.kind == "file" else f"{i}. [{s.title}]({s.url})"
                        for i, s in enumerate(numbered_sources(run.findings), 1))
    report = f"{c.text.strip()}\n\n## Sources\n{sources}\n"
    await progress.report("drafted", f"Draft {msg.revision + 1} ready: ~{len(c.text.split())} words, "
                          f"{len(set(re.findall(r'\[(\d+)\]', c.text)))} sources cited")
    revisions = [r for r in run.revisions if r.revision != msg.revision] + [Revision(revision=msg.revision, report_md=report)]
    return Outcome(next_queue=queues.CRITIC, run_updates={"revisions": revisions}, usage=Usage(**c.usage))


if __name__ == "__main__":
    main(queues.WRITE, handle)
