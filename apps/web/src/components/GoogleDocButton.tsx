"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { exportGoogleDoc, getGoogleStatus } from "@/lib/api";
import { connectGoogle } from "@/lib/connectGoogle";

import { GoogleDriveIcon } from "./GoogleDriveIcon";

type State = { kind: "idle" | "working" } | { kind: "done"; url: string } | { kind: "error"; message: string };

const PENDING = "retro.googleExport"; // the run to export once Google sign-in returns to this page

/** Opens the report as a Google Doc in the user's Drive. Not set up yet: goes to the setup guide in Connectors. Not
 * connected: signs in to Google (Retro only gets the narrow drive.file scope), comes back here and exports. */
export function GoogleDocButton({ runId, variant = "icon" }: { runId: string; variant?: "icon" | "button" }) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const router = useRouter();
  const fail = (e: unknown) => setState({ kind: "error", message: e instanceof Error ? e.message : String(e) });

  useEffect(() => {
    // back from Google sign-in, started by this button for this run: finish the export it was asked for
    let pending: string | null = null;
    try {
      pending = sessionStorage.getItem(PENDING);
      if (pending === runId) sessionStorage.removeItem(PENDING);
    } catch {}
    if (pending !== runId || !new URLSearchParams(window.location.search).has("google")) return;
    exportGoogleDoc(runId)
      .then((doc) => setState({ kind: "done", url: doc.url }))
      .catch((e) => setState({ kind: "error", message: e instanceof Error ? e.message : String(e) }));
  }, [runId]);

  async function open() {
    setState({ kind: "working" });
    try {
      const status = await getGoogleStatus();
      if (!status.configured) return router.push("/connectors?setup=google"); // the guide walks through it
      if (status.connected) {
        const tab = window.open("", "_blank"); // opened during the click, so popup blockers allow it
        try {
          const doc = await exportGoogleDoc(runId);
          if (tab) tab.location.href = doc.url;
          setState({ kind: "done", url: doc.url });
        } catch (e) {
          tab?.close();
          throw e;
        }
        return;
      }
      try {
        sessionStorage.setItem(PENDING, runId);
      } catch {} // without storage the user just clicks again after signing in
      await connectGoogle(window.location.pathname);
    } catch (e) {
      fail(e);
    }
  }

  const label = state.kind === "working" ? "Opening in Google Docs…" : "Open in Google Docs";
  return (
    <span className="relative inline-flex items-center gap-2">
      {variant === "icon" ? (
        <button type="button" onClick={open} disabled={state.kind === "working"} aria-label={label} title={label}
          className="grid size-7 shrink-0 place-items-center rounded-full transition hover:bg-surface-2 disabled:opacity-50">
          <GoogleDriveIcon className={`size-[15px] ${state.kind === "working" ? "pulse" : ""}`} />
        </button>
      ) : (
        <button type="button" onClick={open} disabled={state.kind === "working"} className="btn-ghost py-1.5 disabled:opacity-50">
          <GoogleDriveIcon className="size-3.5" /> {label}
        </button>
      )}
      {state.kind === "done" && (
        <a href={state.url} target="_blank" rel="noopener noreferrer" className="font-mono text-[11px] text-ok hover:underline">doc ↗</a>
      )}
      {state.kind === "error" && (
        <span role="alert" title={state.message} className="max-w-48 truncate font-mono text-[11px] text-bad">✕ {state.message}</span>
      )}
    </span>
  );
}
