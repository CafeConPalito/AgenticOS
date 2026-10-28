import { Eye, Hand, Keyboard, Undo2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { isActive, useRunControl } from '@/api/runs'
import type { Run } from '@/api/types'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/form-errors'
import { cn } from '@/lib/utils'
import { useRunTerminal } from './use-run-terminal'

/**
 * A run's live terminal with the design's frame: read-only by default, «Tomar control» gives
 * this view the keyboard (the agent is interrupted with Esc) until «Devolver al agente».
 * The `dock` variant is a frameless, always read-only viewer.
 */
export function TerminalPanel({
  run,
  variant = 'page',
  className,
}: {
  run: Run
  variant?: 'page' | 'dock'
  className?: string
}) {
  const { t } = useTranslation()
  const [fitAtMount] = useState(() => variant === 'page' && isActive(run))
  const control = useRunControl(run.id)
  const {
    containerRef,
    viewerId,
    state,
    exit,
    interactive: mine,
  } = useRunTerminal(run.id, {
    // A finished run is replayed at the size it was drawn at; only a live one is fitted.
    // Decided at mount: a run ending while it is shown keeps its (already right) terminal.
    fit: fitAtMount,
    size: { cols: run.cols, rows: run.rows },
  })
  const controller = state ? state.controller : run.controller
  const status = exit?.status ?? state?.status ?? run.status
  const activity = state?.activity ?? run.activity
  const finished = Boolean(exit) || !isActive({ status })
  const someoneElse = controller !== null && !mine

  async function act(action: 'take' | 'release') {
    try {
      await control.mutateAsync({ action, client_id: viewerId })
      if (action === 'release') toast.success(t('terminal.released', { name: run.agent_name }))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <section
      aria-label={t('terminal.label')}
      className={cn(
        'flex min-h-0 flex-1 flex-col overflow-hidden rounded-[11px] bg-terminal transition-[box-shadow,border-color] duration-200',
        mine
          ? 'border-2 border-status-intervening shadow-[0_0_0_4px_color-mix(in_oklch,var(--status-intervening)_22%,transparent)]'
          : 'border',
        variant === 'dock' && 'rounded-none border-0',
        className,
      )}
    >
      {variant === 'page' && (
        <header className="flex items-center gap-2.5 border-b border-terminal-border bg-terminal-header py-2 pr-2.5 pl-3 text-terminal-foreground">
          <span aria-hidden className="flex gap-[5px]">
            {[0, 1, 2].map((i) => (
              <span key={i} className="size-[9px] rounded-full bg-terminal-dot" />
            ))}
          </span>
          <span className="min-w-0 truncate font-mono text-[12.5px]">
            {run.agent_name} · {run.cli_session_id?.slice(0, 8) ?? run.id.slice(0, 8)}
          </span>
          {mine ? (
            <span className="inline-flex h-[22px] shrink-0 items-center gap-1.5 rounded-full bg-status-intervening px-[9px] text-[11.5px] font-bold whitespace-nowrap text-status-intervening-foreground">
              <Keyboard className="size-3" />
              {t('terminal.intervening')}
            </span>
          ) : (
            <span className="inline-flex h-[22px] shrink-0 items-center gap-1.5 rounded-full bg-terminal-chip px-[9px] text-[11.5px] whitespace-nowrap text-terminal-foreground">
              <Eye className="size-3" />
              {finished
                ? t('terminal.finished')
                : someoneElse
                  ? t('terminal.otherController')
                  : t('terminal.observing')}
            </span>
          )}
          <div className="ml-auto shrink-0">
            {!finished &&
              (mine ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void act('release')}
                  disabled={control.isPending}
                  className="h-7 border-status-intervening bg-transparent text-status-intervening hover:bg-status-intervening/10 hover:text-status-intervening"
                >
                  <Undo2 />
                  {t('terminal.release')}
                </Button>
              ) : (
                <Button
                  size="sm"
                  onClick={() => void act('take')}
                  disabled={control.isPending || someoneElse}
                  className="h-7 bg-primary-action text-white hover:bg-primary-action-hover"
                >
                  <Hand />
                  {t('terminal.take')}
                </Button>
              ))}
          </div>
        </header>
      )}
      {run.log_purged && (
        <p className="border-b border-terminal-border px-3.5 py-2 font-mono text-[12px] text-terminal-muted">
          {t('runs.logPurged')}
        </p>
      )}
      <div
        ref={containerRef}
        data-testid="xterm"
        className={cn('min-h-0 flex-1 px-2 py-1.5', variant === 'dock' && 'overflow-auto')}
      />
      {variant === 'dock' ? (
        <div className="px-3.5 pb-2 font-mono text-[12px] text-terminal-muted">
          {finished ? t('terminal.finished') : t('terminal.dockReadOnly')}
        </div>
      ) : (
        !finished &&
        !mine && (
          <div className="flex items-center gap-2 px-3.5 pb-2 font-mono text-[12px] text-terminal-muted">
            {activity === 'busy'
              ? t('terminal.working', { name: run.agent_name })
              : t('terminal.waiting')}
            <span className="inline-block h-[13px] w-[7px] animate-blink bg-status-running align-[-2px]" />
          </div>
        )
      )}
    </section>
  )
}
