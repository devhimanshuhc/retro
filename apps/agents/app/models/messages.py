from pydantic import BaseModel, ConfigDict, Field


class AgentMessage(BaseModel):
    """What travels in a queue between actors: ids only. Everything else is read from the run doc in Mongo."""

    model_config = ConfigDict(extra="forbid")

    workflow_run_id: str = Field(min_length=1)
    revision: int = Field(default=0, ge=0)
