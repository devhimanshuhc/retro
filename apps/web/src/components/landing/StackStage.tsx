"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

export type Step = { tier: string; label: string; title: string; body: string; callouts: [string, string] };
type Geometry = {
  width: number; height: number; gapShut: number; gapOpen: number; liftPerUnit: number;
  order: string[]; anchors: Record<string, { a: number[]; b: number[] }>;
};

const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
const ease = (t: number) => 1 - Math.pow(1 - t, 3);
const SVG_NS = "http://www.w3.org/2000/svg";

/** Pinned while the visitor scrolls past: the rack comes apart, then each tier lights in turn with its callouts.
 * Phones get the rack apart and all four steps as a list (no pinning). Reduced motion: no travel, steps still change. */
export function StackStage({ steps, figure, geometry: g }: { steps: Step[]; figure: ReactNode; geometry: Geometry }) {
  const section = useRef<HTMLElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(-1); // -1: the intro, before the first step

  useEffect(() => {
    const sec = section.current!;
    const svg = stage.current!.querySelector("svg")!;
    const tiers = g.order.map((id) => svg.querySelector<SVGGElement>(`[data-tier="${id}"]`)!);
    const calloutLayer = svg.querySelector<SVGGElement>("[data-callouts]")!;
    const still = matchMedia("(prefers-reduced-motion: reduce)");
    const phone = matchMedia("(max-width: 767px)");
    let raf = 0;
    let shown = -2;
    let drawn = "";

    const callouts = (step: number, dys: number[]) => {
      calloutLayer.replaceChildren();
      if (step < 0) return;
      const s = steps[step];
      const ti = g.order.indexOf(s.tier);
      const { a, b } = g.anchors[s.tier];
      [[a, 18, "start", "var(--ok)"], [b, g.width - 18, "end", s.tier === "record" ? "var(--bad)" : "var(--ok)"]].forEach(([pt, edge, anchor, colour], i) => {
        const [x, y0] = pt as number[];
        const y = y0 + dys[ti];
        const ly = y - 46 - i * 8;
        const grp = document.createElementNS(SVG_NS, "g");
        grp.setAttribute("class", "callout");
        const line = document.createElementNS(SVG_NS, "polyline");
        line.setAttribute("points", `${x},${y} ${x},${ly} ${edge},${ly}`);
        const dot = document.createElementNS(SVG_NS, "circle");
        dot.setAttribute("cx", String(x));
        dot.setAttribute("cy", String(y));
        dot.setAttribute("r", "2.6");
        dot.setAttribute("style", `fill:${colour}`);
        const tag = document.createElementNS(SVG_NS, "circle");
        tag.setAttribute("cx", String(anchor === "start" ? (edge as number) + 4 : (edge as number) - 4));
        tag.setAttribute("cy", String(ly - 9));
        tag.setAttribute("r", "2.4");
        tag.setAttribute("style", `fill:${colour}`);
        const text = document.createElementNS(SVG_NS, "text");
        text.setAttribute("x", String(anchor === "start" ? (edge as number) + 12 : (edge as number) - 12));
        text.setAttribute("y", String(ly - 6));
        text.setAttribute("text-anchor", anchor as string);
        text.textContent = s.callouts[i].toUpperCase();
        grp.append(line, dot, tag, text);
        calloutLayer.append(grp);
      });
    };

    const frame = () => {
      raf = 0;
      const r = sec.getBoundingClientRect();
      const p = phone.matches ? 1 : clamp(-r.top / Math.max(1, r.height - innerHeight));
      const open = phone.matches || still.matches ? 1 : ease(clamp(p / 0.14));
      const step = phone.matches ? -1 : p < 0.16 ? -1 : Math.min(steps.length - 1, Math.floor(((p - 0.16) / 0.84) * steps.length));
      const activeTier = step < 0 ? -1 : g.order.indexOf(steps[step].tier);
      const pitch = g.gapShut + (g.gapOpen - g.gapShut) * open;
      const centre = (3 * (g.gapOpen - pitch)) / 2; // keep the rack centred as it closes
      const dys = tiers.map((_, i) => {
        const extra = activeTier >= 0 && i > activeTier ? 26 : 0; // part the stack above the lit tier
        return (i * pitch + centre + extra) * g.liftPerUnit;
      });
      tiers.forEach((t, i) => {
        t.style.transform = `translateY(${dys[i]}px)`;
        t.dataset.dim = activeTier >= 0 && i !== activeTier ? "1" : "0";
      });
      if (step !== shown) {
        shown = step;
        setActive(step);
      }
      const key = `${step}|${dys.map((d) => d.toFixed(1)).join()}`;
      if (key !== drawn) {
        drawn = key;
        callouts(step, dys);
      }
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
    <section ref={section} id="how" aria-labelledby="how-h" className="stack-section relative border-y border-line md:h-[420vh]">
      <div className="grid md:sticky md:top-0 md:h-screen md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="relative flex flex-col justify-center gap-10 px-5 py-16 sm:px-10 md:py-0">
          <div className={`transition-opacity duration-500 ${active >= 0 ? "md:pointer-events-none md:absolute md:opacity-0" : ""}`}>
            <h2 id="how-h" className="max-w-lg font-serif text-4xl leading-[1.05] tracking-tight lg:text-5xl">
              Infrastructure built to <em>recover</em>
            </h2>
            <p className="mt-5 max-w-sm text-[1.05rem] leading-relaxed">
              Each tier does one thing. Scroll to take the scheduler apart and see what holds a run together
              when a worker dies, a model misbehaves or a rate limit hits.
            </p>
          </div>

          {/* the rail: every step is real text (read by screen readers in order); desktop shows the active one */}
          <ol className="flex flex-col gap-6 md:gap-0">
            {steps.map((s, i) => {
              const on = active === i;
              return (
                <li key={s.tier} className="relative md:pl-6">
                  <span aria-hidden className="absolute top-0 bottom-0 left-0 hidden w-px bg-line md:block">
                    <span className={`block w-px bg-fg transition-all duration-500 ${active > i ? "h-full" : on ? "h-1/2" : "h-0"}`} />
                  </span>
                  <p className={`label flex items-center gap-3 py-1.5 transition-colors ${on ? "text-fg" : "text-muted"}`}>
                    <span aria-hidden className={`grid size-3 place-items-center rounded-full border ${on ? "border-ok" : "border-line"} -ml-[1.85rem] hidden bg-bg md:grid`}>
                      <span className={`size-1.5 rounded-full ${on ? "bg-ok" : "bg-line"}`} />
                    </span>
                    <span className="text-muted">0{i + 1}</span> {s.label}
                  </p>
                  <div className={`grid grid-rows-[1fr] transition-all duration-500 ${on ? "md:grid-rows-[1fr] md:opacity-100" : "md:grid-rows-[0fr] md:opacity-0"}`}>
                    <div className="overflow-hidden">
                      <h3 className="pt-2 font-serif text-3xl tracking-tight">{s.title}</h3>
                      <p className="mt-2 max-w-sm pb-4 leading-relaxed">{s.body}</p>
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        </div>

        <div ref={stage} className="dot-grid iso relative flex items-center justify-center border-l border-line px-4 py-10 md:py-0">
          <div className="w-full max-w-[560px]">{figure}</div>
        </div>
      </div>
    </section>
  );
}
