"use client";

import { useEffect, useState } from "react";

import type { StagePhase } from "@/lib/timeline";
import type { RunStatus } from "@/lib/types";

const STATUS: Record<RunStatus, { label: string; cls: string; glyph: string }> = {
  submitted: { label: "Queued", cls: "text-muted bg-surface-2", glyph: "○" },
  working: { label: "Working", cls: "text-run bg-run/10", glyph: "●" },
  "input-required": { label: "Needs input", cls: "text-warn bg-warn/10", glyph: "?" },
  completed: { label: "Completed", cls: "text-ok bg-ok/10", glyph: "✓" },
  failed: { label: "Failed", cls: "text-bad bg-bad/10", glyph: "✕" },
  canceled: { label: "Stopped", cls: "text-muted bg-surface-2", glyph: "■" },
};

export function StatusPill({ status }: { status: RunStatus }) {
  const s = STATUS[status];
  return (
    <span className={`label inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 ${s.cls}`}>
      <span aria-hidden className={status === "working" ? "pulse" : undefined}>{s.glyph}</span>
      {s.label}
    </span>
  );
}

export const PHASE: Record<StagePhase, { label: string; glyph: string; cls: string }> = {
  working: { label: "Working", glyph: "●", cls: "text-run" },
  done: { label: "Done", glyph: "✓", cls: "text-ok" },
  retrying: { label: "Retrying", glyph: "↻", cls: "text-warn" },
  paused: { label: "Paused (rate limit)", glyph: "⏸", cls: "text-warn" },
  dead: { label: "Failed, dead-lettered", glyph: "✕", cls: "text-bad" },
  stopped: { label: "Stopped", glyph: "■", cls: "text-muted" },
};

/** Current time, re-rendering every `ms` while `active`; for live elapsed timers. */
export function useNow(active: boolean, ms = 1000): number {
  const [t, setT] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setT(Date.now()), ms);
    return () => clearInterval(id);
  }, [active, ms]);
  return t;
}

/** Poll an async getter every `ms` while the tab is visible, and again whenever `key` changes.
 * Pass a stable `get` (module-level function). */
export function usePoll<T>(get: () => Promise<T>, ms: number, key?: unknown): { data: T | null; error: string | null } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let stopped = false;
    const tick = () => {
      if (document.visibilityState !== "visible") return;
      get()
        .then((d) => {
          if (!stopped) {
            setData(d);
            setError(null);
          }
        })
        .catch((e) => !stopped && setError(e instanceof Error ? e.message : String(e)));
    };
    tick();
    const id = setInterval(tick, ms);
    return () => {
      stopped = true;
      clearInterval(id);
    };
  }, [get, ms, key]);
  return { data, error };
}
