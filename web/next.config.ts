import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    // Pin the root to this folder so stray lockfiles higher up aren't picked up.
    root: __dirname,
  },
};

export default nextConfig;
