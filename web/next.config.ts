import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Build a self-contained server bundle, which is what the Docker image runs.
  // It only changes what `next build` writes, so local development is unaffected.
  output: "standalone",
  turbopack: {
    // Pin the root to this folder so stray lockfiles higher up aren't picked up.
    root: __dirname,
  },
};

export default nextConfig;
