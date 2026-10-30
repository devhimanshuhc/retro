"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { ApiError, createWorkflow } from "@/lib/api";

const MAX = 4000;

/** Prompt box: Enter sends, Shift+Enter adds a line. By default starts a run and opens it; with `onSubmit` it hands
 * the text over instead (e.g. a change request for the open report). */
export function Composer({ suggestions = [], autoFocus = false, placeholder = "Ask the agents to research and write a report…", onSubmit, action = "Run" }: {
  suggestions?: string[];
  autoFocus?: boolean;
  placeholder?: string;
  onSubmit?: (text: string) => Promise<void>;
  action?: string;
}) {
  const router = useRouter();
  const ref = useRef<HTMLTextAreaElement>(null);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsKey, setNeedsKey] = useState(false);

  async function submit() {
    const text = prompt.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    setNeedsKey(false);
    try {
      if (onSubmit) {
        await onSubmit(text);
        setPrompt("");
      } else {
        const { workflow_run_id } = await createWorkflow(text);
        setPrompt("");
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
          disabled={busy || !prompt.trim()}
          className="btn-primary shrink-0 disabled:opacity-30"
        >
          {busy ? <>Sending <span aria-hidden className="pulse">●</span></> : <>{action} <span aria-hidden className="arrow">→</span></>}
        </button>
      </form>
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
