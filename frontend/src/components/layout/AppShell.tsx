import { useQuery } from '@tanstack/react-query'
import { Outlet, useLocation } from 'react-router'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useInboxSummary } from '@/api/inbox'
import { useInboxNotifier } from '@/hooks/use-inbox-notifier'
import { useHealth } from '@/hooks/useHealth'
import { getApiBaseUrl } from '@/lib/api'
import { TerminalDock, useDockShortcut } from '@/components/terminal/TerminalDock'
import { useDock } from '@/components/terminal/dock-store'
import { cn } from '@/lib/utils'
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
  const dockPosition = useDock((s) => s.position)
  useDockShortcut()
  useInboxNotifier()
  const inbox = useInboxSummary().data

  return (
    <TooltipProvider delayDuration={300}>
      <SidebarProvider style={SIDEBAR_STYLE} className="h-screen">
        <AppSidebar
          active={section.id}
          inboxCount={typeof inbox?.pending === 'number' ? inbox.pending : 0}
          backendState={health.state}
          backendVersion={health.data?.version}
        />
        <SidebarInset className="flex min-w-0 flex-col bg-background">
          <AppHeader section={section} />
          {(health.state === 'disconnected' ||
            health.state === 'reconnecting' ||
            health.state === 'failed') && (
            <OfflineBanner
              state={health.state}
              onRetry={() => void health.refetch()}
              url={apiUrl}
            />
          )}
          <div
            className={cn(
              'flex min-h-0 min-w-0 flex-1',
              dockPosition === 'right' ? 'flex-row' : 'flex-col',
            )}
          >
            <main className="min-h-0 min-w-0 flex-1 overflow-auto">
              <Outlet />
            </main>
            <TerminalDock />
          </div>
        </SidebarInset>
      </SidebarProvider>
      <Toaster position="bottom-right" theme={theme} duration={5200} />
    </TooltipProvider>
  )
}
