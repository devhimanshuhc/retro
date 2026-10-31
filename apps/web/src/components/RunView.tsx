"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { cancelWorkflow, editWorkflow, listDeadLetters, sendMessage } from "@/lib/api";
import { duration, parseWarning, reportTitle, usageLine } from "@/lib/format";
import { FINAL } from "@/lib/timeline";
import { useRunEvents, type Connection } from "@/lib/useRunEvents";

import { AgentActivity, fresh } from "./AgentActivity";
import { Mark } from "./Mark";
import { Composer } from "./Composer";
import { ReportArtifact } from "./ReportView";
import { ResizeHandle, usePanelWidth, useViewportWidth } from "./Resizable";
import { StatusPill, useNow } from "./ui";

const CONNECTION: Partial<Record<Connection, string>> = {
  connecting: "Connecting…",
  reconnecting: "Connection lost, reconnecting…",
  rejected: "Live updates refused: this site's origin isn't in the API's WEB_ORIGINS",
};

// dead-letter errors that mean the model key is missing, wrong, revoked or out of credit
const KEY_ERROR = /No model API key|authentication_failed|billing_error|LLM 401|insufficient.quota|api.key/i;

/** One run as a chat: the request, the agents' live work, then the report. */
export function RunView({ id }: { id: string }) {
  const { timeline, connection, reopen } = useRunEvents(id);
  const { run, status } = timeline;
  const finished = status != null && FINAL.includes(status);
  const now = useNow(!finished);
  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState<string | null>(null);
  const [choice, setChoice] = useState<boolean | null>(null);
  const [teamOpen, setTeamOpen] = useState<boolean | null>(null); // null: open while working, closed for an old run
  const [since] = useState(() => Date.now()); // when the page opened: only what changes after this animates
  const [scroller, content] = useFollow();
  const [panelWidth, setPanelWidth] = usePanelWidth("retro.panel.width", 680);
  const vw = useViewportWidth();
  const PANEL_MIN = 380;
  const [keyFailed, setKeyFailed] = useState(false);
  useEffect(() => {
    if (status !== "failed") return;
    listDeadLetters(id).then((ds) => setKeyFailed(ds.some((d) => KEY_ERROR.test(d.error)))).catch(() => {});
  }, [id, status]);
  const panelMax = Math.max(PANEL_MIN, (vw || 1600) - 300 - 380); // leave the sidebar and at least 380px of chat

  if (connection === "not-found") {
    return (
      <div className="mx-auto max-w-3xl px-4 py-24 text-center">
        <p className="text-lg font-medium">Run not found</p>
        <p className="mt-1 text-sm text-muted">It may have been deleted, or the link is wrong.</p>
      </div>
    );
  }

  async function stop() {
    setStopping(true);
    setStopError(null);
    try {
      await cancelWorkflow(id);
    } catch (e) {
      setStopError(e instanceof Error ? e.message : String(e));
    } finally {
      setStopping(false);
    }
  }

  // the report to show: the latest draft once the run is done; while a change is being made, the last one that passed
  const final = status === "completed" ? run?.revisions.at(-1) : run?.revisions.findLast((r) => r.critique?.passed);
  const canEdit = status === "completed" && !!final;
  const panel = choice ?? !!final; // opens beside the chat when the report arrives, until the reader decides
  const setPanel = setChoice;
  const usage = run ? usageLine(run.usage) : null;
  const budgetNote = run?.warnings.find((w) => w.startsWith("token budget reached"));
  const lastActivity = timeline.stages.findLast((s) => s.phase === "working")?.activities.at(-1)?.detail;
  // the conversation; older runs have no turns, only their prompt
  const turns = run ? (run.turns?.length ? run.turns : [{ role: "user" as const, text: run.prompt, created_at: run.created_at }]) : [];
  const researching = !!run && (run.intent === "research" || (!run.intent && !run.turns?.length));
  const chatting = !!run && !researching;
  // the agent steps: the router's latest pass first ("Reading your message"), then the research agents once it chose research
  const lastRouter = timeline.stages.findLast((s) => s.agent === "router");
  const team = { ...timeline, stages: timeline.stages.filter((s) => s.agent !== "router" || s === lastRouter),
    pending: researching ? timeline.pending.filter((a) => a !== "router") : [] };
  const showTeam = researching || !finished;
  // every step while the run works (one stepper hands on to the next); a run that ended before the page opened shows
  // only its last step until expanded
  const ended = finished && !!run && !fresh(run.updated_at, since);
  const showAll = teamOpen ?? !ended;
  const answered = status === "completed" && !!run && fresh(run.updated_at, since);

  return (
    <div className="flex h-full">
    <div ref={scroller} className="flex min-w-0 flex-1 flex-col overflow-y-auto">
      <header className="sticky top-0 z-10 border-b border-line bg-bg/80 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-3">
          <h1 className="min-w-0 flex-1 truncate font-serif text-lg">{run ? (run.brief ?? run.prompt) : "Loading…"}</h1>
          {run && (
            <span className="label text-muted">
              {duration(run.created_at, finished ? run.updated_at : now)}
            </span>
          )}
          {status && <StatusPill status={status} />}
          {status && !finished && (
            <button
              type="button"
              onClick={stop}
              disabled={stopping}
              className="btn-ghost py-1.5 hover:border-bad hover:text-bad disabled:opacity-50"
            >
              ■ {stopping ? "Stopping…" : "Stop"}
            </button>
          )}
        </div>
        {/* one polite live region: announces status changes and the current sub-step */}
        <p role="status" aria-live="polite" className="sr-only">
          {status ? `Run ${status}. ` : ""}{lastActivity ?? ""}
        </p>
        {(CONNECTION[connection] || stopError) && (
          <p className="mx-auto max-w-3xl px-4 pb-2 text-xs text-warn">⚠ {stopError ?? CONNECTION[connection]}</p>
        )}
      </header>

      <div ref={content} className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-4 py-8">
        {turns.map((m, i) =>
          m.role === "user" ? (
            <p key={i} className={`ml-auto max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-surface-2 px-4 py-2.5 text-[1.02rem] leading-relaxed ${fresh(m.created_at, since) ? "arrive" : ""}`}>
              {m.text}
            </p>
          ) : (
            <Reply key={i} arriving={fresh(m.created_at, since)}>{m.text}</Reply>
          ),
        )}
        {showTeam && <section aria-labelledby="activity-h" className="flex gap-3">
          <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full border border-line bg-surface">
            <Mark className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="activity-h">
              <button type="button" onClick={() => setTeamOpen(!showAll)} aria-expanded={showAll} aria-controls="activity-list"
                className="label group mb-1.5 flex items-center gap-2 pt-2 text-[11px] text-muted hover:text-fg">
                Agent team <span className={finished ? "" : "text-ok"}>· {finished ? "finished" : "working"}</span>
                <span>· {team.stages.length} step{team.stages.length === 1 ? "" : "s"}</span>
                <span aria-hidden className={`transition ${showAll ? "rotate-90" : ""}`}>›</span>
                <span className="sr-only">{showAll ? "Hide earlier steps" : "Show all steps"}</span>
              </button>
            </h2>
            <div id="activity-list">
              {run ? <AgentActivity timeline={team} latestOnly={!showAll} since={since} /> : <div className="h-24 animate-pulse rounded-xl bg-surface-2" />}
            </div>

            {usage && <p className="label mt-0.5 pl-8 text-[10px] text-muted">{usage}</p>}

            {run && run.warnings.length > 0 && (
              <details className="group mt-4 text-sm">
                <summary className="label inline-flex cursor-pointer items-center gap-2 rounded-full border border-line px-3 py-1 text-warn hover:border-warn/50">
                  ⚠ {run.warnings.length} warning{run.warnings.length > 1 ? "s" : ""}
                  <span aria-hidden className="text-muted transition group-open:rotate-90">›</span>
                </summary>
                <ul className="mt-2 flex flex-col divide-y divide-line rounded-md border border-line">
                  {run.warnings.map((w, i) => {
                    const p = parseWarning(w);
                    return (
                      <li key={i} className="flex flex-wrap items-baseline gap-x-3 px-3 py-2" title={w}>
                        <span className="label text-warn">{p.what}</span>
                        {p.where && <span className="font-medium">{p.where}</span>}
                        <span className="text-muted">{p.why}</span>
                      </li>
                    );
                  })}
                </ul>
              </details>
            )}

            {status === "failed" && (
              budgetNote ? (
                <p className="mt-4 rounded-md border border-bad/30 bg-bad/5 px-4 py-3 text-sm">
                  ✕ Stopped at the token budget before any report was written. <span className="text-muted">{budgetNote}</span>
                </p>
              ) : keyFailed ? (
                <p role="alert" className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-md border border-bad/30 bg-bad/5 px-4 py-3 text-sm">
                  ✕ No working API key. The agents need an Anthropic or OpenAI API key with credit: add or replace it in
                  Connectors, then replay this run from its dead letter.
                  <Link href="/connectors" className="btn-ghost py-1">Add a key →</Link>
                  <Link href={`/dead-letters?run=${id}`} className="btn-ghost py-1">Replay →</Link>
                </p>
              ) : (
                <p className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-md border border-bad/30 bg-bad/5 px-4 py-3 text-sm">
                  ✕ The run failed after all retries. The failed job is in the dead-letter queue with its error and the
                  model&apos;s last output.
                  <Link href={`/dead-letters?run=${id}`} className="btn-ghost py-1">Open and replay →</Link>
                </p>
              )
            )}
            {status === "completed" && budgetNote && (
              <p className="mt-4 rounded-md border border-warn/30 bg-warn/5 px-4 py-3 text-sm">
                ⚠ Stopped at the token budget. The report below is the last draft and may not have passed review.
              </p>
            )}
            {status === "canceled" && <p className="mt-4 text-sm text-muted">■ Stopped. No further steps will run.</p>}

            {final?.summary && status === "completed" && (
              <p className={`mt-6 max-w-[62ch] text-[1.02rem] leading-relaxed ${answered ? "arrive" : ""}`}>{final.summary}</p>
            )}
            {final && (
              <button type="button" onClick={() => setPanel(!panel)} aria-expanded={!!panel} aria-controls="report-panel"
                style={{ "--delay": "90ms" } as React.CSSProperties}
                className={`group mt-6 flex w-full max-w-md items-center gap-4 rounded-lg border bg-surface p-3 text-left transition hover:border-fg/50 ${panel ? "border-fg/50" : "border-line"} ${answered ? "arrive" : ""}`}>
                <span aria-hidden className="grid size-11 shrink-0 place-items-center rounded-md border border-line bg-bg font-serif text-xl">¶</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-serif text-[1.05rem]">{reportTitle(final.report_md) ?? "Report"}</span>
                  <span className="label text-muted">Report · draft {final.revision + 1} · {panel ? "open" : "click to open"}</span>
                </span>
                <span aria-hidden className="label text-muted transition group-hover:text-fg">{panel ? "Close" : "Open"} →</span>
              </button>
            )}

            {run && run.edits.length > 0 && (
              <ol className="mt-6 flex flex-col gap-3" aria-label="Changes you asked for">
                {run.edits.map((e) => {
                  const applied = run.revisions.some((r) => r.revision >= e.revision && r.critique?.passed) && (status === "completed" || e !== run.edits.at(-1));
                  return (
                    <li key={e.revision} className="ml-auto max-w-[85%] rounded-lg border border-line bg-surface px-5 py-3">
                      <p className="label flex items-center gap-2 text-muted">
                        Change request
                        <span className={applied ? "text-ok" : "text-run"}>· {applied ? "applied" : status === "working" ? "working on it" : status}</span>
                      </p>
                      <p className="mt-1.5 whitespace-pre-wrap font-serif text-lg leading-snug">{e.instruction}</p>
                    </li>
                  );
                })}
              </ol>
            )}
          </div>
        </section>}
      </div>

      <div className="sticky bottom-0 bg-gradient-to-t from-bg via-bg to-transparent pt-6">
        <div className="mx-auto max-w-3xl px-4 pb-4">
          {canEdit ? (
            <Composer placeholder="Ask for a change to this report…" action="Edit"
              onSubmit={async (text) => {
                await editWorkflow(id, text);
                setTeamOpen(null);
                reopen();
              }} />
          ) : chatting && (run?.intent === "chat" || run?.intent === "decline" || !finished) ? (
            <Composer placeholder="Reply…" action="Send" disabled={!finished}
              onSubmit={async (text) => {
                await sendMessage(id, text);
                reopen();
              }} />
          ) : (
            <Composer placeholder="Start another run…" />
          )}
        </div>
      </div>
    </div>

    {final && panel && (
      <aside id="report-panel" aria-label="Report" style={{ "--panel-w": `${Math.min(panelMax, Math.max(PANEL_MIN, panelWidth))}px` } as React.CSSProperties}
        className="fixed inset-0 z-40 border-line lg:relative lg:inset-auto lg:z-auto lg:w-[var(--panel-w)] lg:shrink-0 lg:border-l">
        <ResizeHandle edge="left" width={panelWidth} min={PANEL_MIN} max={panelMax} onResize={setPanelWidth}
          onCollapse={() => setPanel(false)} label="Resize report panel" />
        <ReportArtifact key={`${run!.id}-${run!.revisions.length}`} run={run!} onClose={() => setPanel(false)} />
      </aside>
    )}
    </div>
  );
}

/** A message from Retro: the mark, then the text. */
function Reply({ children, arriving = false }: { children: React.ReactNode; arriving?: boolean }) {
  return (
    <div className={`flex gap-3 ${arriving ? "arrive" : ""}`}>
      <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full border border-line bg-surface">
        <Mark className="size-4" />
      </span>
      <div className="min-w-0 max-w-[62ch] whitespace-pre-wrap pt-1 text-[1.02rem] leading-relaxed">{children}</div>
    </div>
  );
}

/** Keeps the newest step in view while the conversation grows, the way a chat does, but only while the reader is at
 * the bottom: scrolling up to read stops it until they come back down. */
function useFollow() {
  const scroller = useRef<HTMLDivElement>(null), content = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const box = scroller.current, inner = content.current;
    if (!box || !inner) return;
    let pinned = true;
    // only the reader's own gesture unpins; our smooth scroll fires scroll events too, and must not count
    const leave = (e: Event) => {
      if (e instanceof KeyboardEvent && (e.target as HTMLElement).closest("textarea, input")) return; // typing, not scrolling
      if (e instanceof WheelEvent ? e.deltaY < 0 : e instanceof KeyboardEvent ? ["PageUp", "ArrowUp", "Home"].includes(e.key) : true) pinned = false;
    };
    const onScroll = () => { if (box.scrollHeight - box.scrollTop - box.clientHeight < 160) pinned = true; };
    const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const ro = new ResizeObserver(() => { if (pinned) box.scrollTo({ top: box.scrollHeight, behavior: smooth ? "smooth" : "auto" }); });
    const gestures = ["wheel", "touchmove", "keydown"] as const;
    gestures.forEach((g) => box.addEventListener(g, leave, { passive: true }));
    box.addEventListener("scroll", onScroll, { passive: true });
    ro.observe(inner);
    return () => { gestures.forEach((g) => box.removeEventListener(g, leave)); box.removeEventListener("scroll", onScroll); ro.disconnect(); };
  }, []);
  return [scroller, content] as const;
}
