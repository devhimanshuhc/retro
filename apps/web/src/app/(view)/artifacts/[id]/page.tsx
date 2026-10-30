import type { Metadata } from "next";
import { Suspense } from "react";

import { ArtifactPage } from "@/components/ArtifactPage";

export const metadata: Metadata = { title: "Report · Retro" };

/** A finished report on its own full-screen page (no app chrome), like a published document. */
export default function ArtifactRoute({ params }: PageProps<"/artifacts/[id]">) {
  return (
    <Suspense fallback={<div className="mx-auto mt-24 h-64 max-w-3xl animate-pulse rounded-lg bg-surface-2" />}>
      {params.then(({ id }) => <ArtifactPage key={id} id={id} />)}
    </Suspense>
  );
}
