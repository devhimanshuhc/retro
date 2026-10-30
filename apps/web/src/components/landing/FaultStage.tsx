"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

type Step = { title: string; body: string };
type Geometry = { lift: number; travel: number; xUnit: number[]; zUnit: number[] };

const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
const ease = (t: number) => 1 - Math.pow(1 - t, 3);

/** Pinned while scrolling: the crashed station floats with a red lamp, messages wait, a fresh station drops in,
 * the messages move on. Phones and reduced motion show the recovered end state with every step listed. */
export function FaultStage({ steps, figure, geometry: g }: { steps: Step[]; figure: ReactNode; geometry: Geometry }) {
  const section = useRef<HTMLElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const [step, setStep] = useState(0);

  useEffect(() => {
    const sec = section.current!;
    const svg = stage.current!.querySelector("svg")!;
    const crashed = svg.querySelector<SVGGElement>("[data-crashed]")!;
    const down = crashed.querySelector<SVGGElement>('[data-lamp="down"]');
    const ok = crashed.querySelector<SVGGElement>('[data-lamp="ok"]');
    const caps = [...svg.querySelectorAll<SVGGElement>("[data-capsule]")];
    const still = matchMedia("(prefers-reduced-motion: reduce)");
    const phone = matchMedia("(max-width: 767px)");
    let raf = 0;

    const frame = () => {
      raf = 0;
      const r = sec.getBoundingClientRect();
      const p = phone.matches || still.matches ? 1 : clamp(-r.top / Math.max(1, r.height - innerHeight));
      // one move per caption, each inside its quarter of the scroll:
      // 1 the station crashes out of its place · 2 messages arrive and wait · 3 a fresh station drops in · 4 they flow on
      const lift = p < 0.5 ? g.lift * ease(clamp((p - 0.02) / 0.18)) : g.lift * (1 - ease(clamp((p - 0.52) / 0.18)));
      crashed.style.transform = `translate(${g.zUnit[0] * lift}px, ${g.zUnit[1] * lift}px)`;
      crashed.style.opacity = String(1 - 0.45 * (lift / g.lift));
      if (down) down.style.opacity = lift > 1 ? "1" : "0";
      if (ok) ok.style.opacity = lift > 1 ? "0" : "1";
      caps.forEach((c, i) => {
        const arrive = -g.travel * 0.5 * (1 - ease(clamp((p - 0.27 - i * 0.04) / 0.16))); // from the previous station
        const flow = g.travel * ease(clamp((p - 0.77 - i * 0.05) / 0.16));
        const dx = arrive + flow;
        c.style.transform = `translate(${g.xUnit[0] * dx}px, ${g.xUnit[1] * dx}px)`;
        c.style.opacity = String(clamp((p - 0.25) / 0.04)); // not there until they leave the previous station
      });
      setStep(Math.min(steps.length - 1, Math.floor(p * steps.length * 0.999)));
    };
    const onScroll = () => (raf ||= requestAnimationFrame(frame));
    frame();
    addEventListener("scroll", onScroll, { passive: true });
    addEventListener("resize", onScroll);
    return () => {
      removeEventListener("scroll", onScroll);
      removeEventListener("resize", onScroll);
      cancelAnimationFrame(raf);
    };
  }, [g, steps]);

  return (
    <section ref={section} aria-labelledby="fault-h" className="relative md:h-[320vh]">
      <div className="grid md:sticky md:top-0 md:h-screen md:grid-cols-[minmax(0,4fr)_minmax(0,8fr)]">
        <div className="flex flex-col justify-center gap-6 px-5 py-14 sm:px-10 md:py-0">
          <h3 id="fault-h" className="font-serif text-3xl tracking-tight sm:text-4xl">Watch a crash, recovered</h3>
          <ol className="flex flex-col gap-4">
            {steps.map((s, i) => (
              <li key={s.title} className={`border-l-2 pl-4 transition-all duration-500 ${i === step ? "border-ok opacity-100" : "border-line md:opacity-40"}`}>
                <p className="font-medium">{s.title}</p>
                <p className="mt-1 text-[0.95rem] leading-relaxed text-fg/75">{s.body}</p>
              </li>
            ))}
          </ol>
        </div>
        <div ref={stage} className="dot-grid iso flex items-center justify-center border-l border-line px-4 py-10 md:py-0">
          <div className="w-full max-w-[820px]">{figure}</div>
        </div>
      </div>
    </section>
  );
}
