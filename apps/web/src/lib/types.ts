// Mirrors the pydantic models in apps/agents/app/models/. Change both in the same edit.
// Datetimes arrive as ISO strings.

/** app/models/run.py */
export type RunStatus = "submitted" | "working" | "input-required" | "completed" | "failed" | "canceled";
export type StepName = "router" | "supervisor" | "research" | "write" | "critic";
export type SourceKind = "paper" | "primary" | "news" | "other" | "file"; // file: one the user uploaded (url doc://<id>)

export type NextHop = { queue: string; revision: number };
export type StepState = {
  status: "working" | "done";
  revision: number;
  started_at: string | null;
  finished_at: string | null;
  next: NextHop | null;
};
export type Objective = { id: string; question: string };
export type Plan = { objectives: Objective[]; outline: string[] };
export type Source = { url: string; title: string; kind: SourceKind; quote: string };
export type Finding = { objective_id: string; summary: string; sources: Source[] };
export type Scores = {
  factual_accuracy: number;
  citation_accuracy: number;
  completeness: number;
  source_quality: number;
};
/** scores is null when the deterministic checks failed and the LLM rubric was skipped. */
export type Critique = { passed: boolean; errors: string[]; scores: Scores | null };
export type Revision = { revision: number; report_md: string; created_at: string; critique: Critique | null; summary?: string | null };
/** One message of the conversation the router handles (models/run.Turn). */
export type Turn = { role: "user" | "assistant"; text: string; created_at: string };
export type Intent = "chat" | "decline" | "research";
export type Usage = { input_tokens: number; output_tokens: number };

/** A change the user asked for after the report was done; the writer applies it starting at `revision`. */
export type EditRequest = { revision: number; instruction: string; created_at: string };

export type WorkflowRun = {
  id: string;
  prompt: string;
  turns?: Turn[];
  intent?: Intent | null;
  brief?: string | null;
  document_ids: string[];
  web: boolean;
  status: RunStatus;
  revision: number;
  steps: Partial<Record<StepName, StepState>>;
  plan: Plan | null;
  findings: Finding[];
  revisions: Revision[];
  warnings: string[];
  usage: Partial<Record<StepName, Usage>>;
  edits: EditRequest[];
  events: RunEvent[]; // last 500 events, oldest first
  created_at: string;
  updated_at: string;
};

/** app/models/api.py */
export type WorkflowCreate = { prompt: string };
export type WorkflowCreated = { workflow_run_id: string };
export type EditCreate = { instruction: string };
/** app/models/api.py: connectors (Google Docs). */
export type Provider = "anthropic" | "openai";
/** GET /settings/llm: the provider the agents use and where each key comes from (never the keys). active null = not set up. */
export type LlmSettings = {
  active: Provider | null;
  providers: { id: Provider; name: string; source: "app" | "env" | "login" | null }[];
};
export type ConnectorStatus = { configured: boolean; connected: boolean };
export type Connector = { id: string; name: string; description: string; configured: boolean; connected: boolean; account: string | null; redirect_uri: string | null };
export type ConnectSession = { url: string };
export type DocCreated = { id: string; url: string };
/** GET /artifacts: a finished report. */
export type ArtifactSummary = {
  run_id: string;
  title: string;
  prompt: string;
  revision: number;
  sources: number;
  edits: number;
  created_at: string;
  updated_at: string;
};
export type RunSummary = Pick<WorkflowRun, "id" | "prompt" | "status" | "revision" | "warnings" | "created_at" | "updated_at">;
/** GET /workers: live agent processes (Redis heartbeat). */
export type WorkerInfo = {
  id: string;
  agent: StepName;
  host: string;
  pid: number;
  state: "idle" | "busy";
  run_id: string | null;
  revision: number | null;
  activity: string | null;
  jobs_done: number;
  started_at: string;
  since: string;
  last_seen: string;
};
export type JobState = "waiting" | "active" | "delayed" | "failed" | "completed";
/** GET /queues: job counts per queue name, e.g. counts["agent.write"].waiting */
export type QueueCounts = Record<string, Record<JobState, number>>;

/** app/models/dead_letter.py: a job that ran out of attempts. */
export type DeadLetter = {
  id: string;
  queue: string;
  job_id: string;
  workflow_run_id: string | null;
  revision: number | null;
  data: Record<string, unknown>;
  error: string;
  stack: string;
  raw_output: string | null;
  attempts: number;
  created_at: string;
  replayed_at: string | null;
};

/** app/models/events.py: WS /workflows/{id}/events. The first message is always run.snapshot. */
export type EventType =
  | "step.started" // {revision}
  | "step.progress" // {revision, phase, detail, ...}: a sub-step, e.g. one web search
  | "step.done" // {revision, next: queue name | null}
  | "step.failed" // {revision, attempt, final, error}
  | "rate_limited" // {pause_ms}
  | "dead_lettered" // {dead_letter_id}
  | "run.status" // {status}; the socket closes after a final one
  | "run.snapshot"; // {run: WorkflowRun}
export type RunEvent = {
  id: string;
  type: EventType;
  workflow_run_id: string;
  agent: StepName | null;
  ts: string;
  data: Record<string, unknown>;
};

export type DocumentInfo = { id: string; name: string; size: number; chars: number; created_at: string };
