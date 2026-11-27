import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export: the site is plain files served by Caddy on the VPS.
  output: "export",
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
