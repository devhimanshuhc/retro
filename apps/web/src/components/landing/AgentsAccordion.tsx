"use client";

import Image from "next/image";
import { useState } from "react";

type Agent = { name: string; does: string; facts: string[]; feed: string[]; photo: { src: string; alt: string; pos: string } };

// What each agent really does, and sub-steps it really reports (the same lines the run page shows).
const AGENTS: Agent[] = [
  {
    name: "Planner",
    does: "Turns your request into 2–4 research questions and the report's outline, validated against a schema before anyone else sees it.",
    facts: ["Structured plan, schema-checked", "A bad plan retries, it never ships", "Every question tied to the outline"],
    feed: ["Breaking the request into research questions", "Plan ready: 3 questions, 5 sections"],
    photo: { src: "/img/switchboard-1942.jpg", alt: "Telephone operators at a switchboard in 1942, routing each call to the right line", pos: "50% 50%" },
  },
  {
    name: "Researcher",
    does: "Searches the web, reads the pages itself and keeps passages copied word for word, so every quote in the report exists on a real page.",
    facts: ["Papers and primary sources first", "Quotes copied by code, never written by the model", "Only the most relevant passages are kept"],
    feed: ["WebSearch: solid-state battery commercialization timelines", "Picked 12 candidate pages (2 paper, 1 primary, 9 news)", "Read 11 of 12 pages, 1 unreachable", "Kept the 18 most relevant passages"],
    photo: { src: "/img/reading-room.jpg", alt: "The main reading room of the Library of Congress seen from above, readers at circular desks", pos: "50% 45%" },
  },
  {
    name: "Writer",
    does: "Writes the report from the findings only, citing each claim as [n]. On a rewrite it gets its last draft and every point the critic raised.",
    facts: ["Every number needs a citation", "No outside facts", "Rewrites from the reviewer's notes"],
    feed: ["Writing draft 2 from 3 findings, fixing 1 reviewer point", "Draft 2 ready: ~610 words, 7 sources cited"],
    photo: { src: "/img/typists-1938.jpg", alt: "Typists at work at long rows of desks in an office in 1938", pos: "50% 30%" },
  },
  {
    name: "Critic",
    does: "Checks sections, citations and every number against the sources in code first, then scores the draft. A failed draft goes back to the writer.",
    facts: ["Code checks before any model call", "Rejects numbers not in the sources", "Thinking off: about 30× fewer output tokens"],
    feed: ["Code checks: sections, citations, every number", "factual 1.00 · citation 1.00 · completeness 0.95", "Passed review"],
    photo: { src: "/img/inspecting-1915.jpg", alt: "Women inspecting machine parts laid out in rows on long tables, 1915", pos: "50% 75%" },
  },
];

/** The agents as an accordion that animates open and shut; the picture shows the open agent's live feed as the
 * run page shows it. Clicking the open item closes it (the card keeps showing the last one opened). */
export function AgentsAccordion() {
  const [open, setOpen] = useState(1);
  const [shown, setShown] = useState(1);
  const a = AGENTS[shown];
  const toggle = (i: number) => {
    setOpen(open === i ? -1 : i);
    if (open !== i) setShown(i);
  };
  return (
    <div className="grid gap-10 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:gap-0">
      <div className="flex flex-col md:pr-12">
        {AGENTS.map((ag, i) => {
          const on = i === open;
          return (
            <div key={ag.name} data-reveal className="acc-item relative border-b border-line" data-open={on || undefined}>
              <h3>
                <button type="button" onClick={() => toggle(i)} aria-expanded={on} aria-controls={`agent-${i}`}
                  className={`group flex w-full items-center justify-between gap-4 py-5 text-left font-serif text-2xl tracking-tight transition-[color,padding] duration-300 ${on ? "pl-4 text-fg" : "text-muted hover:pl-2 hover:text-fg"}`}>
                  {ag.name}
                  <span aria-hidden className={`grid size-7 shrink-0 place-items-center rounded-full border font-sans text-base transition duration-300 ${on ? "rotate-45 border-fg text-fg" : "border-line group-hover:border-fg/60"}`}>+</span>
                </button>
              </h3>
              {/* grid rows 0fr → 1fr animates the height without measuring it */}
              <div id={`agent-${i}`} inert={!on} className={`grid transition-[grid-template-rows,opacity] duration-500 ease-[cubic-bezier(.2,.7,.2,1)] ${on ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"}`}>
                <div className="overflow-hidden">
                  <div className={`pb-7 pl-4 transition-transform duration-500 ${on ? "translate-y-0" : "-translate-y-2"}`}>
                    <p className="max-w-md leading-relaxed">{ag.does}</p>
                    <ul className="mt-4 flex flex-col gap-2">
                      {ag.facts.map((f, j) => (
                        <li key={f} className={on ? "acc-line flex gap-2.5" : "flex gap-2.5"} style={{ animationDelay: `${120 + j * 70}ms` }}>
                          <span aria-hidden className="text-ok">✓</span>{f}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="relative min-h-[480px] overflow-hidden" data-reveal>
        {/* one picture per agent, stacked; the open agent's fades in with a slow zoom */}
        {AGENTS.map((ag, i) => (
          <div key={ag.name} className="acc-photo absolute inset-0" data-on={i === shown || undefined} aria-hidden={i !== shown}>
            <Image src={ag.photo.src} alt={ag.photo.alt} fill sizes="(min-width: 768px) 58vw, 100vw"
              className="photo object-cover" style={{ objectPosition: ag.photo.pos }} />
          </div>
        ))}
        {/* a real fragment of the run page: the open agent's sub-steps; remounts per agent so its lines play in */}
        <div key={shown} data-ui className="feed-card absolute right-5 bottom-5 left-5 rounded-lg border border-line bg-bg/95 p-4 sm:right-8 sm:left-auto sm:w-[400px]">
          <div className="flex items-center justify-between">
            <p className="label">{a.name} · live</p>
            <p className="label text-ok"><span aria-hidden className="pulse">●</span> working</p>
          </div>
          <ul className="mt-3 flex flex-col gap-2 text-sm" aria-live="polite">
            {a.feed.map((line, i) => (
              <li key={line} className={`acc-line flex gap-2.5 ${i === a.feed.length - 1 ? "text-fg" : "text-muted"}`} style={{ animationDelay: `${150 + i * 220}ms` }}>
                <span aria-hidden className={i === a.feed.length - 1 ? "pulse text-run" : ""}>{i === a.feed.length - 1 ? "●" : "✓"}</span>
                {line}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
