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
};

export default config;
