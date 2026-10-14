import { CircleCheck, Gauge, Hand } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import type { InboxItem } from '@/api/types'
import { RequestActions } from '@/components/requests/RequestActions'
import { RequestItem } from '@/components/requests/RequestItem'
import { relativeTime } from '@/lib/time'
import { useUiPrefs } from '@/stores/ui-prefs'
import type { CliAlert } from './alerts'

const VISIBLE = 3

/** «Te necesitan»: the requests that wait for the person, then the CLI notices. */
export function NeedsYouPanel({
  requests,
  alerts,
  onHoverAgent,
}: {
  requests: InboxItem[]
  alerts: CliAlert[]
  onHoverAgent: (agentId: string | null) => void
}) {
  const { t } = useTranslation()
  const [showAll, setShowAll] = useState(false)
  const shown = showAll ? requests : requests.slice(0, VISIBLE)
  const total = requests.length + alerts.length

  if (total === 0)
    return (
      <div className="flex items-center gap-2 text-muted-foreground">
        <CircleCheck className="size-[15px] text-status-done" />
        {t('home.needs.empty')}
        <Link to="/inbox?status=resolved" className="ml-1 text-xs hover:text-foreground">
          {t('home.needs.resolved')}
        </Link>
      </div>
    )

  return (
    <section
      aria-labelledby="needs-title"
      className="animate-rise-in overflow-hidden rounded-2xl border border-[color-mix(in_oklch,var(--status-waiting)_50%,var(--sep))] bg-[linear-gradient(180deg,color-mix(in_oklch,var(--status-waiting)_10%,var(--card))_0,var(--card)_150px)] shadow-[0_0_0_4px_color-mix(in_oklch,var(--status-waiting)_7%,transparent),0_22px_50px_-18px_color-mix(in_oklch,var(--status-waiting)_30%,transparent),var(--shadow-card)] [animation-delay:80ms]"
    >
      <div className="flex h-[60px] items-center gap-3 pr-3.5 pl-[18px]">
        <span className="grid size-[30px] place-items-center rounded-full bg-[#F5B547] text-[#0A1A33] shadow-[0_0_22px_color-mix(in_oklch,#F5B547_50%,transparent)]">
          <Hand className="size-[15px]" />
        </span>
        <h2 id="needs-title" className="text-lg font-bold tracking-[-0.02em]">
          {t('home.needs.title')}
        </h2>
        <span className="grid h-5 min-w-5 place-items-center rounded-full bg-[#F5B547] px-[7px] text-[11.5px] font-bold text-[#0A1A33]">
          {total}
        </span>
        <div className="ml-auto flex items-center gap-1">
          {requests.length > VISIBLE && (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              aria-expanded={showAll}
              className="h-[30px] rounded-full px-3 text-[12.5px] text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              {showAll ? t('home.needs.less') : t('home.needs.all', { count: requests.length })}
            </button>
          )}
          <Link
            to="/inbox?status=resolved"
            className="flex h-[30px] items-center rounded-full px-3 text-[12.5px] text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            {t('home.needs.resolved')}
          </Link>
        </div>
      </div>
      {shown.map((item) => (
        <RequestItem key={item.id} item={item} variant="row" onHover={onHoverAgent} />
      ))}
      {alerts.map((alert) => (
        <CliAlertItem key={alert.id} alert={alert} />
      ))}
    </section>
  )
}

/** A system notice about the CLIs, with the anatomy of a request. */
export function CliAlertItem({ alert }: { alert: CliAlert }) {
  const { t } = useTranslation()
  const snooze = useUiPrefs((s) => s.snoozeAlert)
  // A logged-out session has its own «Reconectar»: «Revisar cuentas» would say the same.
  const review = (
    <>
      {alert.item?.kind !== 'account' && (
        <Link
          to="/clis"
          className="inline-flex h-7 items-center rounded-full bg-primary-action px-3 text-[12.5px] font-medium text-white hover:bg-primary-action-hover"
        >
          {t('home.alerts.review')}
        </Link>
      )}
      <button
        type="button"
        onClick={() => {
          snooze(alert.id)
          toast.success(t('home.alerts.snoozed'))
        }}
        className="h-7 rounded-full border px-3 text-[12.5px] hover:bg-accent"
      >
        {t('home.alerts.snooze')}
      </button>
    </>
  )
  return (
    <article
      aria-label={alert.title}
      className="grid grid-cols-[30px_minmax(0,1fr)] gap-3.5 border-t border-sep px-[18px] py-4"
    >
      <span className="grid size-[30px] place-items-center rounded-[9px] bg-muted text-status-waiting">
        <Gauge className="size-[15px]" />
      </span>
      <div className="flex min-w-0 flex-col gap-1.5">
        <div className="flex items-baseline gap-3">
          <h3 className="min-w-0 flex-1 text-sm font-medium">{alert.title}</h3>
          <span className="shrink-0 text-xs text-muted-foreground">
            {alert.createdAt ? relativeTime(alert.createdAt) : t('home.alerts.now')}
          </span>
        </div>
        <div className="text-xs text-muted-foreground">{t('home.alerts.kind')}</div>
        {alert.context && (
          <p className="text-[12.5px] text-pretty text-muted-foreground">{alert.context}</p>
        )}
        <div className="mt-1 flex flex-wrap gap-1.5">
          {alert.item ? (
            <RequestActions item={alert.item} inline extra={review} />
          ) : (
            <div className="flex gap-1.5">{review}</div>
          )}
        </div>
      </div>
    </article>
  )
}
