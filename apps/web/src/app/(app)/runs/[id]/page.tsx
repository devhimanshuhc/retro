import type { Metadata } from "next";
import { Suspense } from "react";

import { RunView } from "@/components/RunView";

export const metadata: Metadata = { title: "Run · Retro" };

export default function RunPage({ params }: PageProps<"/runs/[id]">) {
  return (
    <Suspense fallback={<div className="mx-auto mt-16 h-32 max-w-3xl animate-pulse rounded-2xl bg-surface-2" />}>
      {params.then(({ id }) => <RunView key={id} id={id} />)}
    </Suspense>
  );
}
