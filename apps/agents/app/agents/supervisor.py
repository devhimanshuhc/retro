from app.agents.base import Outcome, main
from app.models.messages import AgentMessage
from app.models.run import Plan, Usage, WorkflowRun
from app.services import llm, progress, queues

SYSTEM = """You are the planner in a research-and-report pipeline. Turn the user's request into:
- objectives: 2-4 concrete questions a web researcher can answer, ids "o1", "o2", ...
- outline: 3-6 section headings for the final report, in order (plain text, no numbering or markdown).
Stay strictly within the scope of the request."""


async def handle(run: WorkflowRun, msg: AgentMessage) -> Outcome:
    await progress.report("planning", "Breaking the request into research questions and report sections")
    c = await llm.complete("supervisor", run.request, system=SYSTEM, schema=Plan.model_json_schema())
    plan = Plan.model_validate(c.data)  # a bad plan raises, so the job retries
    await progress.report("planned", f"Plan ready: {len(plan.objectives)} questions, {len(plan.outline)} sections",
                          questions=[o.question for o in plan.objectives], outline=plan.outline)
    return Outcome(next_queue=queues.RESEARCH, run_updates={"plan": plan}, usage=Usage(**c.usage))


if __name__ == "__main__":
    main(queues.SUPERVISOR, handle)
