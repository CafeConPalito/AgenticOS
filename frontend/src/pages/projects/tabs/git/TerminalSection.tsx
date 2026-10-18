import { SquareTerminal } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { closeShell, useOpenShell } from '@/api/git-more'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { gitErrorText } from './git-errors'
import { useGitShell } from './use-git-shell'

/** A terminal in the repository's folder for what the interface does not cover. It is closed
 * when the person leaves the section. */
export function TerminalSection({ repoId }: { repoId: string }) {
  const { t } = useTranslation()
  const open = useOpenShell(repoId)
  const [shellId, setShellId] = useState<string | null>(null)
  const current = useRef<string | null>(null)

  useEffect(() => {
    current.current = shellId
  }, [shellId])
  useEffect(
    () => () => {
      if (current.current) void closeShell(current.current).catch(() => undefined)
    },
    [],
  )

  async function start() {
    try {
      setShellId((await open.mutateAsync()).shell_id)
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  if (!shellId)
    return (
      <div className="px-6 py-4">
        <EmptyState
          icon={SquareTerminal}
          title={t('git.terminal.title')}
          description={t('git.terminal.help')}
        >
          <Button type="button" size="sm" disabled={open.isPending} onClick={() => void start()}>
            {t('git.terminal.open')}
          </Button>
        </EmptyState>
      </div>
    )
  return <Shell shellId={shellId} onClose={() => setShellId(null)} />
}

function Shell({ shellId, onClose }: { shellId: string; onClose: () => void }) {
  const { t } = useTranslation()
  const { containerRef, exited } = useGitShell(shellId)
  return (
    <div className="flex flex-col gap-2 px-6 py-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {exited ? t('git.terminal.exited') : t('git.terminal.running')}
        </span>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => {
            void closeShell(shellId).catch(() => undefined)
            onClose()
          }}
        >
          {t('git.terminal.close')}
        </Button>
      </div>
      <div
        ref={containerRef}
        role="region"
        aria-label={t('git.terminal.label')}
        className="h-[420px] overflow-hidden rounded-[11px] border bg-terminal p-2"
      />
    </div>
  )
}
