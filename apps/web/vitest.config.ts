import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    // Both e2e directories are Playwright's; vitest must not try to run them.
    // They use `*.spec.ts`, which vitest's default include pattern also matches,
    // so omitting either one here surfaces as a confusing test.describe error.
    exclude: ['node_modules/**', 'e2e/**', 'e2e-seeded/**', '.next/**'],
  },
});
