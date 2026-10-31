import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { AgentsAccordion } from "@/components/landing/AgentsAccordion";
import { GlyphField } from "@/components/landing/GlyphField";
import { Reveal } from "@/components/landing/Reveal";
import { StackScroll } from "@/components/landing/StackScroll";
import { FaultLine } from "@/components/landing/FaultLine";
import { GoogleDriveIcon } from "@/components/GoogleDriveIcon";
import { Wordmark } from "@/components/Mark";

import "../../../vendor/anatomy/iso.css";
import "./landing.css";
import { START_URL } from "@/lib/api";

export const metadata: Metadata = {
  title: "Retro · research agents you can leave running",
  description: "AI agents plan, research, write and review a cited report. They talk only through queues, so a crash, a rate limit or a bad answer slows a run down instead of losing it.",
};

const NAV = [
  ["How it works", "#how"],
  ["Why actors", "#why"],
  ["Agents", "#agents"],
  ["Failures", "#failures"],
  ["Your work", "#work"],
] as const;

// What a run guarantees, each backed by code and a test (see "What happens when it breaks")
const GUARANTEES = [
  ["Nothing is lost", "If a worker crashes mid-step, another picks the job up and the step still runs once."],
  ["Every quote is real", "Quotes are copied from the fetched page by code. The model never writes them."],
  ["Every number is checked", "A draft with a number its sources don't state goes back for a rewrite."],
  ["Spending is capped", "Each run has a token budget. It stops with its best draft instead of looping."],
  ["Failures are kept", "A job that fails every retry is saved with its error and replays in one click."],
];

// Typical agent chain vs Retro, one difference per row
const COMPARE = [
  ["Context", "One long conversation carries everything between agents, so it grows, drifts and gets summarised away.",
    "Agents pass a short note with the run's id. Each one reads the full, original record before it works."],
  ["Crashes", "Every agent runs in one process. If it dies, the whole run is gone and starts over.",
    "Each agent is its own worker. A crash pauses one step; another worker picks it up."],
  ["Rate limits", "One limit stalls everything, or blind retries hammer the provider.",
    "Only that agent's queue pauses until the limit resets. The others keep going."],
  ["Retries", "A retry can repeat work and write the same output twice.",
    "Every step is claimed once, so a retry never duplicates a draft."],
  ["Failures", "A failed run leaves nothing behind to inspect.",
    "Failed jobs are kept with their error and the model's last output, ready to replay."],
  ["Scale", "Going faster means a bigger machine for the whole chain.",
    "Add workers for just the slow step, while the rest stay as they are."],
];

const FAILURES = [
  { title: "A worker is killed mid-step", fix: "Another worker picks its job up, and the step still runs exactly once.", glyph: "✕" },
  { title: "The model is rate-limited", fix: "Every worker of that agent pauses together until the limit resets, then the job retries. Other agents keep going.", glyph: "⏸" },
  { title: "The model returns junk", fix: "Output is checked against a schema. A bad plan or finding fails the attempt, and the retry starts from clean inputs.", glyph: "≠" },
  { title: "A job fails three times", fix: "It moves to the dead-letter queue with its error, stack trace and the model's last output. Replay it with one call.", glyph: "↺" },
  { title: "The same message arrives twice", fix: "Each step can only be claimed once. The duplicate sees the step is done and skips it.", glyph: "⧉" },
  { title: "A number is made up", fix: "The critic checks every number in the report against the sources in code, and rejects the draft if one is missing.", glyph: "#" },
];


export default function Landing() {
  return (
    <div className="dark-only min-h-dvh">
      <Reveal />

      <header className="sticky top-0 z-30 bg-bg/90 backdrop-blur-sm">
        <nav aria-label="Main" className="mx-auto flex max-w-[1440px] items-center justify-between gap-6 px-5 py-4 sm:px-10">
          <Link href="/" aria-label="Retro home"><Wordmark /></Link>
          <ul className="hidden items-center gap-8 lg:flex">
            {NAV.map(([label, href]) => (
              <li key={href}><a href={href} className="label text-fg/85 transition hover:text-fg">{label}</a></li>
            ))}
          </ul>
          <div className="flex items-center gap-3">
            <Link href={START_URL} className="btn-primary">Start a run</Link>
          </div>
        </nav>
      </header>

      <main>
        {/* Hero */}
        <section aria-labelledby="hero-h" className="mx-auto max-w-[1440px] px-5 pt-20 pb-14 sm:px-10 sm:pt-28">
          <h1 id="hero-h" data-reveal className="max-w-[14ch] font-serif text-[clamp(2.35rem,7.4vw,6.6rem)] leading-[0.98] tracking-[-0.03em]">
            Research agents you can leave running
          </h1>
          <div className="mt-8 flex flex-col gap-10 lg:flex-row lg:items-end lg:justify-between">
            <div data-reveal className="max-w-xl">
              <p className="text-[1.2rem] leading-relaxed">
                AI agents plan, research, write and review a cited report for you.{" "}
                <span className="text-muted">They talk only through queues, so a crash, a rate limit or a bad answer slows a run down instead of losing it.</span>
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link href={START_URL} className="btn-primary">Start a run <span aria-hidden className="arrow">→</span></Link>
                <a href="#how" className="btn-ghost">See how it works</a>
              </div>
            </div>
          </div>
        </section>

        <div className="border-y border-line"><GlyphField /></div>

        {/* What every run guarantees */}
        <section aria-labelledby="promise-h" className="mx-auto max-w-[1440px] px-5 sm:px-10">
          <h2 id="promise-h" className="sr-only">What every run guarantees</h2>
          <ul className="grid border-l border-dashed border-line sm:grid-cols-2 lg:grid-cols-5">
            {GUARANTEES.map(([title, body]) => (
              <li key={title} data-reveal className="flex flex-col gap-3 border-r border-b border-dashed border-line px-6 py-8">
                <p className="label flex items-center gap-2 text-fg"><span aria-hidden className="text-ok">●</span>{title}</p>
                <p className="text-[0.95rem] leading-relaxed text-fg/75">{body}</p>
              </li>
            ))}
          </ul>
        </section>

        <div className="h-24 sm:h-36" />
        <StackScroll />

        {/* Why actors */}
        <section id="why" aria-labelledby="why-h" className="mx-auto max-w-[1440px] px-5 pt-28 pb-16 sm:px-10 sm:pt-40">
          <h2 id="why-h" data-reveal className="max-w-3xl font-serif text-4xl tracking-tight sm:text-5xl">
            Built like a post office, not a phone call
          </h2>
          <p data-reveal className="mt-4 max-w-2xl text-[1.05rem] leading-relaxed">
            Most multi-agent tools chain agents inside one long conversation. Retro runs each agent as an independent
            worker that only exchanges short messages, so one failure stays one failure.
          </p>
          <div className="mt-12 overflow-hidden rounded-lg border border-line">
            <div className="grid grid-cols-[7rem_1fr_1fr] border-b border-line bg-surface text-sm sm:grid-cols-[10rem_1fr_1fr]">
              <span />
              <p className="label px-4 py-3 text-muted">A typical agent chain</p>
              <p className="label px-4 py-3 text-ok">Retro</p>
            </div>
            {COMPARE.map(([topic, them, us]) => (
              <div key={topic} data-reveal className="grid grid-cols-[7rem_1fr_1fr] border-b border-line last:border-b-0 sm:grid-cols-[10rem_1fr_1fr]">
                <p className="px-4 py-4 font-serif text-lg">{topic}</p>
                <p className="px-4 py-4 text-[0.95rem] leading-relaxed text-muted"><span aria-hidden className="mr-2 text-bad">✕</span>{them}</p>
                <p className="bg-ok/[0.04] px-4 py-4 text-[0.95rem] leading-relaxed"><span aria-hidden className="mr-2 text-ok">✓</span>{us}</p>
              </div>
            ))}
          </div>
        </section>
        <FaultLine />

        {/* Agents */}
        <section id="agents" aria-labelledby="agents-h" className="mx-auto max-w-[1440px] px-5 py-28 sm:px-10 sm:py-40">
          <h2 id="agents-h" data-reveal className="font-serif text-4xl tracking-tight sm:text-5xl">Specialists, not one long prompt</h2>
          <p data-reveal className="mt-4 mb-12 max-w-xl text-[1.05rem] leading-relaxed">
            Like operators at a switchboard, no agent does another&apos;s work. Each reads the whole run from the record,
            does its part and passes a message on. You watch every sub-step live.
          </p>
          <AgentsAccordion />
        </section>

        {/* Failures */}
        <section id="failures" aria-labelledby="fail-h" className="border-t border-line">
          <div className="mx-auto grid max-w-[1440px] gap-12 px-5 py-28 sm:px-10 sm:py-40 lg:grid-cols-[minmax(0,4fr)_minmax(0,8fr)]">
            <div>
              <h2 id="fail-h" data-reveal className="font-serif text-4xl tracking-tight sm:text-5xl">What happens when it breaks</h2>
              <p data-reveal className="mt-4 max-w-sm text-[1.05rem] leading-relaxed">
                Every one of these is a test that kills, floods or poisons the real system and checks the run still ends
                where it should.
              </p>
              <div data-reveal className="relative mt-10 hidden aspect-[4/3] overflow-hidden lg:block">
                <Image src="/img/mail-sorting.jpg" alt="A post office mail sorting room in the 1920s, with pigeonhole racks and a sorting table" fill sizes="30vw" className="photo object-cover" />
              </div>
            </div>
            <ul className="grid content-start gap-x-10 sm:grid-cols-2">
              {FAILURES.map((f) => (
                <li key={f.title} data-reveal className="flex gap-4 border-b border-line py-6">
                  <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-md border border-line text-lg text-muted">{f.glyph}</span>
                  <div>
                    <h3 className="font-medium">{f.title}</h3>
                    <p className="mt-1 text-[0.95rem] leading-relaxed text-fg/75">{f.fix}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* Your work: connectors, edits, artifacts */}
        <section id="work" aria-labelledby="work-h" className="border-t border-line">
          <div className="mx-auto grid max-w-[1440px] items-center gap-14 px-5 py-28 sm:px-10 sm:py-36 lg:grid-cols-2">
            <div>
              <h2 id="work-h" data-reveal className="font-serif text-4xl tracking-tight sm:text-5xl">Your report, where you work</h2>
              <ul className="mt-10 flex flex-col gap-7">
                {[
                  ["Open it in Google Docs", "Connect your Google account once. Every report opens as a real Google Doc in your Drive, with headings, links and sources intact. Retro can only see the docs it creates."],
                  ["Ask for changes", "Shorter, a new section, a different angle: type it under the report. The writer revises it from the same evidence and the critic checks the change was made."],
                  ["Keep every report", "Artifacts collects every finished report. Open one as a clean page to share, or go back to its chat."],
                ].map(([t, d]) => (
                  <li key={t} data-reveal className="flex gap-4">
                    <span aria-hidden className="mt-1 grid size-8 shrink-0 place-items-center rounded-md border border-line bg-surface">
                      {t.startsWith("Open") ? <GoogleDriveIcon className="size-4" /> : <span className="text-sm text-muted">{t.startsWith("Ask") ? "✎" : "¶"}</span>}
                    </span>
                    <div><p className="font-medium">{t}</p><p className="mt-1 text-[0.95rem] leading-relaxed text-fg/75">{d}</p></div>
                  </li>
                ))}
              </ul>
            </div>
            {/* a real fragment of the app: the report panel's header and the change box */}
            <div data-reveal data-ui className="dot-grid rounded-xl border border-line p-6 sm:p-10">
              <div className="overflow-hidden rounded-lg border border-line bg-surface shadow-2xl shadow-black/40">
                <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-serif text-[0.95rem]">Nvidia Q2 FY2027 Earnings: Market Report</p>
                    <p className="font-mono text-[11px] text-muted">draft 2 · 6 sources</p>
                  </div>
                  <span className="grid size-7 place-items-center rounded-full bg-surface-2 ring-1 ring-ok/40"><GoogleDriveIcon className="size-[15px]" /></span>
                  <span className="grid size-7 place-items-center text-sm text-muted">⧉</span>
                  <span className="grid size-7 place-items-center text-sm text-muted">↓</span>
                </div>
                <p className="border-b border-line px-4 py-1.5 font-mono text-[11px] text-muted">
                  <span className="text-ok">✓ passed</span> · factual <span className="text-fg/80">1.00</span> · citations <span className="text-fg/80">1.00</span> · sources <span className="text-fg/80">1.00</span>
                </p>
                <div className="space-y-2 px-5 py-5">
                  <p className="font-serif text-xl">Executive Summary</p>
                  <p className="text-sm leading-relaxed text-fg/80">Revenue was $96.2 billion, up 106% from a year ago <span className="rounded-full bg-surface-2 px-1.5 font-mono text-[10px]">1</span>. Data Center revenue reached $89.0 billion <span className="rounded-full bg-surface-2 px-1.5 font-mono text-[10px]">1</span>.</p>
                </div>
                <div className="m-4 mt-0 flex items-center justify-between rounded-lg border border-line bg-bg px-3 py-2.5">
                  <span className="text-sm text-muted">Add a short risks section…</span>
                  <span className="btn-primary px-3 py-1 text-[11px]">Edit →</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Close */}
        <section aria-labelledby="cta-h" className="border-t border-line">
          <div className="mx-auto flex max-w-[1440px] flex-col items-center px-5 py-24 text-center sm:px-10 sm:py-32">
            <h2 id="cta-h" data-reveal className="max-w-[18ch] font-serif text-4xl leading-[1.05] tracking-tight sm:text-6xl">
              Ask a question. Watch it get answered.
            </h2>
            <Link data-reveal href={START_URL} className="btn-primary mt-10">Start a run <span aria-hidden className="arrow">→</span></Link>
          </div>
        </section>
        <div aria-hidden className="border-t border-line"><GlyphField /></div>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto grid max-w-[1440px] gap-12 px-5 py-16 sm:px-10 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <div>
            <Wordmark size="lg" />
            <p className="mt-4 max-w-sm text-sm leading-relaxed text-muted">
              Research agents that plan, read real sources, write a cited report and check it, and keep going when
              something breaks.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-8">
            <FooterCol title="Product" links={[["Start a run", START_URL], ["How it works", "#how"], ["Agents", "#agents"]]} />
            <FooterCol title="Reliability" links={[["Failure modes", "#failures"], ["Dead letters", "/dead-letters"]]} />
          </div>
        </div>
        <div className="mx-auto max-w-[1440px] border-t border-line px-5 py-6 text-[13px] leading-relaxed text-muted sm:px-10">
          <p className="max-w-4xl">
            Pictures: “Mail sorting room, U.S. Post
            Office, Washington, D.C.” by National Photo Company; “WAAF telephone operators at No. 11 Group HQ, Uxbridge,
            1942” by a Royal Air Force official photographer; “Reading room, Library of Congress” by National Photo Company;
            “Motor Transport building: typists at work” (1938) by Sam Hood, State Library of New South Wales; “Inspecting
            parts” (1915) by Bain News Service. All public domain, via{" "}
            <a className="underline underline-offset-2 hover:text-fg" href="https://commons.wikimedia.org/">Wikimedia Commons</a>.
           
          </p>
        </div>
      </footer>
    </div>
  );
}

function FooterCol({ title, links }: { title: string; links: [string, string][] }) {
  return (
    <div>
      <h2 className="label text-muted">{title}</h2>
      <ul className="mt-4 flex flex-col gap-2.5 text-sm">
        {links.map(([l, h]) => <li key={l}><a href={h} className="text-fg/85 hover:text-fg">{l}</a></li>)}
      </ul>
    </div>
  );
}
