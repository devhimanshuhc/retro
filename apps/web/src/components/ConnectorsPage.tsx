"use client";

import { useCallback, useEffect, useState } from "react";

import { disconnectGoogle, listConnectors } from "@/lib/api";
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

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-5 py-12">
      <header className="flex flex-col gap-2">
        <h1 className="font-serif text-[clamp(2rem,3.6vw,2.8rem)] leading-tight tracking-[-0.02em]">Connectors</h1>
        <p className="max-w-xl text-muted">Your API key for the agents, and the accounts reports can be sent to.</p>
      </header>
      <ApiKeysCard />
      {error ? (
        <p role="alert" className="text-bad">✕ Couldn&apos;t load connectors: {error}</p>
      ) : items === null ? (
        <div className="h-28 animate-pulse rounded-lg bg-surface-2" />
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((c) => <ConnectorRow key={c.id} c={c} onChange={load} />)}
        </ul>
      )}
    </div>
  );
}

function ConnectorRow({ c, onChange }: { c: Connector; onChange: () => void }) {
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
            {!c.configured ? "· not set up on the server" : c.connected ? `● connected${c.account ? ` as ${c.account}` : ""}` : "○ not connected"}
          </span>
        </p>
        <p className="mt-1 text-sm text-muted">{c.description}</p>
        {err && <p role="alert" className="mt-1 text-sm text-bad">✕ {err}</p>}
      </div>
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
    </li>
  );
}
