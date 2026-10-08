import { useQuery } from '@tanstack/react-query'
import { Outlet, useLocation } from 'react-router'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useHealth } from '@/hooks/useHealth'
import { getApiBaseUrl } from '@/lib/api'
import { useTheme } from '@/theme/ThemeProvider'
import { AppHeader } from './AppHeader'
import { AppSidebar } from './AppSidebar'
import { OfflineBanner } from './OfflineBanner'
import { sectionForPath } from './nav'

const SIDEBAR_STYLE = {
  '--sidebar-width': '232px',
  '--sidebar-width-icon': '60px',
} as React.CSSProperties

export function AppShell() {
  const { pathname } = useLocation()
  const section = sectionForPath(pathname)
  const health = useHealth()
  const apiUrl = useQuery({
    queryKey: ['api-base-url'],
    queryFn: getApiBaseUrl,
    staleTime: Infinity,
    retry: false,
  }).data
  const { theme } = useTheme()

  return (
    <TooltipProvider delayDuration={300}>
      <SidebarProvider style={SIDEBAR_STYLE} className="h-screen">
        <AppSidebar
          active={section.id}
          inboxCount={0}
          backendState={health.state}
          backendVersion={health.data?.version}
        />
        <SidebarInset className="flex min-w-0 flex-col bg-background">
          <AppHeader section={section} />
          {health.state === 'disconnected' && (
            <OfflineBanner onRetry={() => void health.refetch()} url={apiUrl} />
          )}
          <main className="min-h-0 min-w-0 flex-1 overflow-auto">
            <Outlet />
          </main>
        </SidebarInset>
      </SidebarProvider>
      <Toaster position="bottom-right" theme={theme} duration={5200} />
    </TooltipProvider>
  )
}
