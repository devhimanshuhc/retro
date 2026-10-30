import type { Metadata } from "next";

import { ArtifactList } from "@/components/ArtifactList";

export const metadata: Metadata = { title: "Artifacts · Retro" };

export default function ArtifactsPage() {
  return <ArtifactList />;
}
