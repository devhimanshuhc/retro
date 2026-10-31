import type { ArtifactSummary, DocumentInfo, LlmSettings, Provider, Connector, ConnectorStatus, ConnectSession, DeadLetter, DocCreated, QueueCounts, RunStatus, RunSummary, WorkerInfo, WorkflowCreated, WorkflowRun } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
/** Where "Start a run" on the landing page goes: the app locally, the GitHub repo on the public site. */
export const START_URL = process.env.NEXT_PUBLIC_START_URL ?? "/app";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, typeof body?.detail === "string" ? body.detail : `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const createWorkflow = (prompt: string, documentIds: string[] = [], web = true) =>
  call<WorkflowCreated>("/workflows", { method: "POST", body: JSON.stringify({ prompt, document_ids: documentIds, web }) });
export const uploadDocument = async (file: File) => {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/documents`, { method: "POST", body: form }); // the browser sets the multipart header
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => null))?.detail ?? `HTTP ${res.status}`);
  return (await res.json()) as DocumentInfo;
};
export const deleteDocument = async (id: string) => {
  const res = await fetch(`${API_URL}/documents/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!res.ok && res.status !== 404) throw new ApiError(res.status, `HTTP ${res.status}`);
};
export const listWorkflows = (status?: RunStatus) =>
  call<RunSummary[]>(`/workflows${status ? `?status=${status}` : ""}`);
export const getWorkflow = (id: string) => call<WorkflowRun>(`/workflows/${encodeURIComponent(id)}`);
/** WS /workflows/{id}/events: same host as the API, http(s) → ws(s). */
export const eventsUrl = (id: string) =>
  `${API_URL.replace(/^http/, "ws")}/workflows/${encodeURIComponent(id)}/events`;
export const sendMessage = (id: string, message: string) =>
  call<RunSummary>(`/workflows/${encodeURIComponent(id)}/messages`, { method: "POST", body: JSON.stringify({ message }) });
export const editWorkflow = (id: string, instruction: string) =>
  call<RunSummary>(`/workflows/${encodeURIComponent(id)}/edit`, { method: "POST", body: JSON.stringify({ instruction }) });
export const getLlmSettings = () => call<LlmSettings>("/settings/llm");
/** The provider checks the key first (400 with the reason if it's wrong); saving switches the agents to it. The API
 * never sends a key back. */
export const saveApiKey = (provider: Provider, api_key: string) =>
  call<LlmSettings>(`/settings/llm/${provider}/key`, { method: "PUT", body: JSON.stringify({ api_key }) });
export const removeApiKey = (provider: Provider) => call<LlmSettings>(`/settings/llm/${provider}/key`, { method: "DELETE" });
export const chooseProvider = (provider: Provider) =>
  call<LlmSettings>("/settings/llm/active", { method: "PUT", body: JSON.stringify({ provider }) });
export const listConnectors = () => call<Connector[]>("/connectors");
export const disconnectGoogle = async () => {
  const res = await fetch(`${API_URL}/connectors/google`, { method: "DELETE" });
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => null))?.detail ?? `HTTP ${res.status}`);
};
export const getGoogleStatus = () => call<ConnectorStatus>("/connectors/google");
export const createGoogleSession = (returnTo: string) =>
  call<ConnectSession>("/connectors/google/session", { method: "POST", body: JSON.stringify({ return_to: returnTo }) });
export const saveGoogleClient = (clientId: string, clientSecret: string) =>
  call<Connector>("/connectors/google/client", { method: "PUT", body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }) });
export const exportGoogleDoc = (runId: string) =>
  call<DocCreated>(`/workflows/${encodeURIComponent(runId)}/google-doc`, { method: "POST" });
export const listArtifacts = () => call<ArtifactSummary[]>("/artifacts");
export const cancelWorkflow = (id: string) =>
  call<RunSummary>(`/workflows/${encodeURIComponent(id)}/cancel`, { method: "POST" });
export const getWorkers = () => call<WorkerInfo[]>("/workers");
export const getQueues = () => call<QueueCounts>("/queues");
export const listDeadLetters = (workflowRunId?: string) =>
  call<DeadLetter[]>(`/dead-letters${workflowRunId ? `?workflow_run_id=${encodeURIComponent(workflowRunId)}` : ""}`);
export const replayDeadLetter = (id: string) =>
  call<DeadLetter>(`/dead-letters/${encodeURIComponent(id)}/replay`, { method: "POST" });
