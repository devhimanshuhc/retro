"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { disconnectGoogle, listConnectors, saveGoogleClient } from "@/lib/api";
import { connectGoogle } from "@/lib/connectGoogle";
import type { Connector } from "@/lib/types";

import { ApiKeysCard } from "./ApiKeysCard";
import { GoogleDriveIcon } from "./GoogleDriveIcon";

/** The services Retro can send reports to, each with connect and disconnect. */
export function ConnectorsPage() {
  const [items, setItems] = useState<Connector[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    listConnectors()
      .then((d) => {
        setItems(d);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);
  useEffect(load, [load]);
  const params = useSearchParams();
  const signIn = params.get("google_error"); // set by the API when Google sign-in didn't work

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-5 py-12">
      <header className="flex flex-col gap-2">
        <h1 className="font-serif text-[clamp(2rem,3.6vw,2.8rem)] leading-tight tracking-[-0.02em]">Connectors</h1>
        <p className="max-w-xl text-muted">Your API key for the agents, and the accounts reports can be sent to.</p>
      </header>
      <ApiKeysCard />
      {params.get("google") === "connected" && <p role="status" className="text-sm text-ok">● Google account connected. Reports can now open as Google Docs.</p>}
      {signIn && <p role="alert" className="text-sm text-bad">✕ {signIn}</p>}
      {error ? (
        <p role="alert" className="text-bad">✕ Couldn&apos;t load connectors: {error}</p>
      ) : items === null ? (
        <div className="h-28 animate-pulse rounded-lg bg-surface-2" />
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((c) => <ConnectorRow key={c.id} c={c} onChange={load} setupOpen={params.get("setup") === c.id} />)}
        </ul>
      )}
    </div>
  );
}

function ConnectorRow({ c, onChange, setupOpen }: { c: Connector; onChange: () => void; setupOpen: boolean }) {
  const [setup, setSetup] = useState(setupOpen && !c.configured);
  const [busy, setBusy] = useState<"connect" | "disconnect" | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function run(kind: "connect" | "disconnect") {
    if (kind === "disconnect" && !confirm(`Disconnect ${c.account ?? c.name}? Retro's access is revoked at Google; docs already created stay in your Drive.`)) return;
    setBusy(kind);
    setErr(null);
    try {
      if (kind === "connect") await connectGoogle();
      else await disconnectGoogle();
      onChange();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <li className="flex flex-wrap items-center gap-4 rounded-lg border border-line bg-surface p-5">
      <span aria-hidden className="grid size-11 shrink-0 place-items-center rounded-md border border-line bg-bg"><GoogleDriveIcon className="size-6" /></span>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{c.name}</span>
          <span className={`font-mono text-[11px] ${c.connected ? "text-ok" : "text-muted"}`}>
            {!c.configured ? "○ not set up yet" : c.connected ? `● connected${c.account ? ` as ${c.account}` : ""}` : "○ not connected"}
          </span>
        </p>
        <p className="mt-1 text-sm text-muted">{c.description}</p>
        {err && <p role="alert" className="mt-1 text-sm text-bad">✕ {err}</p>}
      </div>
      {!c.configured && !setup && (
        <button type="button" onClick={() => setSetup(true)} className="btn-primary py-1.5">Set up</button>
      )}
      {c.configured && (c.connected ? (
        <button type="button" onClick={() => run("disconnect")} disabled={busy !== null}
          className="btn-ghost py-1.5 hover:border-bad hover:text-bad disabled:opacity-50">
          {busy === "disconnect" ? "Disconnecting…" : "Disconnect"}
        </button>
      ) : (
        <button type="button" onClick={() => run("connect")} disabled={busy !== null} className="btn-primary py-1.5 disabled:opacity-50">
          {busy === "connect" ? "Connecting…" : "Connect"}
        </button>
      ))}
      {c.configured && !c.connected && !setup && (
        <button type="button" onClick={() => setSetup(true)} className="basis-full text-left text-xs text-muted underline-offset-2 hover:text-fg hover:underline">
          Use a different Google app
        </button>
      )}
      {setup && c.redirect_uri && (
        <GoogleSetup redirectUri={c.redirect_uri} onCancel={() => setSetup(false)} onSaved={() => { setSetup(false); onChange(); }} />
      )}
    </li>
  );
}

const STEPS: [string, string, string][] = [
  ["Create a Google Cloud project", "https://console.cloud.google.com/projectcreate", "Any name, e.g. Retro. It's free."],
  ["Turn on the Google Drive API", "https://console.cloud.google.com/apis/library/drive.googleapis.com", "Make sure your new project is selected at the top, then click Enable."],
  ["Set up the sign-in screen", "https://console.cloud.google.com/auth/overview", "Get started → app name Retro, your email → audience External → Create. Then open Audience and click Publish app: in Testing mode Google signs Retro out every 7 days. No review is needed, because Retro only asks to see the files it creates."],
  ["Create the OAuth client", "https://console.cloud.google.com/auth/clients", "Create client → type Web application → under Authorized redirect URIs add the address below → Create."],
];

/** Walks the user through registering their own Google app (OAuth client), then saves its ID and secret. */
function GoogleSetup({ redirectUri, onCancel, onSaved }: { redirectUri: string; onCancel: () => void; onSaved: () => void }) {
  const [id, setId] = useState("");
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await saveGoogleClient(id, secret);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Set up Google Docs" className="basis-full border-t border-line pt-4">
      <p className="text-sm">
        Google needs a one-time setup so Retro can create docs in your Drive. It takes about 5 minutes, and you only do it once.
      </p>
      <ol className="mt-3 flex flex-col gap-3">
        {STEPS.map(([title, href, how], i) => (
          <li key={title} className="flex gap-3 text-sm">
            <span className="grid size-6 shrink-0 place-items-center rounded-full border border-line font-mono text-xs">{i + 1}</span>
            <span>
              <a href={href} target="_blank" rel="noopener noreferrer" className="font-medium underline underline-offset-2">{title} ↗</a>
              <span className="block text-muted">{how}</span>
              {i === 3 && (
                <span className="mt-1.5 flex items-center gap-2">
                  <code className="min-w-0 truncate rounded border border-line bg-bg px-2 py-1 font-mono text-xs">{redirectUri}</code>
                  <button type="button" className="btn-ghost shrink-0 py-1 text-xs"
                    onClick={() => navigator.clipboard?.writeText(redirectUri).then(() => setCopied(true))}>
                    {copied ? "Copied" : "Copy"}
                  </button>
                </span>
              )}
            </span>
          </li>
        ))}
        <li className="flex gap-3 text-sm">
          <span className="grid size-6 shrink-0 place-items-center rounded-full border border-line font-mono text-xs">5</span>
          <form onSubmit={save} className="flex min-w-0 flex-1 flex-col gap-2">
            <span className="font-medium">Paste the client ID and secret Google shows you</span>
            <label className="sr-only" htmlFor="g-id">Client ID</label>
            <input id="g-id" value={id} onChange={(e) => setId(e.target.value)} placeholder="Client ID (…apps.googleusercontent.com)" autoComplete="off" spellCheck={false}
              className="rounded-lg border border-line bg-bg px-3 py-1.5 font-mono text-sm outline-none focus:border-fg/60" />
            <label className="sr-only" htmlFor="g-secret">Client secret</label>
            <input id="g-secret" type="password" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="Client secret (GOCSPX-…)" autoComplete="off" spellCheck={false}
              className="rounded-lg border border-line bg-bg px-3 py-1.5 font-mono text-sm outline-none focus:border-fg/60" />
            {err && <p role="alert" className="text-bad">✕ {err}</p>}
            <span className="flex gap-2">
              <button type="submit" disabled={busy || !id.trim() || !secret.trim()} className="btn-primary py-1.5 disabled:opacity-50">{busy ? "Saving…" : "Save"}</button>
              <button type="button" onClick={onCancel} className="btn-ghost py-1.5">Cancel</button>
            </span>
            <span className="text-xs text-muted">Kept on this computer only. Then click Connect and pick your Google account.</span>
          </form>
        </li>
      </ol>
    </section>
  );
}
