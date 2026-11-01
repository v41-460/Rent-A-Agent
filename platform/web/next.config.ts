import path from "node:path";
import type { NextConfig } from "next";

// The browser only ever talks to this Next.js server. /api/* is forwarded to the
// FastAPI backend, so the backend is never exposed directly and no CORS is needed.
const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // The repo root, so the app can use types from /shared and pages from /agents/*/web.
  turbopack: { root: path.resolve(__dirname, "../..") },
  outputFileTracingRoot: path.resolve(__dirname, "../.."),
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
