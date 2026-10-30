"use client";

import { useEffect, useState } from "react";

import { chooseProvider, getLlmSettings, removeApiKey, saveApiKey } from "@/lib/api";
import type { LlmSettings, Provider } from "@/lib/types";

const SOURCE = { app: "key saved", env: "key from the server's .env", login: "this computer's Claude login (development)" };
const HELP: Record<Provider, { url: string; host: string; placeholder: string }> = {
  anthropic: { url: "https://console.anthropic.com/settings/keys", host: "console.anthropic.com", placeholder: "sk-ant-api03-…" },
  openai: { url: "https://platform.openai.com/api-keys", host: "platform.openai.com", placeholder: "sk-proj-…" },
};

/** Where the user gives Retro an Anthropic or OpenAI API key; the agents run on whichever is in use. Each key is
 * checked by its provider before it's saved, and the page never sees it again. API keys only: apps built on
 * Anthropic's agent SDK may not offer claude.ai subscription login. */
export function ApiKeysCard({ onChange }: { onChange?: (s: LlmSettings) => void }) {
  const [settings, setSettings] = useState<LlmSettings | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getLlmSettings().then(setSettings).catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  const update = (s: LlmSettings) => {
    setSettings(s);
    onChange?.(s);
  };

  return (
    <section aria-labelledby="keys-h" className="rounded-lg border border-line bg-surface p-5">
      <h2 id="keys-h" className="font-medium">Model provider</h2>
      <p className="mt-1 text-sm text-muted">
        The agents run on your own API key from Anthropic or OpenAI, billed by them per token (about 60–120k tokens a
        report). Keys stay on this machine.
      </p>
      {err && <p role="alert" className="mt-2 text-sm text-bad">✕ {err}</p>}
      {settings === null && !err && <div className="mt-4 h-20 animate-pulse rounded-md bg-surface-2" />}
      {settings && (
        <ul className="mt-4 flex flex-col divide-y divide-line border-t border-line">
          {settings.providers.map((p) => (
            <KeyRow key={p.id} p={p} active={settings.active === p.id} onChange={update} />
          ))}
        </ul>
      )}
    </section>
  );
}

function KeyRow({ p, active, onChange }: { p: LlmSettings["providers"][number]; active: boolean; onChange: (s: LlmSettings) => void }) {
  const [editing, setEditing] = useState(false);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function act(fn: () => Promise<LlmSettings>) {
    setBusy(true);
    setErr(null);
    try {
      onChange(await fn());
      setKey("");
      setEditing(false);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const help = HELP[p.id];
  return (
    <li className="py-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <span className="font-medium">{p.name}</span>
          <span className={`font-mono text-[11px] ${p.source ? "text-ok" : "text-muted"}`}>
            {p.source ? `● ${SOURCE[p.source]}` : "○ no key"}
          </span>
          {active && <span className="rounded-full border border-ok/40 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-ok">in use</span>}
        </p>
        {!editing && (
          <span className="flex gap-2">
            {p.source && !active && (
              <button type="button" disabled={busy} onClick={() => act(() => chooseProvider(p.id))} className="btn-ghost py-1.5 disabled:opacity-50">Use {p.name}</button>
            )}
            <button type="button" onClick={() => setEditing(true)} className={`${p.source ? "btn-ghost" : "btn-primary"} py-1.5`}>
              {p.source === "app" ? "Replace" : "Add key"}
            </button>
            {p.source === "app" && (
              <button type="button" disabled={busy} onClick={() => confirm(`Remove the saved ${p.name} key?`) && act(() => removeApiKey(p.id))}
                className="btn-ghost py-1.5 hover:border-bad hover:text-bad disabled:opacity-50">Remove</button>
            )}
          </span>
        )}
      </div>
      {editing && (
        <form className="mt-3 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); if (key.trim()) act(() => saveApiKey(p.id, key.trim())); }}>
          <label htmlFor={`key-${p.id}`} className="sr-only">{p.name} API key</label>
          <input id={`key-${p.id}`} type="password" autoComplete="off" spellCheck={false} autoFocus placeholder={help.placeholder}
            value={key} onChange={(e) => setKey(e.target.value)}
            className="min-w-0 flex-1 rounded-lg border border-line bg-bg px-3 py-1.5 font-mono text-sm outline-none focus:border-fg/60" />
          <button type="submit" disabled={busy || !key.trim()} className="btn-primary py-1.5 disabled:opacity-50">{busy ? "Checking…" : "Save key"}</button>
          <button type="button" onClick={() => { setEditing(false); setKey(""); setErr(null); }} className="btn-ghost py-1.5">Cancel</button>
          <p className="basis-full text-xs text-muted">
            Create one at <a href={help.url} target="_blank" rel="noopener noreferrer" className="underline hover:text-fg">{help.host}</a>.
            Retro checks it with {p.name} before saving (no tokens spent) and switches the agents to it.
          </p>
        </form>
      )}
      {err && <p role="alert" className="mt-2 text-sm text-bad">✕ {err}</p>}
    </li>
  );
}
