import { FileText, Loader2, RotateCcw, WifiOff } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import type { BackendState } from '@/hooks/useHealth'
import { openBackendLogs, restartBackend } from '@/lib/api'
import { cn } from '@/lib/utils'

/**
 * The backend is not answering. `reconnecting`: the desktop app is restarting it; `failed`:
 * it gave up («Reintentar» starts it again, «Abrir logs» shows why); `disconnected`: no
 * answer (in the browser, the backend runs on its own).
 */
export function OfflineBanner({
  state,
  onRetry,
  url,
}: {
  state: Extract<BackendState, 'reconnecting' | 'disconnected' | 'failed'>
  onRetry: () => void
  url?: string
}) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const reconnecting = state === 'reconnecting'

  async function restart() {
    setBusy(true)
    try {
      await restartBackend()
      onRetry()
    } catch (error) {
      toast.error(String(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      role="alert"
      className={cn(
        'flex shrink-0 flex-wrap items-center gap-2.5 border-b px-[18px] py-[9px] text-[12.5px]',
        reconnecting
          ? 'border-[color-mix(in_oklch,var(--status-waiting)_40%,transparent)] bg-[color-mix(in_oklch,var(--status-waiting)_14%,var(--background))]'
          : 'border-[color-mix(in_oklch,var(--status-failed)_40%,transparent)] bg-[color-mix(in_oklch,var(--status-failed)_14%,var(--background))]',
      )}
    >
      {reconnecting ? (
        <Loader2 className="size-4 animate-spin text-status-waiting" />
      ) : (
        <WifiOff className="size-4 text-status-failed" />
      )}
      <strong className="font-medium">
        {t(
          reconnecting
            ? 'backend.reconnectingTitle'
            : state === 'failed'
              ? 'backend.failedTitle'
              : 'backend.offlineTitle',
        )}
      </strong>
      <span className="text-muted-foreground">
        {t(
          reconnecting
            ? 'backend.reconnectingDescription'
            : state === 'failed'
              ? 'backend.failedDescription'
              : 'backend.offlineDescription',
        )}
      </span>
      {state === 'failed' ? (
        <span className="ml-auto flex gap-2">
          <Button
            size="sm"
            variant="outline"
            className="h-[26px]"
            disabled={busy}
            onClick={() => void restart()}
          >
            <RotateCcw />
            {t('backend.restart')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-[26px]"
            onClick={() => void openBackendLogs().catch((error) => toast.error(String(error)))}
          >
            <FileText />
            {t('backend.openLogs')}
          </Button>
        </span>
      ) : (
        !reconnecting && (
          <Button size="sm" variant="outline" className="ml-auto h-[26px]" onClick={onRetry}>
            {t('backend.retry')}
          </Button>
        )
      )}
      {url && state === 'disconnected' && (
        <span className="font-mono text-xs text-muted-foreground">{url}</span>
      )}
    </div>
  )
}
