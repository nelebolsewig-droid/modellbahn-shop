import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

/**
 * Paths that belong to the FastAPI backend. Behind Caddy they never reach Next.js
 * (see ../Caddyfile); `next dev` forwards them so that the browser talks to a single
 * origin and the session cookies stay first-party, exactly as in production.
 */
const BACKEND_PATHS = ["/api/:path*", "/healthz", "/readyz"] as const;

export default function nextConfig(phase: string): NextConfig {
  const isDevServer = phase === PHASE_DEVELOPMENT_SERVER;
  const apiOrigin = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

  return {
    output: "standalone",
    poweredByHeader: false,
    reactStrictMode: true,
    typedRoutes: true,
    ...(isDevServer && {
      async rewrites() {
        return BACKEND_PATHS.map((source) => ({
          source,
          destination: `${apiOrigin}${source}`,
        }));
      },
    }),
  };
}
