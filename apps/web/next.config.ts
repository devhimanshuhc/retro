import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
