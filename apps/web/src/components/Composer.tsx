"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { ApiError, createWorkflow, deleteDocument, uploadDocument } from "@/lib/api";

const MAX = 4000;
const ACCEPT = ".pdf,.txt,.md,.markdown,.html,.htm,.csv,.json";

/** Prompt box: Enter sends, Shift+Enter adds a line. By default starts a run and opens it; with `onSubmit` it hands
 * the text over instead (e.g. a change request for the open report). */
export function Composer({ suggestions = [], autoFocus = false, placeholder = "Ask the agents to research and write a report…", onSubmit, action = "Run", disabled = false }: {
  suggestions?: string[];
  autoFocus?: boolean;
  placeholder?: string;
  onSubmit?: (text: string) => Promise<void>;
  action?: string;
  disabled?: boolean;
}) {
  const router = useRouter();
  const ref = useRef<HTMLTextAreaElement>(null);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsKey, setNeedsKey] = useState(false);
  const [files, setFiles] = useState<{ id: string; name: string }[]>([]);
  const [uploading, setUploading] = useState(0);
  const [web, setWeb] = useState(true);
  const attach = !onSubmit; // files go with a new run; a change request reuses the run's sources

  async function add(list: FileList) {
    setError(null);
    for (const f of Array.from(list)) {
      setUploading((n) => n + 1);
      try {
        const d = await uploadDocument(f);
        setFiles((fs) => [...fs, { id: d.id, name: d.name }]);
      } catch (err) {
        setError(`${f.name}: ${err instanceof Error ? err.message : String(err)}`);
      } finally {
        setUploading((n) => n - 1);
      }
    }
  }

  function drop(id: string) {
    setFiles((fs) => fs.filter((f) => f.id !== id));
    deleteDocument(id).catch(() => {}); // not used by any run yet; a leftover file is harmless
  }

  async function submit() {
    const text = prompt.trim();
    if (!text || busy || uploading || disabled) return;
    setBusy(true);
    setError(null);
    setNeedsKey(false);
    try {
      if (onSubmit) {
        await onSubmit(text);
        setPrompt("");
      } else {
        const { workflow_run_id } = await createWorkflow(text, files.map((f) => f.id), web || files.length === 0);
        setPrompt("");
        setFiles([]);
        router.push(`/runs/${encodeURIComponent(workflow_run_id)}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setNeedsKey(err instanceof ApiError && err.status === 409 && /API key/.test(err.message)); // no model key yet
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="flex items-end gap-2 rounded-xl border border-line bg-surface p-2 transition focus-within:border-fg/60"
      >
        {attach && (
          <label title="Attach files: PDF, text, Markdown, HTML, CSV or JSON"
            className="grid size-11 shrink-0 cursor-pointer place-items-center rounded-lg text-muted transition hover:bg-surface-2 hover:text-fg focus-within:ring-2 focus-within:ring-fg/40">
            <span className="sr-only">Attach files</span>
            <svg aria-hidden viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="m21 11.5-8.6 8.6a5.5 5.5 0 0 1-7.8-7.8l8.6-8.6a3.7 3.7 0 0 1 5.2 5.2l-8.6 8.6a1.8 1.8 0 0 1-2.6-2.6l7.9-7.9" />
            </svg>
            <input type="file" multiple accept={ACCEPT} className="sr-only"
              onChange={(e) => {
                if (e.target.files?.length) add(e.target.files);
                e.target.value = "";
              }} />
          </label>
        )}
        <label htmlFor="prompt" className="sr-only">Request for the agents</label>
        <textarea
          id="prompt"
          ref={ref}
          value={prompt}
          autoFocus={autoFocus}
          onChange={(e) => {
            setPrompt(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height = `${Math.min(e.target.scrollHeight, 220)}px`;
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          maxLength={MAX}
          rows={1}
          placeholder={placeholder}
          className="max-h-[220px] min-h-[44px] flex-1 resize-none bg-transparent px-2 py-2.5 text-[0.95rem] outline-none placeholder:text-muted focus-visible:outline-none"
        />
        <button
          type="submit"
          disabled={busy || disabled || uploading > 0 || !prompt.trim()}
          className="btn-primary shrink-0 disabled:opacity-30"
        >
          {busy ? <>Sending <span aria-hidden className="pulse">●</span></> : <>{action} <span aria-hidden className="arrow">→</span></>}
        </button>
      </form>
      {attach && (files.length > 0 || uploading > 0) && (
        <div className="flex flex-wrap items-center gap-1.5 px-1">
          <ul className="flex flex-wrap gap-1.5" aria-label="Attached files">
            {files.map((f) => (
              <li key={f.id} className="inline-flex max-w-64 items-center gap-1 rounded-md border border-line bg-surface py-0.5 pr-1 pl-2 text-xs">
                <span className="truncate">{f.name}</span>
                <button type="button" onClick={() => drop(f.id)} aria-label={`Remove ${f.name}`}
                  className="rounded px-1 text-muted hover:bg-surface-2 hover:text-fg">×</button>
              </li>
            ))}
            {uploading > 0 && <li role="status" className="px-1 text-xs text-muted">Reading {uploading} file{uploading > 1 ? "s" : ""} <span aria-hidden className="pulse">●</span></li>}
          </ul>
          {files.length > 0 && (
            <label className="ml-auto inline-flex cursor-pointer items-center gap-1.5 text-xs text-muted">
              <input type="checkbox" checked={web} onChange={(e) => setWeb(e.target.checked)} className="accent-current" />
              Also search the web
            </label>
          )}
        </div>
      )}
      <div className="flex min-h-4 items-center justify-between px-1 font-mono text-[11px] text-muted/70">
        {error ? (
          <p role="alert" className="text-bad">
            ✕ {error}
            {needsKey && <> · <Link href="/connectors" className="underline underline-offset-2">Add a key →</Link></>}
          </p>
        ) : (
          <p>enter to send · shift+enter for a new line</p>
        )}
        {prompt.length > MAX * 0.8 && <span>{prompt.length}/{MAX}</span>}
      </div>
      {suggestions.length > 0 && (
        <ul className="flex flex-wrap justify-center gap-1.5" aria-label="Example requests">
          {suggestions.map((s) => (
            <li key={s}>
              <button
                type="button"
                onClick={() => {
                  setPrompt(s);
                  ref.current?.focus();
                }}
                className="rounded-full border border-line px-3 py-1 text-xs text-muted transition hover:border-fg/40 hover:text-fg"
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
