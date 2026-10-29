import { useQuery } from '@tanstack/react-query'
import { Outlet, useLocation } from 'react-router'
import { Toaster } from '@/components/ui/sonner'
import { CommandPalette } from '@/components/palette/CommandPalette'
import { ShortcutsDialog } from '@/components/palette/ShortcutsDialog'
import { DownloadSpeechDialog } from '@/components/dictation/DownloadSpeechDialog'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useInboxNotifier } from '@/hooks/use-inbox-notifier'
import { useHealth } from '@/hooks/useHealth'
import { getApiBaseUrl } from '@/lib/api'
import { useHoldToDictate } from '@/lib/dictation/hold'
import { useGlobalShortcuts } from '@/lib/shortcuts'
import { TerminalDock, useDockShortcut } from '@/components/terminal/TerminalDock'
import { useDock } from '@/components/terminal/dock-store'
import { cn } from '@/lib/utils'
import { NewAgentDialog } from '@/pages/agents/NewAgentDialog'
import { TeamDialog } from '@/pages/home/TeamDialog'
import { NewProjectDialog } from '@/pages/projects/NewProjectDialog'
import { NewTaskDialog } from '@/pages/tasks/NewTaskDialog'
import { useDialogs } from '@/stores/dialogs'
import { useTheme } from '@/theme/ThemeProvider'
import { AppHeader } from './AppHeader'
import { OfflineBanner } from './OfflineBanner'
import { sectionForPath } from './nav'

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
  const newTask = useDialogs((s) => s.newTask)
  const closeNewTask = useDialogs((s) => s.closeNewTask)
  const palette = useDialogs((s) => s.palette)
  const closePalette = useDialogs((s) => s.closePalette)
  const shortcuts = useDialogs((s) => s.shortcuts)
  const closeShortcuts = useDialogs((s) => s.closeShortcuts)
  const newAgent = useDialogs((s) => s.newAgent)
  const closeNewAgent = useDialogs((s) => s.closeNewAgent)
  const newAgentInit = useDialogs((s) => s.newAgentInit)
  const team = useDialogs((s) => s.newTeam)
  const closeTeam = useDialogs((s) => s.closeTeam)
  const newProject = useDialogs((s) => s.newProject)
  const closeNewProject = useDialogs((s) => s.closeNewProject)
  useDockShortcut()
  useGlobalShortcuts()
  useHoldToDictate()
  useInboxNotifier()

  return (
    <TooltipProvider delayDuration={300}>
      {/* Clip, not hidden: an overflow-hidden box can still be scrolled from code, and a
          scrollIntoView near the end of a page (Ajustes › Limpieza) slid the whole app up with
          no way back (phase 21). */}
      <div className="relative flex h-screen flex-col overflow-clip bg-background">
        <div aria-hidden className="pointer-events-none absolute inset-0 bg-atmos" />
        <AppHeader
          section={section.id}
          backendState={health.state}
          backendVersion={health.data?.version}
          endpoint={apiUrl}
        />
        <div className="relative z-[1] flex min-h-0 flex-1 flex-col pt-14">
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
        </div>
      </div>
      <NewTaskDialog
        open={newTask !== null}
        init={newTask}
        onOpenChange={(open) => !open && closeNewTask()}
      />
      <NewAgentDialog
        open={newAgent}
        init={newAgentInit}
        onOpenChange={(open) => !open && closeNewAgent()}
      />
      <TeamDialog team={team} onClose={closeTeam} />
      <NewProjectDialog open={newProject} onOpenChange={(open) => !open && closeNewProject()} />
      <CommandPalette open={palette} onOpenChange={(open) => !open && closePalette()} />
      <ShortcutsDialog open={shortcuts} onOpenChange={(open) => !open && closeShortcuts()} />
      <DownloadSpeechDialog />
      <Toaster theme={theme} />
    </TooltipProvider>
  )
}
