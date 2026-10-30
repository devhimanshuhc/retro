"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { getWorkflow } from "@/lib/api";
import { numberedSources, reportTitle } from "@/lib/format";
import type { WorkflowRun } from "@/lib/types";

import { GoogleDocButton } from "./GoogleDocButton";
import { Wordmark } from "./Mark";
import { ReportBody, Verdict } from "./ReportView";

/** The report as a standalone document page: a slim bar, then the report set like an article. */
export function ArtifactPage({ id }: { id: string }) {
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    getWorkflow(id).then(setRun).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [id]);

  const rev = run?.revisions.findLast((r) => r.critique?.passed) ?? run?.revisions.at(-1);
  const title = rev ? reportTitle(rev.report_md) ?? "Report" : "Report";

  useEffect(() => {
    if (rev) document.title = `${title} · Retro`;
  }, [rev, title]);

  if (error) return <p role="alert" className="mx-auto mt-24 max-w-3xl px-5 text-bad">✕ Couldn&apos;t load this report: {error}</p>;
  if (!run || !rev) {
    return run ? <p className="mx-auto mt-24 max-w-3xl px-5 text-muted">This run has no report yet.</p>
      : <div className="mx-auto mt-24 h-64 max-w-3xl animate-pulse rounded-lg bg-surface-2" />;
  }

  function download() {
    const url = URL.createObjectURL(new Blob([rev!.report_md], { type: "text/markdown" }));
    Object.assign(document.createElement("a"), { href: url, download: `${title.replace(/[^\w-]+/g, "-").toLowerCase()}.md` }).click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="min-h-dvh bg-bg">
      <header className="sticky top-0 z-10 border-b border-line bg-bg/90 backdrop-blur-sm">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-5 py-3">
          <Link href="/" aria-label="Retro home"><Wordmark /></Link>
          <span className="label hidden min-w-0 flex-1 truncate text-muted sm:block">Report · draft {rev.revision + 1}</span>
          <div className="ml-auto flex gap-2">
            <button type="button" className="btn-ghost py-1.5" onClick={async () => {
              await navigator.clipboard.writeText(rev.report_md);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}>{copied ? "Copied ✓" : "Copy"}</button>
            <button type="button" className="btn-ghost py-1.5" onClick={download}>Download .md</button>
            <GoogleDocButton runId={run.id} variant="button" />
            <Link href={`/runs/${run.id}`} className="btn-primary py-1.5">Open chat</Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-5 py-14 sm:py-20">
        <p className="label text-muted">{run.prompt}</p>
        {rev.critique && <div className="mt-4"><Verdict c={rev.critique} /></div>}
        <article className="artifact mt-10">
          <ReportBody md={rev.report_md} sources={numberedSources(run.findings)} />
        </article>
        <footer className="label mt-16 border-t border-line pt-6 text-muted">
          Researched, written and reviewed by Retro · {new Date(run.updated_at).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" })}
        </footer>
      </main>
    </div>
  );
}
