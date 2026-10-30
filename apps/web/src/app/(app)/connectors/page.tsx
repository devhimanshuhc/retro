import type { Metadata } from "next";

import { ConnectorsPage } from "@/components/ConnectorsPage";

export const metadata: Metadata = { title: "Connectors · Retro" };

export default function Connectors() {
  return <ConnectorsPage />;
}
