import { Download, Plus, Search, SquareTerminal } from 'lucide-react'
import { Fragment, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useMatches, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { downloadSessionsCsv, periodFromParam } from '@/api/usage'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { useDock } from '@/components/terminal/dock-store'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { LaunchRunDialog } from '@/pages/runs/LaunchRunDialog'
import { NewTaskDialog } from '@/pages/tasks/NewTaskDialog'
import type { CrumbHandle } from './crumbs'
import type { NavItem, PrimaryAction } from './nav'

/** Where each primary header action goes; actions without a route are not available yet. */
const PRIMARY_ROUTES: Partial<Record<PrimaryAction, string>> = {
  newAgent: '/agentes/nuevo',
  newProject: '/proyectos/nuevo',
}

function useCrumbs() {
  return useMatches()
    .filter((m) => (m.handle as CrumbHandle | undefined)?.crumb)
    .map((m) => ({ id: m.id, path: m.pathname, node: (m.handle as CrumbHandle).crumb(m.params) }))
}

export function AppHeader({ section }: { section: NavItem }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const comingSoon = t('header.comingSoon')
  const crumbs = useCrumbs()
  const primaryRoute = section.primary ? PRIMARY_ROUTES[section.primary] : undefined
  const [launching, setLaunching] = useState(false)
  const [creatingTask, setCreatingTask] = useState(false)
  const dockOpen = useDock((s) => s.open)
  const toggleDock = useDock((s) => s.toggle)
  const [params] = useSearchParams()
  const primaryAvailable =
    Boolean(primaryRoute) ||
    section.primary === 'launchRun' ||
    section.primary === 'newTask' ||
    section.primary === 'exportCsv'

  function onPrimary() {
    if (section.primary === 'launchRun') setLaunching(true)
    else if (section.primary === 'newTask') setCreatingTask(true)
    else if (section.primary === 'exportCsv')
      // The period the Consumo page shows (kept in its URL).
      downloadSessionsCsv({ days: periodFromParam(params.get('periodo')) }).then(
        () => toast.success(t('usage.exported')),
        (error: unknown) => toast.error(String(error)),
      )
    else if (primaryRoute) navigate(primaryRoute)
  }
  const PrimaryIcon = section.primary === 'exportCsv' ? Download : Plus

  return (
    <header className="flex h-[52px] shrink-0 items-center gap-3 border-b bg-background px-[18px]">
      <Breadcrumb className="min-w-0 flex-1">
        <BreadcrumbList className="flex-nowrap gap-1.5 text-[13px]">
          {crumbs.length === 0 ? (
            <BreadcrumbItem>
              <BreadcrumbPage className="font-medium whitespace-nowrap">
                {t(`nav.${section.id}`)}
              </BreadcrumbPage>
            </BreadcrumbItem>
          ) : (
            crumbs.map((crumb, i) => (
              <Fragment key={crumb.id}>
                {i > 0 && <BreadcrumbSeparator>/</BreadcrumbSeparator>}
                <BreadcrumbItem>
                  {i === crumbs.length - 1 ? (
                    <BreadcrumbPage className="truncate font-medium whitespace-nowrap">
                      {crumb.node}
                    </BreadcrumbPage>
                  ) : (
                    <BreadcrumbLink asChild>
                      <Link
                        to={crumb.path}
                        className="rounded-[5px] px-1.5 py-0.5 whitespace-nowrap hover:bg-accent"
                      >
                        {crumb.node}
                      </Link>
                    </BreadcrumbLink>
                  )}
                </BreadcrumbItem>
              </Fragment>
            ))
          )}
        </BreadcrumbList>
      </Breadcrumb>
      <button
        type="button"
        disabled
        title={comingSoon}
        className="flex h-8 w-[300px] items-center gap-2 rounded-lg border bg-subtle pr-2 pl-2.5 text-[12.5px] text-muted-foreground disabled:cursor-not-allowed"
      >
        <Search className="size-3.5" />
        <span className="flex-1 text-left">{t('header.search')}</span>
        <kbd className="rounded border bg-card px-1.5 py-px font-mono text-[11px]">
          {t('header.searchShortcut')}
        </kbd>
      </button>
      <Button
        variant="outline"
        aria-pressed={dockOpen}
        title={t('dock.toggle')}
        onClick={toggleDock}
        className={cn('h-8 gap-[7px]', dockOpen ? 'bg-accent' : 'bg-transparent')}
      >
        <SquareTerminal className="size-[15px]" />
        {t('header.terminal')}
      </Button>
      {section.primary && (
        <Button
          disabled={!primaryAvailable}
          title={primaryAvailable ? undefined : comingSoon}
          onClick={onPrimary}
          className="h-8 gap-1.5 bg-primary-action font-medium text-white hover:bg-primary-action-hover"
        >
          <PrimaryIcon className="size-[15px]" />
          {t(`header.primary.${section.primary}`)}
        </Button>
      )}
      <LaunchRunDialog open={launching} onOpenChange={setLaunching} />
      <NewTaskDialog open={creatingTask} onOpenChange={setCreatingTask} />
    </header>
  )
}
