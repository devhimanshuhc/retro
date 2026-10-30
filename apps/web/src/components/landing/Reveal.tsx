"use client";

import { useEffect } from "react";

/** Entrances: every [data-reveal] rises in once as it enters, staggered within its section. Content is visible
 * without script (the hidden state only applies under .js-reveal) and under reduced motion. */
export function Reveal() {
  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const root = document.documentElement;
    root.classList.add("js-reveal");
    const items = [...document.querySelectorAll<HTMLElement>("[data-reveal]")];
    const order = new Map<Element, number>();
    for (const el of items) {
      const sec = el.closest("section, header, footer") ?? document.body;
      order.set(sec, (order.get(sec) ?? -1) + 1);
      el.style.transitionDelay = `${Math.min(order.get(sec)!, 6) * 80}ms`;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) {
          e.target.setAttribute("data-in", "");
          io.unobserve(e.target);
        }
      },
      { rootMargin: "0px 0px -8% 0px" },
    );
    items.forEach((el) => io.observe(el));
    return () => {
      io.disconnect();
      root.classList.remove("js-reveal");
    };
  }, []);
  return null;
}
