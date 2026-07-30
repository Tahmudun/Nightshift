'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';

/**
 * TanStack Query owns server state; Zustand is reserved for scene state (M4).
 *
 * The client is created in state rather than at module scope so that it is not
 * shared between requests on the server, which would leak one user's cache into
 * another's — a real bug even at one user, because it also breaks Fast Refresh.
 */
export function Providers({ children }: { readonly children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
