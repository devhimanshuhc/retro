"use client";

import { useEffect, useRef, useState } from "react";

/** A panel width the viewer chose, remembered in this browser only (a convenience: storage may be missing). */
export function usePanelWidth(key: string, fallback: number) {
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    try {
      const saved = Number(localStorage.getItem(key));
      if (saved > 0) setWidth(saved); // eslint-disable-line react-hooks/set-state-in-effect -- read after mount to match the server render
    } catch {}
  }, [key]);
  const save = (w: number) => {
    setWidth(w);
    try {
      localStorage.setItem(key, String(Math.round(w)));
    } catch {}
  };
  return [width, save] as const;
}

/** The window's width, kept current (0 before mount). */
export function useViewportWidth() {
  const [w, setW] = useState(0);
  useEffect(() => {
    const on = () => setW(innerWidth);
    on();
    addEventListener("resize", on);
    return () => removeEventListener("resize", on);
  }, []);
  return w;
}

/** Drag handle on a panel's inner edge. `edge` is where the handle sits on the panel: "right" for a left sidebar,
 * "left" for a right-hand panel. Dragging past `min` by COLLAPSE_PX closes the panel (on release). Keyboard: arrows
 * resize, Enter closes. */
const COLLAPSE_PX = 80;
export function ResizeHandle({ edge, width, min, max, onResize, onCollapse, label }: {
  edge: "left" | "right";
  width: number;
  min: number;
  max: number;
  onResize: (w: number) => void;
  onCollapse: () => void;
  label: string;
}) {
  const drag = useRef<{ x: number; w: number } | null>(null);
  const [state, setState] = useState<"idle" | "drag" | "closing">("idle");
  const clamp = (w: number) => Math.min(max, Math.max(min, w));

  function move(e: React.PointerEvent) {
    if (!drag.current) return;
    const dx = e.clientX - drag.current.x;
    const raw = drag.current.w + (edge === "right" ? dx : -dx);
    setState(raw < min - COLLAPSE_PX ? "closing" : "drag");
    onResize(clamp(raw));
  }

  function end(e: React.PointerEvent) {
    if (!drag.current) return;
    e.currentTarget.releasePointerCapture(e.pointerId);
    drag.current = null;
    document.body.style.removeProperty("cursor");
    document.body.style.removeProperty("user-select");
    if (state === "closing") onCollapse();
    setState("idle");
  }

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={Math.round(width)}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        drag.current = { x: e.clientX, w: width };
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none"; // no text selection while dragging
        setState("drag");
      }}
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={end}
      onDoubleClick={onCollapse}
      onKeyDown={(e) => {
        const step = e.shiftKey ? 64 : 16;
        if (e.key === "ArrowLeft") onResize(clamp(width + (edge === "right" ? -step : step)));
        else if (e.key === "ArrowRight") onResize(clamp(width + (edge === "right" ? step : -step)));
        else if (e.key === "Enter") onCollapse();
        else return;
        e.preventDefault();
      }}
      title="Drag to resize · drag past the edge or double-click to close"
      className={`group absolute top-0 bottom-0 z-20 hidden w-3 cursor-col-resize touch-none md:block ${edge === "right" ? "-right-1.5" : "-left-1.5"}`}
    >
      <span aria-hidden className={`absolute top-0 bottom-0 left-1/2 w-px -translate-x-1/2 transition-colors ${
        state === "closing" ? "bg-bad" : state === "drag" ? "bg-fg" : "bg-transparent group-hover:bg-fg/50 group-focus-visible:bg-fg"}`} />
    </div>
  );
}
