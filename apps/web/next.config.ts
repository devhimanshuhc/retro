import type { NextConfig } from "next";

// The public site (Vercel) is the landing page only: "Start a run" leads to the GitHub repo, and the app's pages, which
// need a local Retro behind them, go back to the landing page. A local install leaves this unset and keeps /app.
const START_URL = process.env.NEXT_PUBLIC_START_URL ?? "/app";
const LANDING_ONLY = START_URL.startsWith("http");

const nextConfig: NextConfig = {
  async redirects() {
    if (!LANDING_ONLY) return [];
    return ["/app", "/runs/:path*", "/artifacts/:path*", "/connectors", "/dead-letters"].map((source) => ({
      source, destination: "/", permanent: false,
    }));
  },
  /* config options here */
  cacheComponents: true,
  output: "standalone", // a self-contained server for the Docker image
  devIndicators: { position: "bottom-right" }, // bottom-left covers the workers panel, top-right the report close button
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
