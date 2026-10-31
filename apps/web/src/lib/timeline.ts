// Pure: run events → what the run page shows. Tested in timeline.test.ts (node --test).
import type { RunEvent, RunStatus, StepName, WorkflowRun } from "./types.ts";

export const STEPS: StepName[] = ["router", "supervisor", "research", "write", "critic"];
export const FINAL: RunStatus[] = ["completed", "failed", "canceled"];

export type StagePhase = "working" | "done" | "retrying" | "paused" | "dead" | "stopped";
export type Activity = { id: string; ts: string; phase: string; detail: string; data: Record<string, unknown> };
/** One pass of one agent: Plan, Research, Draft 1, Review 1, Draft 2, ... */
export type Stage = {
  key: string; // `${agent}:${revision}`
  agent: StepName;
  revision: number;
  phase: StagePhase;
  activities: Activity[]; // sub-steps, oldest first
  attempt?: number; // failed attempts so far
  error?: string;
  pauseUntil?: string; // ISO time the 429 pause ends
  deadLetterId?: string;
  startedAt?: string;
  finishedAt?: string;
};
export type Timeline = {
  run: WorkflowRun | null;
  status: RunStatus | null;
  stages: Stage[]; // in the order they started
  pending: StepName[]; // agents of the first pass that haven't started yet
  log: RunEvent[]; // every event, oldest first, each once
};

/** Apply events in order. A run.snapshot carries the run's stored events: they replace the history, and live
 * events already in it (same id) are skipped, so reconnecting never duplicates or loses a sub-step. */
export function reduceEvents(events: RunEvent[]): Timeline {
  let run: WorkflowRun | null = null;
  let log: RunEvent[] = [];
  for (const e of events) {
    if (e.type === "run.snapshot") {
      run = e.data.run as WorkflowRun;
      const stored = run.events ?? [];
      const ids = new Set(stored.map((s) => s.id));
      log = [...stored, ...log.filter((l) => !ids.has(l.id))];
    } else if (!log.some((l) => l.id === e.id)) {
      log.push(e);
    }
  }
  return build(run, log);
}

function build(run: WorkflowRun | null, log: RunEvent[]): Timeline {
  const stages: Stage[] = [];
  let status = run?.status ?? null;
  const latest = (agent: StepName) => stages.findLast((s) => s.agent === agent);
  const stageFor = (agent: StepName, revision: number, ts: string | undefined) => {
    let s = stages.find((x) => x.agent === agent && x.revision === revision);
    if (!s) stages.push((s = { key: `${agent}:${revision}`, agent, revision, phase: "working", activities: [], startedAt: ts }));
    return s;
  };
  const note = (s: Stage, e: RunEvent, phase: string, detail: string) =>
    s.activities.push({ id: e.id, ts: e.ts, phase, detail, data: e.data });

  for (const e of log) {
    const d = e.data;
    if (e.type === "run.status") {
      status = d.status as RunStatus;
      continue;
    }
    if (!e.agent) continue;
    const revision = typeof d.revision === "number" ? d.revision : (latest(e.agent)?.revision ?? 0);
    const s = stageFor(e.agent, revision, e.ts);
    switch (e.type) {
      case "step.started":
        Object.assign(s, { phase: "working", error: undefined, pauseUntil: undefined });
        break;
      case "step.progress":
        note(s, e, d.phase as string, d.detail as string);
        break;
      case "step.done":
        Object.assign(s, { phase: "done", finishedAt: e.ts, error: undefined, pauseUntil: undefined });
        break;
      case "step.failed":
        Object.assign(s, { phase: d.final ? "dead" : "retrying", attempt: d.attempt, error: d.error });
        note(s, e, "failed", `Attempt ${d.attempt} failed${d.final ? " (final)" : ", retrying"}: ${d.error}`);
        break;
      case "rate_limited": {
        const pauseUntil = new Date(Date.parse(e.ts) + (d.pause_ms as number)).toISOString();
        Object.assign(s, { phase: "paused", pauseUntil });
        note(s, e, "rate_limited", `Rate limited: every ${e.agent} worker paused for ${Math.round((d.pause_ms as number) / 1000)}s`);
        break;
      }
      case "dead_lettered":
        Object.assign(s, { phase: "dead", deadLetterId: d.dead_letter_id });
        break;
    }
  }

  // The run doc is the truth: fill in steps whose events were never stored (older runs) and settle lost ones.
  for (const agent of STEPS) {
    const st = run?.steps[agent];
    if (!st) continue;
    const s = stageFor(agent, st.revision, st.started_at ?? undefined);
    if (st.status === "done") Object.assign(s, { phase: "done", finishedAt: s.finishedAt ?? st.finished_at ?? undefined });
  }
  if (status === "failed" || status === "canceled") {
    // nothing runs any more: an unfinished step on a failed run is the one that died; on a canceled one it stopped
    for (const s of stages) if (s.phase !== "done" && s.phase !== "dead") s.phase = status === "failed" ? "dead" : "stopped";
  }
  stages.sort((a, b) => (a.startedAt ?? "").localeCompare(b.startedAt ?? ""));
  const started = new Set(stages.map((s) => s.agent));
  const pending = status && FINAL.includes(status) ? [] : STEPS.filter((a) => a !== "router" && !started.has(a)); // the router never waits: it goes first
  return { run, status, stages, pending, log };
}
