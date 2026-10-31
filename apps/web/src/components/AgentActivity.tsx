"use client";

import { useState } from "react";

import { AGENT, stageTitle } from "@/lib/agents";
import { domain, duration } from "@/lib/format";
import type { Activity, Stage, Timeline } from "@/lib/timeline";

import { PHASE, useNow } from "./ui";

/** True when `ts` happened after `since` (when the page opened): only what changes while the reader watches moves. */
export const fresh = (ts: string | null | undefined, since: number) => !!ts && Date.parse(ts) > since - 500;

/** The agents' live work: one card per agent pass, each with its sub-steps. `since`: when the page opened. */
export function AgentActivity({ timeline, latestOnly = false, since = 0 }: { timeline: Timeline; latestOnly?: boolean; since?: number }) {
  // collapsed: just the latest pass (the one working now, or the last that ran)
  const stages = latestOnly ? timeline.stages.slice(-1) : timeline.stages;
  const pending = latestOnly && timeline.stages.length ? [] : timeline.pending;
  return (
    <ol className="flex flex-col" aria-label="Agent activity">
      {stages.map((s, i) => (
        <StageItem key={s.key} stage={s} last={i === stages.length - 1 && pending.length === 0} since={since} />
      ))}
      {pending.map((agent, i) => (
        <li key={agent} className="relative flex gap-2.5 pb-1.5">
          {i < pending.length - 1 && <span aria-hidden className="absolute top-6 bottom-0 left-[11px] w-px bg-line" />}
          <span aria-hidden className="grid size-6 shrink-0 place-items-center rounded-full border border-dashed border-line text-[11px] text-muted">
            {AGENT[agent].glyph}
          </span>
          <div className="pt-0.5 text-[13px] text-muted">
            {AGENT[agent].name} <span className="text-[11px]">· waiting</span>
          </div>
        </li>
      ))}
    </ol>
  );
}

function StageItem({ stage: s, last, since }: { stage: Stage; last: boolean; since: number }) {
  const live = s.phase === "working" || s.phase === "retrying" || s.phase === "paused";
  const [open, setOpen] = useState<boolean | null>(null); // null: follow live state (open while working)
  const expanded = open ?? live;
  const now = useNow(live);
  const p = PHASE[s.phase];
  const current = live ? s.activities.at(-1)?.detail : undefined;

  const done = s.phase === "done";
  return (
    <li className={`relative flex gap-2.5 pb-1.5 ${fresh(s.startedAt, since) ? "arrive" : ""}`}>
      {!last && <span aria-hidden className="absolute top-6 bottom-0 left-[11px] w-px bg-line" />}
      {/* the line to the next step fills once this one is done: the work moving on */}
      {!last && done && <span aria-hidden className={`absolute top-6 bottom-0 left-[11px] w-px bg-fg/45 ${fresh(s.finishedAt, since) ? "rail-fill" : ""}`} />}
      <span
        aria-hidden
        className={`relative grid size-6 shrink-0 place-items-center rounded-full border text-[11px] ${
          live ? "border-run/30 text-run" : done ? "border-line bg-surface text-fg" : `border-line bg-surface ${p.cls}`
        }`}
      >
        {live && <span className="turning absolute -inset-px rounded-full border-2 border-transparent border-t-run" />}
        <span key={done ? "done" : "glyph"} className={done && fresh(s.finishedAt, since) ? "settle" : undefined}>
          {done ? "✓" : AGENT[s.agent].glyph}
        </span>
      </span>
      <div className="min-w-0 flex-1">
        <button
          type="button"
          onClick={() => setOpen(!expanded)}
          aria-expanded={expanded}
          className="flex w-full items-center justify-between gap-3 rounded-md px-1.5 py-0.5 text-left hover:bg-surface-2"
        >
          <span className="min-w-0">
            <span className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-serif text-[0.98rem] leading-tight">{stageTitle(s.agent, s.revision)}</span>
              <span className="label text-[10px] text-muted">{AGENT[s.agent].name}</span>
            </span>
            {!expanded && current && <span className="block truncate text-xs text-muted">{current}</span>}
          </span>
          <span className="label flex shrink-0 items-center gap-2 text-[10px]">
            <span className={p.cls}>
              <span aria-hidden className={live ? "pulse" : undefined}>{p.glyph}</span> {p.label}
              {s.phase === "retrying" && s.attempt ? ` (attempt ${s.attempt + 1})` : ""}
            </span>
            {s.startedAt && (
              <span className="font-mono text-muted">{duration(s.startedAt, s.finishedAt ?? (live ? now : s.startedAt))}</span>
            )}
            <span aria-hidden className={`text-muted transition ${expanded ? "rotate-90" : ""}`}>›</span>
          </span>
        </button>
        <div className="fold" data-closed={!expanded}>
          <div>
          <ul className="mt-0.5 mb-1 ml-1.5 flex flex-col gap-1 border-l border-line pl-3" inert={!expanded}>
            {s.activities.length === 0 && <li className="text-[13px] text-muted">{live ? "Starting…" : "No sub-steps recorded."}</li>}
            {s.activities.map((a, i) => (
              <ActivityRow key={a.id} a={a} live={live && i === s.activities.length - 1} arriving={fresh(a.ts, since)} />
            ))}
            {s.phase === "paused" && s.pauseUntil && (
              <li className="text-sm text-warn">⏸ Resumes at {new Date(s.pauseUntil).toLocaleTimeString()}</li>
            )}
            {s.phase === "dead" && s.error && (
              <li className="rounded-lg bg-bad/10 px-3 py-2 text-sm text-bad">
                ✕ {s.error}
                {s.deadLetterId && <span className="block text-xs opacity-80">Saved to the dead-letter queue ({s.deadLetterId.slice(0, 8)}) for replay.</span>}
              </li>
            )}
          </ul>
          </div>
        </div>
      </div>
    </li>
  );
}

const ACT_GLYPH: Record<string, string> = {
  tool: "⌕", searching: "⌕", found: "◎", fetching: "⇣", fetched: "▤", ranked: "≡", summarizing: "✎", summarized: "✓",
  planning: "◇", planned: "☰", drafting: "✎", drafted: "▤", checking: "⚙", checked: "⚙", judging: "⚖", judged: "⚖",
  verdict: "⚑", failed: "✕", rate_limited: "⏸",
};

function ActivityRow({ a, live, arriving }: { a: Activity; live: boolean; arriving: boolean }) {
  const d = a.data;
  const cls = a.phase === "failed" ? "text-bad" : a.phase === "rate_limited" ? "text-warn" : live ? "text-fg" : "text-muted";
  return (
    <li className={`text-[13px] ${arriving ? "arrive" : ""}`}>
      <div className={`flex gap-2 ${cls}`}>
        <span aria-hidden className={`w-4 shrink-0 text-center ${live ? "pulse text-run" : ""}`}>{ACT_GLYPH[a.phase] ?? "·"}</span>
        <span className="min-w-0 flex-1 break-words">{a.detail}</span>
        <time className="shrink-0 font-mono text-[11px] text-muted" dateTime={a.ts}>
          {new Date(a.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
        </time>
      </div>
      {a.phase === "planned" && Array.isArray(d.questions) && (
        <ol className="mt-1.5 ml-6 list-decimal space-y-0.5 pl-4 text-muted">
          {(d.questions as string[]).map((q, i) => <li key={i}>{q}</li>)}
        </ol>
      )}
      {a.phase === "found" && Array.isArray(d.pages) && (
        <ul className="mt-1.5 ml-6 flex flex-wrap gap-1.5">
          {[...new Map((d.pages as { url: string; title: string; kind: string }[]).map((p) => [p.url, p])).values()].map((p) => (
            <li key={p.url}>
              <a href={p.url} target="_blank" rel="noopener noreferrer" title={p.title}
                className="inline-flex max-w-64 items-center gap-1 rounded-md border border-line bg-surface px-2 py-0.5 text-xs text-muted hover:text-fg">
                <span className="truncate">{domain(p.url)}</span>
                <span className="shrink-0 rounded bg-surface-2 px-1 text-[0.65rem] uppercase">{p.kind}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
      {a.phase === "fetched" && Array.isArray(d.dropped) && d.dropped.length > 0 && (
        <ul className="mt-1 ml-6 space-y-0.5 text-xs text-muted">
          {(d.dropped as string[]).map((x, i) => <li key={i} className="break-all">✕ {x}</li>)}
        </ul>
      )}
      {a.phase === "checked" && Array.isArray(d.errors) && (
        <ul className="mt-1 ml-6 list-disc space-y-0.5 pl-4 text-xs text-warn">
          {(d.errors as string[]).map((x, i) => <li key={i}>{x}</li>)}
        </ul>
      )}
      {a.phase === "judged" && d.scores != null && <Scores scores={d.scores as Record<string, number>} />}
    </li>
  );
}

export function Scores({ scores }: { scores: Record<string, number> }) {
  return (
    <dl className="mt-2 ml-6 grid max-w-md grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1 text-xs">
      {Object.entries(scores).map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted capitalize">{k.replace(/_/g, " ")}</dt>
          <dd aria-hidden className="h-1.5 overflow-hidden rounded-full bg-surface-2">
            <span className={`block h-full rounded-full ${v >= 0.7 ? "bg-ok" : "bg-warn"}`} style={{ width: `${Math.round(v * 100)}%` }} />
          </dd>
          <dd className="font-mono">{v.toFixed(2)}{v < 0.7 && <span className="text-warn"> ▾</span>}</dd>
        </div>
      ))}
    </dl>
  );
}
