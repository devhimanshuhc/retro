"use client";

import { useEffect, useState, type ReactNode } from "react";

import { getLlmSettings } from "@/lib/api";

import { ApiKeysCard } from "./ApiKeysCard";

/** Shows a no-key error and the API key form instead of its children until the agents have a model provider key. */
export function KeyGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState<boolean | null>(null);
  useEffect(() => {
    getLlmSettings().then((s) => setReady(s.active !== null)).catch(() => setReady(true)); // API down: the composer shows that error
  }, []);
  if (ready !== false) return children;
  return (
    <div className="flex flex-col gap-4">
      <p role="alert" className="rounded-md border border-bad/30 bg-bad/5 px-4 py-3 text-sm">
        ✕ No model connected. The agents need an Anthropic or OpenAI API key before they can run. Get one from the{" "}
        <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer" className="underline underline-offset-2">Anthropic Console</a>{" "}
        or{" "}
        <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer" className="underline underline-offset-2">OpenAI platform</a>
        , then paste it below.
      </p>
      <ApiKeysCard onChange={(s) => setReady(s.active !== null)} />
    </div>
  );
}
