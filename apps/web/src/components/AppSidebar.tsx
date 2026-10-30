"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { Mark } from "./Mark";
import { ResizeHandle, usePanelWidth } from "./Resizable";

const MIN = 220;
const MAX = 440;

/** The app sidebar: resizable from its right edge (MIN–MAX px); dragged past MIN it collapses to a thin rail. */
export function AppSidebar({ children }: { children: ReactNode }) {
  const [width, setWidth] = usePanelWidth("retro.sidebar.width", 288);
  const [open, setOpen] = useState(true);
  useEffect(() => {
    try {
      if (localStorage.getItem("retro.sidebar.open") === "0") setOpen(false); // eslint-disable-line react-hooks/set-state-in-effect -- after mount, to match the server render
    } catch {}
  }, []);
  const toggle = (v: boolean) => {
    setOpen(v);
    try {
      localStorage.setItem("retro.sidebar.open", v ? "1" : "0");
    } catch {}
  };

  if (!open) {
    return (
      <aside aria-label="Sidebar (collapsed)" className="hidden w-14 shrink-0 flex-col items-center gap-3 border-r border-line bg-surface py-4 md:flex">
        <Link href="/" aria-label="Retro home"><Mark className="size-6" /></Link>
        <button type="button" onClick={() => toggle(true)} aria-label="Open sidebar" title="Open sidebar"
          className="grid size-8 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-fg">»</button>
        <Link href="/app" aria-label="New run" title="New run" className="grid size-8 place-items-center rounded-full bg-accent text-accent-fg">+</Link>
      </aside>
    );
  }
  return (
    <aside style={{ width: Math.min(MAX, Math.max(MIN, width)) }}
      className="relative hidden shrink-0 flex-col gap-5 border-r border-line bg-surface p-3 md:flex">
      {children}
      <button type="button" onClick={() => toggle(false)} aria-label="Collapse sidebar" title="Collapse sidebar"
        className="absolute top-4 right-3 grid size-7 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-fg">«</button>
      <ResizeHandle edge="right" width={width} min={MIN} max={MAX} onResize={setWidth} onCollapse={() => toggle(false)} label="Resize sidebar" />
    </aside>
  );
}
