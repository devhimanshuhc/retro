"use client";

import { useState } from "react";

import { AGENT, stageTitle } from "@/lib/agents";
import { domain, duration } from "@/lib/format";
import type { Activity, Stage, Timeline } from "@/lib/timeline";

import { PHASE, useNow } from "./ui";

/** The agents' live work: one card per agent pass, each with its sub-steps. */
export function AgentActivity({ timeline, latestOnly = false }: { timeline: Timeline; latestOnly?: boolean }) {
  // collapsed: just the latest pass (the one working now, or the last that ran)
  const stages = latestOnly ? timeline.stages.slice(-1) : timeline.stages;
  const pending = latestOnly && timeline.stages.length ? [] : timeline.pending;
  return (
    <ol className="flex flex-col" aria-label="Agent activity">
      {stages.map((s, i) => (
        <StageItem key={s.key} stage={s} last={i === stages.length - 1 && pending.length === 0} />
      ))}
      {pending.map((agent, i) => (
        <li key={agent} className="relative flex gap-3 pb-3">
          {i < pending.length - 1 && <span aria-hidden className="absolute top-8 bottom-0 left-[15px] w-px bg-line" />}
          <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full border border-dashed border-line text-sm text-muted">
            {AGENT[agent].glyph}
          </span>
          <div className="pt-1.5 text-sm text-muted">
            {AGENT[agent].name} <span className="text-xs">· waiting</span>
          </div>
        </li>
      ))}
    </ol>
  );
}

function StageItem({ stage: s, last }: { stage: Stage; last: boolean }) {
  const live = s.phase === "working" || s.phase === "retrying" || s.phase === "paused";
  const [open, setOpen] = useState<boolean | null>(null); // null: follow live state (open while working)
  const expanded = open ?? live;
  const now = useNow(live);
  const p = PHASE[s.phase];
  const current = live ? s.activities.at(-1)?.detail : undefined;

  return (
    <li className="relative flex gap-3 pb-3">
      {!last && <span aria-hidden className="absolute top-8 bottom-0 left-[15px] w-px bg-line" />}
      <span
        aria-hidden
        className={`relative grid size-8 shrink-0 place-items-center rounded-full border text-sm ${
          live ? "border-run bg-run/10 text-run" : s.phase === "done" ? "border-line bg-surface text-fg" : `border-line bg-surface ${p.cls}`
        }`}
      >
        {AGENT[s.agent].glyph}
      </span>
      <div className="min-w-0 flex-1">
        <button
          type="button"
          onClick={() => setOpen(!expanded)}
          aria-expanded={expanded}
          className="flex w-full items-start justify-between gap-3 rounded-lg px-2 py-1 text-left hover:bg-surface-2"
        >
          <span className="min-w-0">
            <span className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-serif text-lg leading-tight">{stageTitle(s.agent, s.revision)}</span>
              <span className="label text-muted">{AGENT[s.agent].name}</span>
            </span>
            {!expanded && current && <span className="mt-0.5 block truncate text-sm text-muted">{current}</span>}
          </span>
          <span className="label flex shrink-0 items-center gap-2 pt-1">
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
        {expanded && (
          <ul className="mt-1 flex flex-col gap-1.5 border-l border-line pl-3 ml-2">
            {s.activities.length === 0 && <li className="text-sm text-muted">{live ? "Starting…" : "No sub-steps recorded."}</li>}
            {s.activities.map((a, i) => (
              <ActivityRow key={a.id} a={a} live={live && i === s.activities.length - 1} />
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
        )}
      </div>
    </li>
  );
}

const ACT_GLYPH: Record<string, string> = {
  tool: "⌕", searching: "⌕", found: "◎", fetching: "⇣", fetched: "▤", ranked: "≡", summarizing: "✎", summarized: "✓",
  planning: "◇", planned: "☰", drafting: "✎", drafted: "▤", checking: "⚙", checked: "⚙", judging: "⚖", judged: "⚖",
  verdict: "⚑", failed: "✕", rate_limited: "⏸",
};

function ActivityRow({ a, live }: { a: Activity; live: boolean }) {
  const d = a.data;
  const cls = a.phase === "failed" ? "text-bad" : a.phase === "rate_limited" ? "text-warn" : live ? "text-fg" : "text-muted";
  return (
    <li className="text-sm">
      <div className={`flex gap-2 ${cls}`}>
        <span aria-hidden className={`w-4 shrink-0 text-center ${live ? "pulse text-run" : ""}`}>{ACT_GLYPH[a.phase] ?? "·"}</span>
        <span className="min-w-0 flex-1 break-words">{a.detail}</span>
        <time className="shrink-0 font-mono text-xs text-muted" dateTime={a.ts}>
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
