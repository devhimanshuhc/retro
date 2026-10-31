"""The router: reads every message first, on a small, cheap model, and decides whether to answer it in chat, decline
it, or start research. Only research reaches the planner, so "hey" costs a few hundred tokens, not a report."""
import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.base import Outcome, main
from app.models.messages import AgentMessage
from app.models.run import Turn, Usage, WorkflowRun
import config
from app.services import limits, llm, progress, queues

SYSTEM = """You are Retro, a research assistant. Retro's agents search the web (and files the user attaches), read real
sources, and write a cited report that a reviewer checks before the user sees it. A report takes a few minutes.

Read the conversation and decide what to do with the user's latest message:
- "research": the user wants information that needs sources: a topic, a company, a market, a paper, a person's public
  work, a comparison, a question of fact. This includes short questions ("nvidia earnings?"). In research_request,
  write the request as one standalone sentence with everything the conversation established. In reply, one short
  sentence saying what you'll research.
- "chat": greetings, thanks, questions about Retro itself (what it does, how long it takes, how to attach files or
  edit a report), or the user hasn't said what to research yet. Reply briefly and warmly (1-3 sentences) and, when it
  fits, suggest one concrete thing Retro could research for them.
- "decline": tasks Retro isn't for: writing code, homework, creative writing, personal advice, translation, chatting
  about unrelated things at length. Say kindly that Retro writes cited research reports, and offer how the request
  could become one.
Never answer a factual question yourself: facts need sources, so route them to research. Never question whether an event,
company or person is real, recent or verified: your own knowledge is out of date, and finding out is research's job. A
request that asks for a report, research, an investigation, an analysis or a summary of a topic is always "research".
Plain text, no markdown."""

# a plain ask for a report always researches, whatever the small model thought (it once asked to "verify" a recent event)
ASKS_FOR_REPORT = re.compile(r"\b(report|research|investigat\w*|analy[sz]\w*|deep[- ]dive|brief(ing)?|look into|find out|summar\w*)\b", re.I)

HISTORY = 12  # messages of context the router sees


class Route(BaseModel):
    intent: Literal["chat", "decline", "research"]
    reply: str = Field(min_length=1, max_length=600)
    research_request: str = Field(default="", max_length=1000)


async def handle(run: WorkflowRun, msg: AgentMessage) -> Outcome:
    turns = run.turns or [Turn(role="user", text=run.prompt)]
    if run.document_ids and msg.revision == 0:      # files attached: research them, no need to ask the model
        route, usage = Route(intent="research", reply="I'll read your files and write a cited report."), None
    else:
        await progress.report("routing", "Reading your message")
        convo = "\n".join(f"{t.role}: {t.text}" for t in turns[-HISTORY:])
        c = await llm.complete("router", convo, system=f"{SYSTEM}\n\nToday is {date.today():%B %-d, %Y}.",
                               schema=Route.model_json_schema(), think=False)
        route, usage = Route.model_validate(c.data), Usage(**c.usage)
        if route.intent == "chat" and ASKS_FOR_REPORT.search(turns[-1].text):   # declines are left alone
            route = Route(intent="research", reply="I'll research that and write a cited report.",
                          research_request=route.research_request)
    reply = Turn(role="assistant", text=route.reply)
    await progress.report("routed", {"research": "Starting research", "chat": "Replied", "decline": "Replied"}[route.intent],
                          intent=route.intent)
    if route.intent != "research":
        return Outcome(run_updates={"intent": route.intent, "turns": [*turns, reply], "status": "completed"}, usage=usage)
    if (lc := limits.client.get()) and (wait := await limits.hit(lc[0], f"{lc[1]}:ratelimit:research", config.RUNS_PER_WINDOW,
                                                                     config.RUN_WINDOW_S)):
        note = (f"You've started {config.RUNS_PER_WINDOW} reports in the last {config.RUN_WINDOW_S // 60} minutes, the limit "
                f"set for this install. Ask me again in about {wait // 60 + 1} minutes and I'll research it.")
        return Outcome(run_updates={"intent": "chat", "turns": [*turns, Turn(role="assistant", text=note)], "status": "completed"},
                       usage=usage)
    updates = {"intent": "research", "turns": [*turns, reply]}
    if msg.revision > 0 and route.research_request.strip():   # a later message: the brief carries the conversation
        updates["brief"] = route.research_request.strip()
    return Outcome(next_queue=queues.SUPERVISOR, next_revision=0, usage=usage, run_updates=updates)


if __name__ == "__main__":
    main(queues.ROUTER, handle)
