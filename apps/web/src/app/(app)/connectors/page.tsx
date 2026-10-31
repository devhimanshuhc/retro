import type { Metadata } from "next";
import { Suspense } from "react";

import { ConnectorsPage } from "@/components/ConnectorsPage";

export const metadata: Metadata = { title: "Connectors · Retro" };

export default function Connectors() {
  return (
    <Suspense>
      <ConnectorsPage />
    </Suspense>
  ); // reads ?google=… after Google sign-in
}
