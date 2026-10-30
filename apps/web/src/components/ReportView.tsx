"use client";

import { useState } from "react";
import Markdown from "react-markdown";

import { GoogleDocButton } from "./GoogleDocButton";
import { domain, linkCitations, numberedSources, reportTitle } from "@/lib/format";
import type { Critique, Source, WorkflowRun } from "@/lib/types";

const KIND_LABEL = { paper: "Paper", primary: "Primary", news: "News", other: "Other" } as const;
const SCORE_LABEL: Record<string, string> = {
  factual_accuracy: "Factual", citation_accuracy: "Citations", completeness: "Complete", source_quality: "Sources",
};

/** The final report as a side panel, like an artifact next to the chat: a header with actions, the drafts,
 * the critic's verdict in one compact row, then the report and its sources. */
export function ReportArtifact({ run, onClose }: { run: WorkflowRun; onClose: () => void }) {
  const [sel, setSel] = useState(run.revisions.length - 1);
  const [copied, setCopied] = useState(false);
  const rev = run.revisions[Math.min(sel, run.revisions.length - 1)];
  const sources = numberedSources(run.findings);
  if (!rev) return null;
  const title = reportTitle(rev.report_md) ?? "Report";

  function download() {
    const url = URL.createObjectURL(new Blob([rev.report_md], { type: "text/markdown" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `${title.replace(/[^\w-]+/g, "-").toLowerCase()}.md` });
    a.click();
    URL.revokeObjectURL(url);
  }

  async function copy() {
    await navigator.clipboard.writeText(rev.report_md);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <article aria-labelledby="artifact-h" className="flex h-full flex-col bg-surface">
      <header className="flex items-center gap-2 border-b border-line px-4 py-2">
        <div className="min-w-0 flex-1">
          <h2 id="artifact-h" className="truncate font-serif text-[0.95rem] leading-tight">{title}</h2>
          <p className="mt-0.5 font-mono text-[11px] text-muted">draft {rev.revision + 1} · {sources.length} sources</p>
        </div>
        <GoogleDocButton runId={run.id} />
        <IconButton label={copied ? "Copied" : "Copy markdown"} onClick={copy}>{copied ? "✓" : "⧉"}</IconButton>
        <IconButton label="Download .md" onClick={download}>↓</IconButton>
        <IconButton label="Close report" onClick={onClose}>✕</IconButton>
      </header>

      <div className="flex min-w-0 items-center gap-3 border-b border-line px-4 py-1.5">
        {run.revisions.length > 1 && (
          <div role="tablist" aria-label="Drafts" className="flex shrink-0 items-center gap-0.5">
            {run.revisions.map((r, i) => (
              <button key={r.revision} role="tab" aria-selected={i === sel} onClick={() => setSel(i)}
                className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${i === sel ? "bg-surface-2 text-fg" : "text-muted hover:text-fg"}`}>
                d{r.revision + 1}
                <span aria-hidden className={`ml-0.5 ${r.critique?.passed ? "text-ok" : r.critique ? "text-bad" : ""}`}>{r.critique ? (r.critique.passed ? "✓" : "✕") : "·"}</span>
                <span className="sr-only">Draft {r.revision + 1}, {r.critique ? (r.critique.passed ? "passed" : "rejected") : "not reviewed"}</span>
              </button>
            ))}
          </div>
        )}
        {rev.critique && <Verdict c={rev.critique} />}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-7 sm:px-9">
        {rev.critique && rev.critique.errors.length > 0 && (
          <details className="group mb-6 text-sm">
            <summary className="cursor-pointer font-mono text-[11px] text-muted hover:text-fg">
              {rev.critique.errors.length} reviewer note{rev.critique.errors.length > 1 ? "s" : ""}
            </summary>
            <ul className="mt-2 flex flex-col gap-1.5 border-l border-line pl-3 text-[0.85rem] text-muted">
              {rev.critique.errors.map((e, i) => <li key={i} className="flex gap-2"><span aria-hidden>–</span>{e}</li>)}
            </ul>
          </details>
        )}

        <ReportBody md={rev.report_md} sources={sources} />
      </div>
    </article>
  );
}

/** A small round icon button with its name as the accessible label and the tooltip. */
function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-label={label} title={label}
      className="grid size-7 shrink-0 place-items-center rounded-full text-sm text-muted transition hover:bg-surface-2 hover:text-fg">
      <span aria-hidden>{children}</span>
    </button>
  );
}

/** The critic's verdict on one quiet line: passed or rejected, then each score (amber under 0.7). */
export function Verdict({ c }: { c: Critique }) {
  return (
    // one quiet line: verdict, then each score; a weak score (under 0.7) is the only thing in colour
    <p className="flex min-w-0 items-center gap-2 overflow-hidden whitespace-nowrap font-mono text-[11px] text-muted">
      <span className={c.passed ? "text-ok" : "text-bad"}>{c.passed ? "✓ passed" : "✕ rejected"}</span>
      {c.scores && Object.entries(c.scores).map(([k, v]) => (
        <span key={k} title={k.replace(/_/g, " ")} className="truncate">
          <span aria-hidden className="mr-2 opacity-40">·</span>
          {(SCORE_LABEL[k] ?? k).toLowerCase()} <span className={v < 0.7 ? "text-warn" : "text-fg/80"}>{v.toFixed(2)}</span>
        </span>
      ))}
    </p>
  );
}

/** The report itself, with citations linked to its source cards. Shared by the side panel and the full-page view. */
export function ReportBody({ md, sources }: { md: string; sources: Source[] }) {
  return (
    <>
      <div className="report">
        <Markdown
          components={{
            a: ({ href, children }) =>
              href?.startsWith("#source-") ? (
                <a href={href} aria-label={`source ${String(children)}`}>{children}</a>
              ) : (
                <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
              ),
          }}
        >
          {linkCitations(md)}
        </Markdown>
      </div>

      {sources.length > 0 && (
        <section aria-labelledby="sources-h" className="mt-10 flex flex-col gap-3">
          <h3 id="sources-h" className="font-serif text-xl tracking-tight">Sources <span className="label align-middle text-muted">· quotes copied verbatim</span></h3>
          <ol className="grid border-t border-l border-dashed border-line xl:grid-cols-2">
            {sources.map((s, i) => (
              <li key={s.url} id={`source-${i + 1}`} className="scroll-mt-6 border-r border-b border-dashed border-line p-4 transition target:bg-surface-2">
                <a href={s.url} target="_blank" rel="noopener noreferrer" className="group flex flex-col gap-1">
                  <span className="label flex items-center gap-2 text-muted">
                    <span className="text-fg">{i + 1}</span>
                    <span className="truncate normal-case tracking-normal">{domain(s.url)}</span>
                    <span className="ml-auto">{KIND_LABEL[s.kind]}</span>
                  </span>
                  <span className="line-clamp-2 text-sm font-medium group-hover:underline">{s.title}</span>
                  <q className="line-clamp-3 text-xs leading-relaxed text-muted">{s.quote}</q>
                </a>
              </li>
            ))}
          </ol>
        </section>
      )}
    </>
  );
}
