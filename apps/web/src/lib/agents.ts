// Display names and roles of the agents; plain data, usable from server and client components.
import type { StepName } from "./types";

export const AGENT: Record<StepName, { name: string; glyph: string; role: string }> = {
  router: { name: "Router", glyph: "↳", role: "Reads each message and decides: chat, decline, or research" },
  supervisor: { name: "Planner", glyph: "◇", role: "Splits the request into research questions and an outline" },
  research: { name: "Researcher", glyph: "⌕", role: "Searches the web, reads pages, keeps verbatim evidence" },
  write: { name: "Writer", glyph: "✎", role: "Writes a cited report from the evidence only" },
  critic: { name: "Critic", glyph: "✓", role: "Checks numbers and citations, scores the draft" },
};

export function stageTitle(agent: StepName, revision: number): string {
  switch (agent) {
    case "router":
      return "Reading your message";
    case "supervisor":
      return "Planning";
    case "research":
      return "Researching";
    case "write":
      return `Writing draft ${revision + 1}`;
    case "critic":
      return `Reviewing draft ${revision + 1}`;
  }
}
