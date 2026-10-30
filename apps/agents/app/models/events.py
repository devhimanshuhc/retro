from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.run import StepName, now

# step.started {revision} · step.done {revision, next} · step.failed {revision, attempt, final, error}
# step.progress {revision, phase, detail, ...}: a sub-step inside an agent, e.g. one web search
# rate_limited {pause_ms} · dead_lettered {dead_letter_id} · run.status {status} · run.snapshot {run} (WS only, first)
EventType = Literal["step.started", "step.progress", "step.done", "step.failed", "rate_limited", "dead_lettered", "run.status",
                    "run.snapshot"]


class Event(BaseModel):
    """What the dashboard receives over WebSocket. Events are hints to redraw; the run doc stays the truth."""

    id: str = Field(default_factory=lambda: uuid4().hex)  # clients dedupe the snapshot's stored events against live ones
    type: EventType
    workflow_run_id: str
    agent: StepName | None = None  # None for run-level events
    ts: datetime = Field(default_factory=now)
    data: dict[str, Any] = Field(default_factory=dict)
