"""Request/response shapes that exist only at the HTTP boundary. Mirrored in apps/web/src/lib/types.ts."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.models.run import RunStatus, StepName


class WorkflowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=4000)


class EditCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(min_length=1, max_length=2000)


class ArtifactSummary(BaseModel):
    """A finished report, for the artifacts list."""

    run_id: str
    title: str
    prompt: str
    revision: int
    sources: int
    edits: int
    created_at: datetime
    updated_at: datetime


Provider = Literal["anthropic", "openai"]


class ProviderStatus(BaseModel):
    id: Provider
    name: str
    source: Literal["app", "env", "login"] | None  # where its key comes from; None = no key


class LlmSettings(BaseModel):
    """GET /settings/llm: which provider the agents use and which have a key (never the keys). active None = not set up."""
    active: Provider | None
    providers: list[ProviderStatus]


class ApiKeySet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr  # never echoed in logs; length is checked in api_keys.verify (pydantic errors echo the input)


class ProviderChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Provider


class ConnectorStatus(BaseModel):
    configured: bool  # the server has a Nango secret key
    connected: bool  # the user has connected the account


class Connector(BaseModel):
    id: str
    name: str
    description: str
    configured: bool
    connected: bool
    account: str | None = None  # e.g. the connected Google account's email


class ConnectSession(BaseModel):
    token: str  # short-lived; opens Nango's Connect UI in the browser


class DocCreated(BaseModel):
    id: str
    url: str


class WorkflowCreated(BaseModel):
    workflow_run_id: str


class RunSummary(BaseModel):
    """A run without its plan, findings and reports, for lists."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    prompt: str
    status: RunStatus
    revision: int
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class WorkerInfo(BaseModel):
    """One live agent process, from its Redis heartbeat (services/workers.py). Gone = no heartbeat for TTL."""

    id: str
    agent: StepName
    host: str
    pid: int
    state: Literal["idle", "busy"] = "idle"
    run_id: str | None = None  # the job in progress, when busy
    revision: int | None = None
    activity: str | None = None  # latest step.progress detail of that job
    jobs_done: int = 0
    started_at: datetime  # process start
    since: datetime  # last state change
    last_seen: datetime


JOB_STATES = ("waiting", "active", "delayed", "failed", "completed")
