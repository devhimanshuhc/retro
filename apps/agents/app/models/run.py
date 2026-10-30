from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

# A2A task states (docs/research.md); input-required is reserved for a later human-in-the-loop
RunStatus = Literal["submitted", "working", "input-required", "completed", "failed", "canceled"]
TERMINAL: tuple[RunStatus, ...] = ("completed", "failed", "canceled")

StepName = Literal["supervisor", "research", "write", "critic"]


def now() -> datetime:
    # Mongo stores milliseconds; truncate so what we return equals what we read back
    t = datetime.now(UTC)
    return t.replace(microsecond=t.microsecond // 1000 * 1000)


class NextHop(BaseModel):
    queue: str
    revision: int = Field(ge=0)


class StepState(BaseModel):
    """Progress of one actor on a run. A missing step means pending (docs/schema.md)."""

    status: Literal["working", "done"]
    revision: int = Field(ge=0)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    next: NextHop | None = None  # outbox: the message to send after done, re-sent if a crash lost it


class Objective(BaseModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)


class Plan(BaseModel):
    objectives: list[Objective] = Field(min_length=1, max_length=5)
    outline: list[str] = Field(min_length=1, max_length=8)  # report section headings, in order


SourceKind = Literal["paper", "primary", "news", "other"]


class Source(BaseModel):
    url: str = Field(pattern=r"^https?://")
    title: str
    kind: SourceKind  # paper: journal, conference or preprint; primary: filing, official site, dataset, standard
    quote: str = Field(min_length=20, max_length=500)  # verbatim from the page; services/sources.py checks it's there


class Finding(BaseModel):
    objective_id: str
    summary: str = Field(min_length=1)
    sources: list[Source] = Field(min_length=1)


class Scores(BaseModel):
    factual_accuracy: float = Field(ge=0, le=1)
    citation_accuracy: float = Field(ge=0, le=1)
    completeness: float = Field(ge=0, le=1)
    source_quality: float = Field(ge=0, le=1)


class Critique(BaseModel):
    passed: bool
    errors: list[str] = Field(default_factory=list)
    scores: Scores | None = None  # None when the deterministic checks failed and the LLM rubric was skipped


class Revision(BaseModel):
    revision: int = Field(ge=0)
    report_md: str
    created_at: datetime = Field(default_factory=now)
    critique: Critique | None = None


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


def numbered_sources(findings: list[Finding]) -> list[Source]:
    """All sources across findings, deduped by URL. The report cites them as [1], [2], ... in this order."""
    seen: dict[str, Source] = {}
    for f in findings:
        for s in f.sources:
            seen.setdefault(s.url, s)
    return list(seen.values())


class EditRequest(BaseModel):
    """A change the user asked for after a report was done; the writer applies it starting at `revision`."""

    revision: int = Field(ge=1)
    instruction: str = Field(min_length=1, max_length=2000)
    created_at: datetime = Field(default_factory=now)


class WorkflowRun(BaseModel):
    """One workflow run, stored in Mongo `workflow_runs` with `_id` = workflow_run_id."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: uuid4().hex, alias="_id")
    prompt: str = Field(min_length=1)
    status: RunStatus = "submitted"
    revision: int = Field(default=0, ge=0)
    steps: dict[StepName, StepState] = Field(default_factory=dict)
    plan: Plan | None = None
    findings: list[Finding] = Field(default_factory=list)
    revisions: list[Revision] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    usage: dict[StepName, Usage] = Field(default_factory=dict)
    edits: list[EditRequest] = Field(default_factory=list)  # follow-up changes, oldest first
    # last MAX_EVENTS events as JSON (models/events.Event), so a reload rebuilds the timeline; written only by events.emit
    events: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)

    def tokens_used(self) -> int:
        return sum(u.input_tokens + u.output_tokens for u in self.usage.values())

    def active_edit(self, revision: int) -> "EditRequest | None":
        """The user's change request this revision works on (the latest one at or before it), if any."""
        return next((e for e in reversed(self.edits) if e.revision <= revision), None)


class RunUpdate(BaseModel):
    """Fields an actor may change on a run. Unknown fields are rejected so a typo can't write junk."""

    model_config = ConfigDict(extra="forbid")

    # Not Optional: the None default means "not given" and is never written, while an explicit None is rejected
    status: RunStatus = None  # type: ignore[assignment]
    revision: int = Field(default=None, ge=0)  # type: ignore[assignment]
    plan: Plan = None  # type: ignore[assignment]
    findings: list[Finding] = None  # type: ignore[assignment]
    revisions: list[Revision] = None  # type: ignore[assignment]
    warnings: list[str] = None  # type: ignore[assignment]
    usage: dict[StepName, Usage] = None  # type: ignore[assignment]
