import type { Metadata } from "next";
import { Suspense } from "react";

import { DeadLetters } from "@/components/DeadLetters";

export const metadata: Metadata = { title: "Dead letters · Retro" };

export default function DeadLettersPage() {
  // DeadLetters reads ?run= from the URL, so it sits in Suspense (cacheComponents)
  return (
    <Suspense fallback={<div className="mx-auto mt-16 h-40 max-w-4xl animate-pulse rounded-lg bg-surface-2" />}>
      <DeadLetters />
    </Suspense>
  );
}
