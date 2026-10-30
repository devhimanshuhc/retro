"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { listDeadLetters, listWorkflows } from "@/lib/api";
import type { RunSummary } from "@/lib/types";

import { usePoll } from "./ui";

const DOT: Record<RunSummary["status"], string> = {
  submitted: "○", working: "●", "input-required": "?", completed: "✓", failed: "✕", canceled: "■",
};
const DOT_CLS: Record<RunSummary["status"], string> = {
  submitted: "text-muted", working: "text-run pulse", "input-required": "text-warn", completed: "text-ok",
  failed: "text-bad", canceled: "text-muted",
};

const listAll = () => listWorkflows();
const listDead = () => listDeadLetters();

/** Link to the artifacts page (every finished report). */
export function ArtifactsLink() {
  const active = usePathname() === "/artifacts";
  return (
    <Link href="/artifacts" aria-current={active ? "page" : undefined}
      className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm ${active ? "bg-surface-2 text-fg" : "text-muted hover:bg-surface-2 hover:text-fg"}`}>
      <span aria-hidden className="w-3 text-xs">¶</span> Artifacts
    </Link>
  );
}

/** Link to the connectors page (Google Docs and later others). */
export function ConnectorsLink() {
  const active = usePathname() === "/connectors";
  return (
    <Link href="/connectors" aria-current={active ? "page" : undefined}
      className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm ${active ? "bg-surface-2 text-fg" : "text-muted hover:bg-surface-2 hover:text-fg"}`}>
      <span aria-hidden className="w-3 text-xs">⇄</span> Connectors
    </Link>
  );
}

/** Link to the dead-letter page with the number of jobs waiting for a replay. */
export function DeadLettersLink() {
  const pathname = usePathname();
  const { data } = usePoll(listDead, 10000, pathname);
  const open = data?.filter((d) => !d.replayed_at).length ?? 0;
  const active = pathname === "/dead-letters";
  return (
    <Link href="/dead-letters" aria-current={active ? "page" : undefined}
      className={`flex items-center justify-between rounded-lg px-3 py-1.5 text-sm ${active ? "bg-surface-2 text-fg" : "text-muted hover:bg-surface-2 hover:text-fg"}`}>
      <span className="flex items-center gap-2"><span aria-hidden className="w-3 text-xs">↺</span> Dead letters</span>
      {open > 0 && <span className="label rounded-full bg-bad/15 px-2 py-0.5 text-bad">{open}<span className="sr-only"> waiting</span></span>}
    </Link>
  );
}

function group(runs: RunSummary[]): [string, RunSummary[]][] {
  const today = new Date().toDateString();
  const out: Record<string, RunSummary[]> = { Today: [], Earlier: [] };
  for (const r of runs) out[new Date(r.created_at).toDateString() === today ? "Today" : "Earlier"].push(r);
  return Object.entries(out).filter(([, rs]) => rs.length > 0);
}

/** Run history, like a chat list. Reads the pathname, so the layout wraps it in Suspense (cacheComponents). */
export function RunHistory() {
  const pathname = usePathname();
  const { data, error } = usePoll(listAll, 4000, pathname); // refetch on navigation, e.g. right after a new run

  if (error) return <p className="px-3 text-xs text-bad">✕ Couldn&apos;t load runs</p>;
  if (!data) return <RunHistorySkeleton />;
  if (data.length === 0) return <p className="px-3 text-sm text-muted">No runs yet. Start one.</p>;
  return (
    <nav aria-label="Runs" className="flex flex-col gap-4">
      {group(data.slice(0, 40)).map(([label, runs]) => (
        <div key={label} className="flex flex-col gap-0.5">
          <h2 className="label px-3 pb-1 text-muted">{label}</h2>
          {runs.map((r) => {
            const href = `/runs/${r.id}`;
            const active = pathname === href;
            return (
              <Link
                key={r.id}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm ${active ? "bg-surface-2 text-fg" : "text-muted hover:bg-surface-2 hover:text-fg"}`}
              >
                <span aria-hidden className={`w-3 shrink-0 text-xs ${DOT_CLS[r.status]}`}>{DOT[r.status]}</span>
                <span className="truncate">{r.prompt}</span>
                <span className="sr-only">({r.status})</span>
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

export function RunHistorySkeleton() {
  return (
    <div aria-hidden className="flex flex-col gap-2 px-3">
      {[70, 55, 80, 60].map((w) => (
        <div key={w} className="h-4 animate-pulse rounded bg-surface-2" style={{ width: `${w}%` }} />
      ))}
    </div>
  );
}
