from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.models.run import now


class DeadLetter(BaseModel):
    """A job that used up its attempts or can't succeed, stored in Mongo `dead_letters` (docs/schema.md)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: uuid4().hex, alias="_id")
    queue: str  # the agent queue it failed on, e.g. agent.research
    job_id: str
    workflow_run_id: str | None = None  # None when the message itself was malformed
    revision: int | None = None
    data: dict  # the job data as received
    error: str
    stack: str
    raw_output: str | None = None  # the last LLM output this job got, if any (e.g. a plan that failed validation)
    attempts: int
    created_at: datetime = Field(default_factory=now)
    replayed_at: datetime | None = None
