"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { listArtifacts } from "@/lib/api";
import type { ArtifactSummary } from "@/lib/types";

/** Every finished report, newest change first, each with its chat and a full-page view. */
export function ArtifactList() {
  const [items, setItems] = useState<ArtifactSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listArtifacts().then(setItems).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-8 px-5 py-12">
      <header className="flex flex-col gap-3">
        <h1 className="font-serif text-[clamp(2.2rem,4vw,3.2rem)] leading-tight tracking-[-0.02em]">Artifacts</h1>
        <p className="max-w-2xl leading-relaxed">Every finished report. Open the chat to ask for changes, or open the report on its own page.</p>
      </header>

      {error ? (
        <p role="alert" className="text-bad">✕ Couldn&apos;t load artifacts: {error}</p>
      ) : items === null ? (
        <div className="h-40 animate-pulse rounded-lg bg-surface-2" />
      ) : items.length === 0 ? (
        <div className="dot-grid flex flex-col items-center gap-3 rounded-lg border border-dashed border-line px-6 py-16 text-center">
          <p className="font-serif text-2xl">No reports yet</p>
          <Link href="/app" className="btn-primary">Start a run <span aria-hidden className="arrow">→</span></Link>
        </div>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {items.map((a) => (
            <li key={a.run_id} className="flex flex-col gap-4 rounded-lg border border-line bg-surface p-5 transition hover:border-fg/40">
              <div className="flex items-start gap-3">
                <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-md border border-line bg-bg font-serif text-lg">¶</span>
                <div className="min-w-0">
                  <h2 className="line-clamp-2 font-serif text-xl leading-snug">{a.title}</h2>
                  <p className="mt-1 line-clamp-2 text-sm text-muted">{a.prompt}</p>
                </div>
              </div>
              <p className="label text-muted">
                Draft {a.revision + 1} · {a.sources} sources{a.edits ? ` · ${a.edits} change${a.edits > 1 ? "s" : ""}` : ""} ·{" "}
                {new Date(a.updated_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })}
              </p>
              <div className="mt-auto flex flex-wrap gap-2">
                <Link href={`/runs/${a.run_id}`} className="btn-ghost">Open chat</Link>
                <a href={`/artifacts/${a.run_id}`} target="_blank" rel="noopener" className="btn-primary">
                  Open artifact <span aria-hidden className="arrow">↗</span>
                </a>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
