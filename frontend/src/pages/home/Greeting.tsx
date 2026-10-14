import { useTranslation } from 'react-i18next'
import i18n from '@/i18n'
import { formatTokensUnit, formatUsd } from '@/lib/format'

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="flex h-[30px] items-center gap-[7px] rounded-full border border-sep bg-card/65 px-[13px] backdrop-blur-[10px]">
      {children}
    </span>
  )
}

export function greetingKey(hour: number): 'morning' | 'afternoon' | 'evening' {
  if (hour < 13) return 'morning'
  if (hour < 20) return 'afternoon'
  return 'evening'
}

/** Date, live sessions, the greeting and the three chips of the day. */
export function Greeting({
  sessions,
  working,
  waiting,
  cost,
  tokens,
  now = new Date(),
}: {
  sessions: number
  working: number
  waiting: number
  /** Spent today, in USD; with no cost (agy only) the tokens are shown. */
  cost: number
  tokens: number
  now?: Date
}) {
  const { t } = useTranslation()
  const date = new Intl.DateTimeFormat(i18n.language, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  }).format(now)
  const spent = cost > 0 || tokens === 0 ? formatUsd(cost) : formatTokensUnit(tokens)

  return (
    <div className="flex min-w-0 animate-rise-in flex-col gap-3.5">
      <div className="font-mono text-[11.5px] tracking-[0.14em] text-muted-foreground uppercase">
        {date} · {t('home.live', { count: sessions })}
      </div>
      <h1 className="-mt-1.5 text-[40px] leading-[1.05] font-bold tracking-[-0.035em] whitespace-nowrap">
        {t(`home.greeting.${greetingKey(now.getHours())}`)}
      </h1>
      <div className="flex flex-wrap items-center gap-2 text-[13px] whitespace-nowrap text-muted-foreground">
        <Chip>
          <span className="size-[7px] animate-live-pulse rounded-full bg-status-running" />
          <b className="font-medium text-foreground">{working}</b>
          {t('home.chips.working')}
        </Chip>
        <Chip>
          <span className="size-[7px] rounded-full bg-status-waiting" />
          <b className="font-medium text-foreground">{waiting}</b>
          {t('home.chips.waiting')}
        </Chip>
        <Chip>
          <b className="font-mono font-medium text-foreground">{spent}</b>
          {t('home.chips.spent')}
        </Chip>
      </div>
    </div>
  )
}
