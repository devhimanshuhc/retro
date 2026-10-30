"use client";

import { useEffect, useRef } from "react";

const CELL_W = 10;
const CELL_H = 15;
const AGENTS = ["supervisor", "research", "write", "critic"];
const hex = () => Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, "0");

type Packet = { row: number; x: number; speed: number; text: string };

/** The band under the hero: a field of queue traffic. Each bright run is a message as it really looks on the
 * wire, `<run>-<step>-<revision>` (ids only, never the work), sliding along its row like a capsule in a tube. */
export function GlyphField() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const css = getComputedStyle(canvas);
    const ink = css.getPropertyValue("--fg").trim() || "#ece7dd";
    const faint = css.getPropertyValue("--border").trim() || "#2b2926";
    const font = `12px ${css.getPropertyValue("--font-geist-mono").trim() || "ui-monospace"}, monospace`;
    let w = 0, h = 0, cols = 0, rows = 0, raf = 0, last = 0, visible = true;
    let base: string[] = [];
    let packets: Packet[] = [];

    const spawn = (anywhere: boolean): Packet => ({
      row: Math.floor(Math.random() * rows),
      x: anywhere ? Math.random() * w : -200 - Math.random() * 400,
      speed: 18 + Math.random() * 46,
      text: `${hex()}-${AGENTS[Math.floor(Math.random() * 4)]}-${Math.floor(Math.random() * 3)}`,
    });

    const size = () => {
      const dpr = Math.min(devicePixelRatio || 1, 2);
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      cols = Math.ceil(w / CELL_W);
      rows = Math.floor(h / CELL_H);
      base = Array.from({ length: rows }, () => Array.from({ length: cols }, () => (Math.random() < 0.82 ? "/" : " ")).join(""));
      packets = Array.from({ length: Math.max(6, Math.round((rows * cols) / 220)) }, () => spawn(true));
    };

    const draw = (dt: number) => {
      ctx.clearRect(0, 0, w, h);
      ctx.font = font;
      ctx.textBaseline = "top";
      ctx.fillStyle = faint;
      for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) if (base[r][c] !== " ") ctx.fillText(base[r][c], c * CELL_W, r * CELL_H + 2);
      ctx.fillStyle = ink;
      for (const p of packets) {
        p.x += p.speed * dt;
        if (p.x > w + 40) Object.assign(p, spawn(false));
        for (let i = 0; i < p.text.length; i++) {
          const x = Math.round((p.x + i * CELL_W) / CELL_W) * CELL_W; // snap to the grid, like a terminal
          if (x < -CELL_W || x > w) continue;
          ctx.globalAlpha = 0.25 + 0.75 * ((i + 1) / p.text.length); // brightest at the head
          ctx.clearRect(x, p.row * CELL_H, CELL_W, CELL_H);
          ctx.fillText(p.text[i], x, p.row * CELL_H + 2);
        }
        ctx.globalAlpha = 1;
      }
    };

    const loop = (t: number) => {
      const dt = last ? Math.min(0.05, (t - last) / 1000) : 0;
      last = t;
      if (visible) draw(dt);
      raf = requestAnimationFrame(loop);
    };

    size();
    draw(0);
    const ro = new ResizeObserver(() => {
      size();
      draw(0);
    });
    ro.observe(canvas);
    const io = new IntersectionObserver(([e]) => (visible = e.isIntersecting));
    io.observe(canvas);
    if (!still) raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
    };
  }, []);

  return (
    <canvas
      ref={ref}
      className="block h-[220px] w-full sm:h-[260px]"
      role="img"
      aria-label="Queue traffic: message ids of the form run, step, revision sliding through their queues"
    />
  );
}
