"use client";

import { useState } from "react";

import { exportGoogleDoc, getGoogleStatus } from "@/lib/api";
import { connectGoogle } from "@/lib/connectGoogle";

import { GoogleDriveIcon } from "./GoogleDriveIcon";

type State = { kind: "idle" | "working" } | { kind: "done"; url: string } | { kind: "error"; message: string };

/** Opens the report as a Google Doc in the user's Drive. The first time, Nango's Connect UI asks them to sign in
 * to Google (Retro only gets the narrow drive.file scope); after that it's one click. */
export function GoogleDocButton({ runId, variant = "icon" }: { runId: string; variant?: "icon" | "button" }) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const fail = (e: unknown) => setState({ kind: "error", message: e instanceof Error ? e.message : String(e) });

  async function open() {
    setState({ kind: "working" });
    try {
      const status = await getGoogleStatus();
      if (!status.configured) return fail(new Error("Google Docs isn't set up on the server yet"));
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
      if (!(await connectGoogle())) return setState({ kind: "idle" }); // closed without connecting
      const doc = await exportGoogleDoc(runId);
      setState({ kind: "done", url: doc.url });
      window.open(doc.url, "_blank");
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
