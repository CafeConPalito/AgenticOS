import { ArrowLeft, ArrowRight, ChevronRight, Inbox, Search, SquareTerminal } from 'lucide-react'
import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useMatches, useNavigate } from 'react-router'
import { useHome } from '@/api/home'
import { useInboxSummary } from '@/api/inbox'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { Kbd } from '@/components/palette/Kbd'
import { useDock } from '@/components/terminal/dock-store'
import type { BackendState } from '@/hooks/useHealth'
import { isMacDesktop } from '@/lib/platform'
import { SHORTCUTS } from '@/lib/shortcuts'
import { cn } from '@/lib/utils'
import { useDialogs } from '@/stores/dialogs'
import { BackendStatus } from './BackendStatus'
import type { CrumbHandle } from './crumbs'
import { Logo } from './Logo'
import { type Section } from './nav'
import { TopNav } from './TopNav'
import { useHistoryStack } from './use-history-stack'

const ICON_BUTTON =
  'grid size-8 shrink-0 place-items-center rounded-full text-foreground hover:bg-accent'
const NAV_BUTTON =
  'grid size-7 shrink-0 place-items-center rounded-full bg-muted hover:bg-accent disabled:pointer-events-none disabled:opacity-40'

function useCrumbs() {
  return useMatches()
    .filter((m) => (m.handle as CrumbHandle | undefined)?.crumb)
    .map((m) => ({ id: m.id, path: m.pathname, node: (m.handle as CrumbHandle).crumb(m.params) }))
}

const PALETTE_KEYS = SHORTCUTS.find((s) => s.id === 'palette')!.keys

/** Glass bar over the content: logo, back, breadcrumb, top navigation and the global tools. */
export function AppHeader({
  section,
  backendState,
  backendVersion,
  endpoint,
}: {
  section: Section
  backendState: BackendState
  backendVersion?: string
  endpoint?: string
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const crumbs = useCrumbs()
  const counts = useHome().data?.counts
  const inboxPending = useInboxSummary().data?.pending ?? 0
  const { canForward } = useHistoryStack()
  const dockOpen = useDock((s) => s.open)
  const toggleDock = useDock((s) => s.toggle)
  const openPalette = useDialogs((s) => s.openPalette)

  const mac = isMacDesktop()
  const atHome = location.pathname === '/'
  // `key` is «default» for the first page of the session: nothing to go back to.
  const hasHistory = location.key !== 'default'
  const parent = crumbs.length > 1 ? crumbs[crumbs.length - 2].path : '/'
  function goBack() {
    if (hasHistory) void navigate(-1)
    else void navigate(parent)
  }

  return (
    <header
      // On macOS the header is the title bar: room for the system's buttons on the left, and
      // it drags the window.
      data-tauri-drag-region={mac || undefined}
      className={cn(
        'absolute inset-x-0 top-0 z-20 flex h-14 items-center gap-3 border-b border-sep px-[22px] glass',
        mac && 'pl-[84px]',
      )}
    >
      <Link
        to="/"
        aria-label={t('header.home')}
        className="flex items-center gap-2.5 text-foreground"
      >
        <Logo />
        <span className="text-[15px] font-bold tracking-[-0.01em] whitespace-nowrap">
          {t('app.name')}
        </span>
      </Link>
      <span aria-hidden className="mx-1 h-[22px] w-px bg-border" />
      {(!atHome || canForward) && (
        <div className="flex shrink-0 gap-1">
          <button
            type="button"
            onClick={goBack}
            disabled={atHome}
            aria-label={t('header.back')}
            title={t('header.backHint')}
            className={NAV_BUTTON}
          >
            <ArrowLeft className="size-[15px]" />
          </button>
          <button
            type="button"
            onClick={() => void navigate(1)}
            disabled={!canForward}
            aria-label={t('header.forward')}
            title={t('header.forwardHint')}
            className={NAV_BUTTON}
          >
            <ArrowRight className="size-[15px]" />
          </button>
        </div>
      )}

      <Breadcrumb className="min-w-0 flex-1">
        <BreadcrumbList className="flex-nowrap gap-1 text-[13px]">
          {crumbs.length === 0 ? (
            <BreadcrumbItem>
              <BreadcrumbPage className="px-1.5 font-medium whitespace-nowrap">
                {t(`nav.${section}`)}
              </BreadcrumbPage>
            </BreadcrumbItem>
          ) : (
            crumbs.map((crumb, i) => (
              <Fragment key={crumb.id}>
                {i > 0 && (
                  <BreadcrumbSeparator>
                    <ChevronRight className="size-[13px]" />
                  </BreadcrumbSeparator>
                )}
                <BreadcrumbItem className="min-w-0">
                  {i === crumbs.length - 1 ? (
                    <BreadcrumbPage className="truncate px-1.5 font-medium whitespace-nowrap">
                      {crumb.node}
                    </BreadcrumbPage>
                  ) : (
                    <BreadcrumbLink asChild>
                      <Link
                        to={crumb.path}
                        className="rounded-[5px] px-1.5 py-0.5 whitespace-nowrap text-muted-foreground hover:bg-accent hover:text-foreground"
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

      <TopNav active={section} counts={{ board: counts?.open_tasks, runs: counts?.active_runs }} />

      <Link
        to="/inbox"
        aria-label={t('header.inbox', { count: inboxPending })}
        title={t('header.inbox', { count: inboxPending })}
        aria-current={section === 'inbox' ? 'page' : undefined}
        className={cn(ICON_BUTTON, 'relative', section === 'inbox' && 'bg-accent')}
      >
        <Inbox className="size-[15px]" />
        {inboxPending > 0 && (
          <span
            aria-hidden
            className="absolute -top-0.5 -right-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-status-intervening px-1 font-mono text-[10px] font-bold text-status-intervening-foreground"
          >
            {inboxPending > 99 ? '99+' : inboxPending}
          </span>
        )}
      </Link>
      <button
        type="button"
        onClick={openPalette}
        className="flex h-8 w-[220px] items-center gap-2 rounded-full bg-muted/80 pr-1.5 pl-3 text-[12.5px] text-muted-foreground hover:bg-accent"
      >
        <Search className="size-3.5 shrink-0" />
        <span className="flex-1 truncate text-left">{t('header.search')}</span>
        <Kbd keys={PALETTE_KEYS} />
      </button>
      <button
        type="button"
        aria-pressed={dockOpen}
        aria-label={t('dock.toggle')}
        title={t('dock.toggle')}
        onClick={toggleDock}
        className={cn(ICON_BUTTON, dockOpen && 'bg-accent')}
      >
        <SquareTerminal className="size-[15px]" />
      </button>
      <span title={endpoint}>
        <BackendStatus state={backendState} version={backendVersion} />
      </span>
    </header>
  )
}
