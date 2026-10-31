import { PanelBottom, PanelRight, Plus, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { isActive, useRunControl } from '@/api/runs'
import { useCloseTerminal, useTerminals } from '@/api/terminals'
import type { Run } from '@/api/types'
import { CliTag } from '@/components/agentic/primitives'
import { errorMessage } from '@/lib/form-errors'
import { cn } from '@/lib/utils'
import { useDock } from './dock-store'
import { NewTerminalDialog } from './NewTerminalDialog'
import { useRunTerminal } from './use-run-terminal'

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

/** The last folder of a path, for a tab: `D:\code\web` → `web`; `~` stays. */
export function folderName(path: string): string {
  return (
    path
      .replace(/[\\/]+$/, '')
      .split(/[\\/]/)
      .pop() || path
  )
}

/**
 * Global terminal dock (phase 23, ADR 0029): the person's own terminals, a CLI each with the
 * account and folder they chose, in tabs. The agents' runs are in Ejecuciones.
 */
export function TerminalDock() {
  const open = useDock((s) => s.open)
  return open ? <OpenDock /> : null
}

function OpenDock() {
  const { t } = useTranslation()
  const { position, activeRunId, setOpen, swapPosition, setActive } = useDock()
  const terminals = useTerminals()
  const close = useCloseTerminal()
  const [creating, setCreating] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const list = terminals.data ?? []
  const active = list.find((run) => run.id === activeRunId) ?? list[0]
  // Opening the dock with no terminal asks for one at once.
  const asking = creating || (terminals.isSuccess && list.length === 0 && !dismissed)

  const actions = [
    {
      icon: position === 'right' ? PanelBottom : PanelRight,
      label: position === 'right' ? t('dock.toBottom') : t('dock.toRight'),
      onClick: swapPosition,
    },
    { icon: X, label: t('dock.close'), onClick: () => setOpen(false) },
  ]

  function closeTab(run: Run) {
    close.mutate(run.id, { onError: (error) => toast.error(errorMessage(error)) })
  }

  return (
    <aside
      aria-label={t('dock.label')}
      data-terminal-dock
      className={cn(
        'flex shrink-0 flex-col bg-terminal text-terminal-foreground',
        position === 'bottom' ? 'h-[300px] border-t' : 'w-[480px] border-l',
      )}
    >
      <div className="flex h-9 shrink-0 items-stretch border-b border-terminal-border bg-terminal-header">
        <div role="tablist" aria-label={t('dock.tabs')} className="flex min-w-0 overflow-x-auto">
          {list.map((run) => {
            const selected = run.id === active?.id
            const name = `${run.account_label} · ${folderName(run.cwd)}`
            return (
              <div
                key={run.id}
                className={cn(
                  'flex shrink-0 items-center border-r border-terminal-border',
                  selected
                    ? 'bg-terminal text-terminal-foreground shadow-[inset_0_2px_0_var(--terminal-accent)]'
                    : 'text-terminal-muted hover:text-terminal-foreground',
                )}
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  title={run.cwd}
                  onClick={() => setActive(run.id)}
                  className="flex items-center gap-[7px] py-1 pr-1 pl-3 text-xs whitespace-nowrap"
                >
                  <CliTag cli={run.cli} label={t(`cli.${run.cli}`)} size={16} />
                  {name}
                </button>
                <button
                  type="button"
                  aria-label={t('dock.closeTab', { name })}
                  onClick={() => closeTab(run)}
                  className="mr-1.5 grid size-5 place-items-center rounded hover:bg-terminal-chip"
                >
                  <X className="size-3" />
                </button>
              </div>
            )
          })}
          <button
            type="button"
            aria-label={t('dock.new.open')}
            title={t('dock.new.open')}
            onClick={() => setCreating(true)}
            className="grid w-9 shrink-0 place-items-center text-terminal-muted hover:text-terminal-foreground"
          >
            <Plus className="size-[15px]" />
          </button>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-0.5 px-1.5">
          {actions.map(({ icon: Icon, label, onClick }) => (
            <button
              key={label}
              type="button"
              onClick={onClick}
              aria-label={label}
              title={label}
              className="grid size-7 place-items-center rounded-md text-terminal-muted hover:bg-terminal-chip hover:text-terminal-foreground"
            >
              <Icon className="size-[15px]" />
            </button>
          ))}
        </div>
      </div>
      <div className="flex min-h-0 flex-1 flex-col">
        {active ? (
          <OwnTerminal key={active.id} run={active} onClose={() => closeTab(active)} />
        ) : (
          <div className="m-auto flex flex-col items-center gap-3 px-4 text-center text-[13px] text-terminal-muted">
            {t('dock.empty')}
            <button
              type="button"
              onClick={() => setCreating(true)}
              className="rounded-md bg-terminal-chip px-3 py-1.5 text-terminal-foreground hover:bg-terminal-dot"
            >
              {t('dock.new.open')}
            </button>
          </div>
        )}
      </div>
      <NewTerminalDialog
        open={asking}
        onOpenChange={(next) => {
          setCreating(next)
          if (!next) setDismissed(true)
        }}
        onOpened={(run) => {
          setCreating(false)
          setDismissed(true)
          setActive(run.id)
        }}
      />
    </aside>
  )
}

/** One terminal of the person's own: the view takes the keyboard while it is shown. */
function OwnTerminal({ run, onClose }: { run: Run; onClose: () => void }) {
  const { t } = useTranslation()
  const { mutate } = useRunControl(run.id)
  const { containerRef, viewerId, state, exit } = useRunTerminal(run.id, { fit: true })
  const status = exit?.status ?? state?.status ?? run.status
  const finished = Boolean(exit) || !isActive({ status })

  useEffect(() => {
    if (finished) return
    mutate({ action: 'take', client_id: viewerId })
    return () => mutate({ action: 'release', client_id: viewerId })
  }, [finished, mutate, viewerId])

  return (
    <section aria-label={t('terminal.label')} className="flex min-h-0 flex-1 flex-col">
      <div ref={containerRef} data-testid="xterm" className="min-h-0 flex-1 px-2 py-1.5" />
      {finished && (
        <div className="flex items-center gap-3 px-3.5 pb-2 font-mono text-[12px] text-terminal-muted">
          {t('dock.ended')}
          <button type="button" onClick={onClose} className="underline">
            {t('dock.closeEnded')}
          </button>
        </div>
      )}
    </section>
  )
}
