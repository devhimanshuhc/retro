// Pure display helpers for runs. Tested in format.test.ts (node --test).
import type { Finding, Source } from "./types.ts";

/** Same order as the backend's numbered_sources(): deduped by URL; the report cites them as [1], [2], ... */
export function numberedSources(findings: Finding[]): Source[] {
  const seen = new Map<string, Source>();
  for (const f of findings) for (const s of f.sources) if (!seen.has(s.url)) seen.set(s.url, s);
  return [...seen.values()];
}

/** Report markdown for display: drop the code-built "## Sources" list (the page shows source cards instead)
 * and turn each citation [n] into a link to its card. */
export function linkCitations(md: string): string {
  const body = md.replace(/\n## Sources\n[\s\S]*$/, "\n");
  return body.replace(/\[(\d+)\](?![(:])/g, "[$1](#source-$1)");
}

export function domain(url: string): string {
  if (url.startsWith("doc://")) return "your file";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function duration(fromIso: string, toIso: string | number): string {
  const s = Math.max(0, Math.round(((typeof toIso === "number" ? toIso : Date.parse(toIso)) - Date.parse(fromIso)) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

/** The report's own title: its first "# " heading. */
export function reportTitle(md: string): string | null {
  return md.match(/^#\s+(.+)$/m)?.[1].trim() ?? null;
}

/** "230,937 tokens · supervisor 10.2k · research 186.7k · …", in pipeline order; null when nothing was used. */
export function usageLine(usage: Partial<Record<string, { input_tokens: number; output_tokens: number }>>): string | null {
  const parts = ["supervisor", "research", "write", "critic"]
    .filter((k) => usage[k])
    .map((k) => [k, usage[k]!.input_tokens + usage[k]!.output_tokens] as const);
  const total = parts.reduce((n, [, t]) => n + t, 0);
  if (!total) return null;
  return [`${total.toLocaleString("en-US")} tokens`, ...parts.map(([k, t]) => `${k} ${(t / 1000).toFixed(1)}k`)].join(" · ");
}

/** A run warning made short for display: "dropped source <url>: HTTP 403" → { what: "Source dropped", where: "openai.com", why: "HTTP 403" }. */
export function parseWarning(w: string): { what: string; where?: string; why: string } {
  const dropped = w.match(/^dropped source (\S+): (.+)$/);
  if (dropped) return { what: "Source dropped", where: domain(dropped[1]), why: dropped[2] };
  const weak = w.match(/^weak sources: source_quality ([\d.]+)/);
  if (weak) return { what: "Weak sources", why: `source quality ${weak[1]}` };
  return { what: "Note", why: w };
}
