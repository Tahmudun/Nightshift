import path from 'node:path';
import type { NextConfig } from 'next';

const config: NextConfig = {
  reactStrictMode: true,
  // Pin the trace root to this app. Without it Next walks up looking for a
  // lockfile and can settle on one in the developer's home directory, which
  // makes the build's file tracing wrong in a way that is hard to notice.
  outputFileTracingRoot: path.join(import.meta.dirname, '../..'),
  // Fail the build on a type error or lint error rather than shipping past it.
  typescript: { ignoreBuildErrors: false },
  eslint: { ignoreDuringBuilds: false },
  poweredByHeader: false,
  /*
   * M5b (ADR 0037): the browser reaches the API through this app's own origin.
   *
   * It used to call `http://127.0.0.1:8000` directly. That is a different
   * *site* from `localhost:3000`, so a `SameSite=Lax` session cookie set by
   * the API is never sent back — and `SameSite=None` requires `Secure`
   * requires HTTPS, which local development does not have. Proxying makes the
   * cookie first-party, removes CORS from the browser path entirely, and means
   * a deployment need not expose the API publicly at all.
   *
   * `API_ORIGIN` and not `NEXT_PUBLIC_API_BASE_URL`: this rewrite runs on the
   * server, so the value must NOT be inlined into the browser bundle. The
   * public variable still exists for the Playwright specs, which talk to the
   * API directly to set up their state.
   */
  async rewrites() {
    const target = process.env.API_ORIGIN ?? 'http://127.0.0.1:8000';
    return [{ source: '/api/ns/:path*', destination: `${target}/:path*` }];
  },
};

export default config;
