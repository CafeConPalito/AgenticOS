import { Maximize2, PanelBottom, PanelRight, X } from 'lucide-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { useRuns } from '@/api/runs'
import type { Run } from '@/api/types'
import { AgentAvatar } from '@/components/agentic/primitives'
import { cn } from '@/lib/utils'
import { runTitle } from '@/pages/runs/RunPage'
import { useDock } from './dock-store'
import { TerminalPanel } from './TerminalPanel'

/** Ctrl+` (the key left of 1, «º» on a Spanish keyboard, as in VS Code) toggles the dock. */
export function useDockShortcut() {
  const toggle = useDock((s) => s.toggle)
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.ctrlKey && !e.altKey && !e.shiftKey && !e.metaKey && e.code === 'Backquote') {
        // Capture phase: a focused xterm must not receive it.
        e.preventDefault()
        e.stopPropagation()
        toggle()
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [toggle])
}

function dotClass(run: Run) {
  if (run.status === 'intervening') return 'bg-status-intervening'
  if (run.status === 'starting') return 'bg-status-queued animate-live-pulse'
  return run.activity === 'busy' ? 'bg-status-running animate-live-pulse' : 'bg-status-running'
}

/** Global terminal dock: one tab per active run, docked at the bottom or on the right. */
export function TerminalDock() {
  const open = useDock((s) => s.open)
  return open ? <OpenDock /> : null
}

function OpenDock() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { position, activeRunId, setOpen, swapPosition, setActive } = useDock()
  const { data: runs = [] } = useRuns({ active: true })
  const active = runs.find((r) => r.id === activeRunId) ?? runs[0]

  const actions = [
    {
      icon: position === 'right' ? PanelBottom : PanelRight,
      label: position === 'right' ? t('dock.toBottom') : t('dock.toRight'),
      onClick: swapPosition,
      disabled: false,
    },
    {
      icon: Maximize2,
      label: t('dock.expand'),
      onClick: () => active && navigate(`/ejecuciones/${active.id}`),
      disabled: !active,
    },
    { icon: X, label: t('dock.close'), onClick: () => setOpen(false), disabled: false },
  ]

  return (
    <aside
      aria-label={t('dock.label')}
      data-terminal-dock
      className={cn(
        'flex shrink-0 flex-col bg-terminal text-terminal-foreground',
        position === 'bottom' ? 'h-[260px] border-t' : 'w-[440px] border-l',
      )}
    >
      <div className="flex h-9 shrink-0 items-stretch border-b border-terminal-border bg-terminal-header">
        <div role="tablist" aria-label={t('dock.tabs')} className="flex min-w-0 overflow-x-auto">
          {runs.map((run) => {
            const selected = run.id === active?.id
            return (
              <button
                key={run.id}
                type="button"
                role="tab"
                aria-selected={selected}
                title={run.prompt}
                onClick={() => setActive(run.id)}
                className={cn(
                  'flex shrink-0 items-center gap-[7px] border-r border-terminal-border px-3 text-xs whitespace-nowrap',
                  selected
                    ? 'bg-terminal text-terminal-foreground shadow-[inset_0_2px_0_var(--terminal-accent)]'
                    : 'text-terminal-muted hover:text-terminal-foreground',
                )}
              >
                <span aria-hidden className={cn('size-[7px] rounded-full', dotClass(run))} />
                <AgentAvatar
                  name={run.agent_name}
                  color={run.agent_color}
                  agentId={run.agent_id}
                  size={16}
                />
                {runTitle(run, 32)}
              </button>
            )
          })}
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-0.5 px-1.5">
          {actions.map(({ icon: Icon, label, onClick, disabled }) => (
            <button
              key={label}
              type="button"
              onClick={onClick}
              disabled={disabled}
              aria-label={label}
              title={label}
              className="grid size-7 place-items-center rounded-md text-terminal-muted hover:bg-terminal-chip hover:text-terminal-foreground disabled:pointer-events-none disabled:opacity-40"
            >
              <Icon className="size-[15px]" />
            </button>
          ))}
        </div>
      </div>
      <div className="flex min-h-0 flex-1 flex-col">
        {active ? (
          <TerminalPanel key={active.id} run={active} variant="dock" />
        ) : (
          <p className="m-auto px-4 text-center text-[13px] text-terminal-muted">
            {t('dock.empty')}
          </p>
        )}
      </div>
    </aside>
  )
}
