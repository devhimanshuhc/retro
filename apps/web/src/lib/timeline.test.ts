import assert from "node:assert/strict";
import { test } from "node:test";

import { reduceEvents } from "./timeline.ts";
import type { EventType, RunEvent, StepName, StepState, WorkflowRun } from "./types.ts";

let n = 0;
const ev = (type: EventType, agent: StepName | null, data: Record<string, unknown> = {}, ts = `2026-10-29T10:00:${String(n % 60).padStart(2, "0")}.000Z`): RunEvent =>
  ({ id: `e${n++}`, type, workflow_run_id: "r", agent, ts, data });

const run = (over: Partial<WorkflowRun> = {}): WorkflowRun => ({
  id: "r", prompt: "p", status: "working", revision: 0, steps: {}, plan: null, findings: [], revisions: [],
  warnings: [], usage: {}, edits: [], events: [], created_at: "", updated_at: "", ...over,
});
const snap = (over: Partial<WorkflowRun> = {}) => ev("run.snapshot", null, { run: run(over) });
const step = (status: StepState["status"], revision = 0): StepState =>
  ({ status, revision, started_at: "2026-10-29T09:00:00.000Z", finished_at: null, next: null });

test("sub-steps land on their stage; unstarted agents stay pending", () => {
  const t = reduceEvents([
    snap(),
    ev("step.started", "supervisor", { revision: 0 }),
    ev("step.progress", "supervisor", { revision: 0, phase: "planning", detail: "Breaking it down" }),
    ev("step.done", "supervisor", { revision: 0, next: "agent.research" }),
    ev("step.started", "research", { revision: 0 }),
    ev("step.progress", "research", { revision: 0, phase: "tool", detail: "WebSearch: nvidia q3" }),
  ]);
  assert.deepEqual(t.stages.map((s) => [s.key, s.phase, s.activities.map((a) => a.detail)]), [
    ["supervisor:0", "done", ["Breaking it down"]],
    ["research:0", "working", ["WebSearch: nvidia q3"]],
  ]);
  assert.deepEqual(t.pending, ["write", "critic"]);
});

test("each revision is its own stage: draft 1, review 1, draft 2", () => {
  const t = reduceEvents([
    snap(),
    ev("step.started", "write", { revision: 0 }), ev("step.done", "write", { revision: 0 }),
    ev("step.started", "critic", { revision: 0 }), ev("step.done", "critic", { revision: 0, next: "agent.write" }),
    ev("step.started", "write", { revision: 1 }),
  ]);
  assert.deepEqual(t.stages.map((s) => `${s.key}=${s.phase}`), ["write:0=done", "critic:0=done", "write:1=working"]);
});

test("retry, 429 pause, then success, with each shown as a sub-step", () => {
  const t = reduceEvents([
    snap(),
    ev("step.started", "write", { revision: 1 }),
    ev("step.failed", "write", { revision: 1, attempt: 1, final: false, error: "RateLimited: 429" }),
    ev("rate_limited", "write", { pause_ms: 30000 }, "2026-10-29T10:00:00.000Z"),
  ]);
  const [s] = t.stages;
  assert.equal(s.phase, "paused");
  assert.equal(s.pauseUntil, "2026-10-29T10:00:30.000Z");
  assert.deepEqual(s.activities.map((a) => a.phase), ["failed", "rate_limited"]);
  const done = reduceEvents([snap(), ev("step.started", "write", { revision: 1 }), ev("step.done", "write", { revision: 1 })]);
  assert.equal(done.stages[0].phase, "done");
});

test("final failure dead-letters the stage and fails the run", () => {
  const t = reduceEvents([
    snap(),
    ev("step.started", "critic", { revision: 0 }),
    ev("step.failed", "critic", { revision: 0, attempt: 3, final: true, error: "boom" }),
    ev("dead_lettered", "critic", { dead_letter_id: "dl1" }),
    ev("run.status", null, { status: "failed" }),
  ]);
  assert.deepEqual([t.stages[0].phase, t.stages[0].deadLetterId, t.status, t.pending], ["dead", "dl1", "failed", []]);
});

test("reconnect: the snapshot's stored events replace history and live duplicates are skipped", () => {
  const a = ev("step.started", "supervisor", { revision: 0 });
  const b = ev("step.progress", "supervisor", { revision: 0, phase: "planning", detail: "x" });
  const t = reduceEvents([snap(), a, b, snap({ events: [a, b] }), b]);
  assert.deepEqual(t.log.map((e) => e.id), [a.id, b.id]);
  assert.equal(t.stages[0].activities.length, 1);
});

test("older runs without stored events are rebuilt from run.steps", () => {
  const t = reduceEvents([snap({ status: "completed", steps: { supervisor: step("done"), research: step("done") } })]);
  assert.deepEqual(t.stages.map((s) => `${s.agent}=${s.phase}`), ["supervisor=done", "research=done"]);
  assert.deepEqual(t.pending, []);
});

test("a failed run's unfinished stage is dead; a canceled run's is stopped", () => {
  const failed = reduceEvents([snap({ status: "failed", steps: { supervisor: step("done"), research: step("working") } })]);
  assert.deepEqual(failed.stages.map((s) => s.phase), ["done", "dead"]);
  const canceled = reduceEvents([snap({ status: "canceled", steps: { supervisor: step("working") } })]);
  assert.equal(canceled.stages[0].phase, "stopped");
});
