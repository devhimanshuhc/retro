import Link from "next/link";
import { Suspense } from "react";

import { AppSidebar } from "@/components/AppSidebar";
import { Wordmark } from "@/components/Mark";
import { ArtifactsLink, ConnectorsLink, DeadLettersLink, RunHistory, RunHistorySkeleton } from "@/components/Sidebar";

function Brand() {
  return (
    <Link href="/" aria-label="Retro home"><Wordmark /></Link>
  );
}

/** The app shell: run history and live workers on the left, the run on the right. */
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="fixed inset-0 flex"> {/* pinned to the window: 100dvh is short of it in some browsers and app webviews */}
      <AppSidebar>
        <div className="px-2 pt-2"><Brand /></div>
        <Link href="/app" className="btn-primary justify-center">
          <span aria-hidden>+</span> New run
        </Link>
        <Suspense fallback={null}>
          <nav aria-label="Sections" className="-mt-2 flex flex-col">
            <DeadLettersLink />
            <ArtifactsLink />
            <ConnectorsLink />
          </nav>
        </Suspense>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <Suspense fallback={<RunHistorySkeleton />}>
            <RunHistory />
          </Suspense>
        </div>
      </AppSidebar>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5 md:hidden">
          <Brand />
          <Link href="/app" className="btn-ghost">+ New</Link>
        </div>
        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
