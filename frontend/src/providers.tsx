import { QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError } from '@/lib/api'
import { recordClientLog } from '@/lib/client-log'
import { ThemeProvider } from '@/theme/ThemeProvider'

const isClientError = (error: unknown) =>
  error instanceof ApiError && error.status >= 400 && error.status < 500

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        // Phase 20: requests that failed for a reason other than the request itself.
        queryCache: new QueryCache({
          onError: (error, query) => {
            if (!isClientError(error))
              recordClientLog('warn', error, JSON.stringify(query.queryKey))
          },
        }),
        defaultOptions: {
          // Client errors (404 for a deleted agent, 422…) will not change on retry.
          queries: { retry: (count, error) => !isClientError(error) && count < 3 },
        },
      }),
  )
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>{children}</ThemeProvider>
    </QueryClientProvider>
  )
}
