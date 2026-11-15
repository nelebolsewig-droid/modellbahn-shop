import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

/**
 * Paths that belong to the FastAPI backend. Behind Caddy they never reach Next.js
 * (see ../Caddyfile); `next dev` forwards them so that the browser talks to a single
 * origin and the session cookies stay first-party, exactly as in production.
 */
const BACKEND_PATHS = ["/api/:path*", "/healthz", "/readyz"] as const;

/**
 * Old addresses of the Stellwerk (bookmarks, links in mails) and where they live now
 * (ADR 0028): the catalogue is "Modelle", categories and scales are settings, and the
 * quick entry became the wizard "Neues Modell". The specific ones come first.
 */
export const STELLWERK_REDIRECTS = [
  { source: "/admin/katalog/kategorien", destination: "/admin/einstellungen/kategorien" },
  { source: "/admin/katalog/massstaebe", destination: "/admin/einstellungen/massstaebe" },
  { source: "/admin/katalog", destination: "/admin/modelle" },
  { source: "/admin/katalog/:id", destination: "/admin/modelle/:id" },
  { source: "/admin/erfassen", destination: "/admin/modelle/neu" },
] as const;

export default function nextConfig(phase: string): NextConfig {
  const isDevServer = phase === PHASE_DEVELOPMENT_SERVER;
  const apiOrigin = process.env.API_INTERNAL_URL || "http://localhost:8000";

  return {
    output: "standalone",
    poweredByHeader: false,
    reactStrictMode: true,
    typedRoutes: true,
    // Caddy compresses everything it forwards from Next.js (`encode` in ../Caddyfile).
    // Next's own gzip would also hold back the SSE stream of the admin feed that
    // `next dev` forwards to the API: the events would sit in the compressor's buffer.
    compress: false,
    async redirects() {
      return STELLWERK_REDIRECTS.map((redirect) => ({ ...redirect, permanent: true }));
    },
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
