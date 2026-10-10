import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError } from '@/lib/api'
import { ThemeProvider } from '@/theme/ThemeProvider'

const isClientError = (error: unknown) =>
  error instanceof ApiError && error.status >= 400 && error.status < 500

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
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
