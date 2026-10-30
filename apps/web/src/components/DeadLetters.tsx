"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { listDeadLetters, replayDeadLetter } from "@/lib/api";
import type { DeadLetter } from "@/lib/types";

const ago = (iso: string) => {
  const s = Math.round((Date.now() - Date.parse(iso)) / 1000);
  return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)}m ago` : s < 86400 ? `${Math.round(s / 3600)}h ago` : `${Math.round(s / 86400)}d ago`;
};
/** Model output is often JSON (a plan or findings that failed validation): show it indented when it parses. */
const pretty = (text: string) => {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
};

type Filter = "open" | "replayed" | "all";

/** Jobs that ran out of attempts, newest first, each with its error, stack, last model output and a replay button.
 * `?run=<id>` narrows the list to one run. */
export function DeadLetters() {
  const runId = useSearchParams().get("run") ?? undefined;
  const [items, setItems] = useState<DeadLetter[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("open");

  const load = useCallback(() => {
    listDeadLetters(runId)
      .then((d) => {
        setItems(d);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [runId]);
  useEffect(load, [load]);

  const shown = (items ?? []).filter((d) => filter === "all" || (filter === "open") === !d.replayed_at);
  const open = (items ?? []).filter((d) => !d.replayed_at).length;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-8 px-5 py-12">
      <header className="flex flex-col gap-3">
        <h1 className="font-serif text-[clamp(2.2rem,4vw,3.2rem)] leading-tight tracking-[-0.02em]">Dead letters</h1>
        <p className="max-w-2xl leading-relaxed">
          Jobs that failed every attempt. Each keeps its error, stack trace and the model&apos;s last output. Replay
          reopens the run and retries the job with fresh attempts.
        </p>
        {runId && (
          <p className="label text-muted">
            Run {runId.slice(0, 8)} · <Link href="/dead-letters" className="text-fg underline underline-offset-2">show all runs</Link>
          </p>
        )}
      </header>

      <div className="flex items-center justify-between gap-4">
        <div role="tablist" aria-label="Filter" className="flex rounded-full border border-line p-0.5">
          {(["open", "replayed", "all"] as const).map((f) => (
            <button key={f} role="tab" aria-selected={filter === f} onClick={() => setFilter(f)}
              className={`label rounded-full px-3 py-1 ${filter === f ? "bg-fg text-bg" : "text-muted hover:text-fg"}`}>
              {f === "open" ? `Not replayed · ${open}` : f === "replayed" ? "Replayed" : "All"}
            </button>
          ))}
        </div>
        <button type="button" onClick={load} className="btn-ghost py-1.5">Refresh</button>
      </div>

      {error ? (
        <p role="alert" className="text-bad">✕ Couldn&apos;t load dead letters: {error}</p>
      ) : items === null ? (
        <div className="h-40 animate-pulse rounded-lg bg-surface-2" />
      ) : shown.length === 0 ? (
        <div className="dot-grid flex flex-col items-center gap-2 rounded-lg border border-dashed border-line px-6 py-16 text-center">
          <p className="font-serif text-2xl">{filter === "open" ? "Nothing waiting" : "Nothing here"}</p>
          <p className="text-muted">
            {filter === "open" ? "No job has run out of attempts, or every one has been replayed." : "No dead letters match this filter."}
          </p>
        </div>
      ) : (
        <ul className="flex flex-col gap-4">
          {shown.map((d) => (
            <DeadLetterCard key={d.id} d={d} onReplayed={(next) => setItems((xs) => xs?.map((x) => (x.id === next.id ? next : x)) ?? null)} />
          ))}
        </ul>
      )}
    </div>
  );
}

function DeadLetterCard({ d, onReplayed }: { d: DeadLetter; onReplayed: (d: DeadLetter) => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const agent = d.queue.replace(/^agent\./, "");

  async function replay() {
    setBusy(true);
    setErr(null);
    try {
      onReplayed(await replayDeadLetter(d.id));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="rounded-lg border border-line bg-surface">
      <div className="flex flex-wrap items-start gap-4 p-5">
        <div className="min-w-0 flex-1">
          <p className="label flex flex-wrap items-center gap-x-3 gap-y-1 text-muted">
            <span className="rounded-full border border-line px-2 py-0.5 text-fg">{agent}</span>
            <span>{d.attempts} attempt{d.attempts === 1 ? "" : "s"}</span>
            {d.revision !== null && <span>revision {d.revision}</span>}
            <time dateTime={d.created_at} title={new Date(d.created_at).toLocaleString()}>{ago(d.created_at)}</time>
          </p>
          <p className="mt-3 break-words font-mono text-[0.85rem] leading-relaxed text-bad">{d.error}</p>
          {d.workflow_run_id ? (
            <Link href={`/runs/${d.workflow_run_id}`} className="label mt-3 inline-block text-muted hover:text-fg">
              Run {d.workflow_run_id.slice(0, 8)} →
            </Link>
          ) : (
            <p className="label mt-3 text-muted">Malformed message: no run</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-2">
          {d.replayed_at ? (
            <p className="label text-ok">✓ Replayed {ago(d.replayed_at)}</p>
          ) : (
            <button type="button" onClick={replay} disabled={busy || !d.workflow_run_id} className="btn-primary disabled:opacity-40">
              {busy ? "Replaying…" : <>Replay <span aria-hidden className="arrow">↺</span></>}
            </button>
          )}
          {err && <p role="alert" className="max-w-56 text-right text-sm text-bad">✕ {err}</p>}
        </div>
      </div>
      <div className="flex flex-col border-t border-line text-sm">
        <Trace title="Stack trace" text={d.stack} />
        {d.raw_output && <Trace title="Last model output" text={pretty(d.raw_output)} />}
        <Trace title="Job data" text={JSON.stringify({ job_id: d.job_id, ...d.data }, null, 2)} />
      </div>
    </li>
  );
}

function Trace({ title, text }: { title: string; text: string }) {
  return (
    <details className="group border-b border-line last:border-b-0">
      <summary className="label flex cursor-pointer items-center gap-2 px-5 py-2.5 text-muted hover:text-fg">
        <span aria-hidden className="transition group-open:rotate-90">›</span> {title}
      </summary>
      <pre className="max-h-96 overflow-auto bg-bg px-5 py-4 text-[0.8rem] leading-relaxed"><code>{text}</code></pre>
    </details>
  );
}
