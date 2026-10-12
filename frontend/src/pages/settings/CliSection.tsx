import { RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useClis, useRefreshClis } from '@/api/clis'
import type { CliInfo } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useNow } from '@/hooks/use-now'
import { errorMessage } from '@/lib/form-errors'
import { relativeTime } from '@/lib/time'
import { cn } from '@/lib/utils'

const INITIALS: Record<string, string> = { claude: 'CC', agy: 'AG' }

type Status = 'loggedIn' | 'loggedOut' | 'notDetected' | 'unknown'

function statusOf(cli: CliInfo): Status {
  if (!cli.installed) return 'notDetected'
  if (cli.logged_in === null) return 'unknown'
  return cli.logged_in ? 'loggedIn' : 'loggedOut'
}

const STATUS_COLOR: Record<Status, string> = {
  loggedIn: 'text-status-done',
  loggedOut: 'text-status-waiting',
  notDetected: 'text-status-failed',
  unknown: 'text-muted-foreground',
}

/** «CLIs detectados» (design `12-ajustes`): path, version, session and «Comprobar». */
export function CliSection() {
  const { t } = useTranslation()
  const { data: clis } = useClis()
  const refresh = useRefreshClis()
  const [checking, setChecking] = useState(false)
  const now = useNow(60_000)

  async function check() {
    setChecking(true)
    try {
      await refresh()
      toast.success(t('settings.clis.checked'))
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setChecking(false)
    }
  }

  return (
    <section aria-labelledby="clis-title" className="flex flex-col gap-2.5">
      <h2 id="clis-title" className="text-[15px] font-medium">
        {t('settings.clis.title')}
      </h2>
      {!clis ? (
        <Skeleton className="h-32 rounded-xl" />
      ) : (
        <ul aria-labelledby="clis-title" className="divide-y rounded-xl border bg-card">
          {clis.map((cli) => {
            const status = statusOf(cli)
            const hint =
              status === 'notDetected'
                ? t(`settings.clis.install.${cli.id}`)
                : status === 'loggedOut'
                  ? t(`settings.clis.login.${cli.id}`)
                  : null
            return (
              <li key={cli.id} className="flex flex-wrap items-center gap-4 px-4 py-3">
                <span
                  aria-hidden
                  className="flex size-[34px] shrink-0 items-center justify-center rounded-md border bg-primary font-mono text-[11px] font-bold text-white"
                >
                  {INITIALS[cli.id] ?? cli.id.slice(0, 2).toUpperCase()}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13.5px] font-medium">{cli.name}</span>
                  <span className="block truncate font-mono text-[11.5px] text-muted-foreground">
                    {cli.path ?? t('settings.clis.notFound')}
                  </span>
                  {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
                </span>
                <span className="w-24 font-mono text-[12.5px]">
                  {cli.version ? `v${cli.version.split(' ')[0]}` : t('settings.clis.noVersion')}
                </span>
                <span className="w-44 text-[12.5px]">
                  <span className={cn('flex items-center gap-1.5', STATUS_COLOR[status])}>
                    <span aria-hidden className="size-1.5 rounded-full bg-current" />
                    {t(`settings.clis.status.${status}`)}
                  </span>
                  {cli.checked_at && (
                    <span className="block text-[11.5px] text-muted-foreground">
                      {t('settings.clis.checkedAgo', { time: relativeTime(cli.checked_at, now) })}
                    </span>
                  )}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={checking}
                  onClick={() => void check()}
                >
                  <RefreshCw className={cn(checking && 'animate-spin')} />
                  {t('settings.clis.check')}
                </Button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
