import type { TFunction } from 'i18next'
import { ChevronDown, Plus } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'
import type { Account, CliInfo, HomeAgent, HomeProject, LimitState, UsageToday } from '@/api/types'
import { AgentAvatar, CLI_TAG } from '@/components/agentic/primitives'
import { formatPercent, formatTokensUnit, formatUsd } from '@/lib/format'
import { highestWindow, windowName } from '@/lib/quota'
import { cn } from '@/lib/utils'
import { useDialogs } from '@/stores/dialogs'

/** From here the spend turns amber. */
export const WARN_AT = 0.8
const ROW = '-mx-2 rounded-[9px] px-2 text-foreground hover:bg-subtle'

function AsideSection({
  title,
  meta,
  link,
  onAdd,
  addLabel,
  children,
}: {
  title: string
  meta?: string
  link?: { label: string; to: string }
  onAdd?: () => void
  addLabel?: string
  children: React.ReactNode
}) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="flex flex-col gap-1">
      <div className="mb-1.5 flex items-center gap-2">
        <h2 id={id} className="m-0 shrink-0 eyebrow whitespace-nowrap">
          {title}
        </h2>
        {meta && <span className="min-w-0 truncate text-xs text-muted-foreground">{meta}</span>}
        {link && (
          <Link
            to={link.to}
            className="ml-auto text-xs text-muted-foreground hover:text-foreground"
          >
            {link.label}
          </Link>
        )}
        {onAdd && (
          <button
            type="button"
            onClick={onAdd}
            aria-label={addLabel}
            title={addLabel}
            className="grid size-6 shrink-0 place-items-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <Plus className="size-[13px]" />
          </button>
        )}
      </div>
      {children}
    </section>
  )
}

/** The sum of the daily limits that are set, or null when none is. */
function totalLimit(states: LimitState[]): number | null {
  const set = states.filter((s) => s.limit !== null)
  return set.length > 0 ? set.reduce((sum, s) => sum + (s.limit ?? 0), 0) : null
}

/** Today's spend against the daily limit (amber from 80 %). */
export function SpendMeter({
  cost,
  tokens,
  limit,
}: {
  cost: number
  tokens: number
  limit: number | null
}) {
  const { t } = useTranslation()
  const usd = limit
  const ratio = usd ? cost / usd : null
  const amount = cost > 0 || tokens === 0 ? formatUsd(cost) : formatTokensUnit(tokens)
  return (
    <Link
      to="/consumo"
      aria-label={t('home.summary.spend')}
      className="flex flex-col gap-2.5 rounded-lg hover:no-underline"
    >
      <div className="flex items-baseline gap-2">
        <h2 className="m-0 eyebrow whitespace-nowrap">{t('home.summary.spend')}</h2>
        <span className="ml-auto font-mono">
          <strong className="text-xl font-bold tracking-[-0.02em]">{amount}</strong>
          {usd && <span className="text-muted-foreground"> / {formatUsd(usd)}</span>}
        </span>
      </div>
      {ratio !== null ? (
        <>
          <span
            role="progressbar"
            aria-valuenow={Math.round(ratio * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            className="relative h-1.5 rounded-full bg-muted"
          >
            <span
              className={cn(
                'absolute inset-y-0 left-0 rounded-full',
                ratio >= WARN_AT ? 'bg-status-waiting' : 'bg-muted-foreground',
              )}
              style={{ width: `${Math.min(ratio, 1) * 100}%` }}
            />
            <span
              title={t('home.summary.warnAt')}
              className="absolute -inset-y-[3px] left-[80%] w-px bg-muted-foreground"
            />
          </span>
          <span className="text-xs text-muted-foreground">
            {t('home.summary.ofLimit', { percent: formatPercent(ratio) })}
          </span>
        </>
      ) : (
        <span className="text-xs text-muted-foreground">{t('home.summary.noLimit')}</span>
      )}
    </Link>
  )
}

/** What fills an account's bar: its fullest subscription window, else its daily limit. */
export function accountLevel(
  account: Account,
  now: number = Date.now(),
): { ratio: number; source: 'quota' | 'daily'; window?: string } | null {
  const window = highestWindow(account, now)
  if (window) return { ratio: window.used_pct / 100, source: 'quota', window: window.id }
  if (account.daily_limit)
    return { ratio: account.used_today / account.daily_limit, source: 'daily' }
  return null
}

function LevelBar({ ratio }: { ratio: number | null }) {
  return (
    <span className="h-1 overflow-hidden rounded-full bg-muted">
      <span
        className={cn(
          'block h-full',
          (ratio ?? 0) >= WARN_AT ? 'bg-status-waiting' : 'bg-muted-foreground',
        )}
        style={{ width: `${Math.min(ratio ?? 0, 1) * 100}%` }}
      />
    </span>
  )
}

function LevelPercent({ ratio }: { ratio: number | null }) {
  return (
    <span
      className={cn(
        'text-right font-mono text-xs',
        (ratio ?? 0) >= WARN_AT ? 'text-status-waiting' : 'text-muted-foreground',
      )}
    >
      {ratio !== null ? formatPercent(ratio) : '—'}
    </span>
  )
}

function levelTitle(t: TFunction, level: ReturnType<typeof accountLevel>): string | undefined {
  if (!level) return undefined
  return level.source === 'quota'
    ? t('home.summary.quotaWindow', {
        window: windowName(level.window ?? ''),
        percent: formatPercent(level.ratio),
      })
    : t('home.summary.dailyTitle', { percent: formatPercent(level.ratio) })
}

/** One CLI: the fullest of its accounts; a click shows each account with its own bar. */
function CliRow({ cli, accounts }: { cli: CliInfo; accounts: Account[] }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const levels = accounts.map((account) => accountLevel(account))
  const worst = levels.reduce<number | null>(
    (max, level) => (level && (max === null || level.ratio > max) ? level.ratio : max),
    null,
  )
  const sessions = accounts.reduce((sum, a) => sum + a.live_runs, 0)
  const session = !cli.installed
    ? 'missing'
    : accounts.some((a) => a.session_state === 'down')
      ? 'down'
      : accounts.length > 0 && accounts.every((a) => a.session_state === 'ok')
        ? 'ok'
        : 'unknown'
  const meta = `${t('home.summary.accountsCount', { count: accounts.length })} · ${t('home.summary.sessionsCount', { count: sessions })}`
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-label={t(open ? 'home.summary.collapse' : 'home.summary.expand', {
          cli: t(`cli.${cli.id}`),
        })}
        onClick={() => setOpen((v) => !v)}
        title={
          worst !== null
            ? t('home.summary.quotaTitle', { percent: formatPercent(worst) })
            : undefined
        }
        className={cn(
          ROW,
          'grid w-[calc(100%+1rem)] grid-cols-[24px_minmax(0,1fr)_56px_34px_14px] items-center gap-x-2 gap-y-px py-1.5 text-left',
        )}
      >
        <span className="grid h-[18px] place-items-center rounded-[5px] border font-mono text-[10px] font-bold text-muted-foreground">
          {CLI_TAG[cli.id]}
        </span>
        <span className="truncate">{t(`cli.${cli.id}`)}</span>
        <LevelBar ratio={worst} />
        <LevelPercent ratio={worst} />
        <ChevronDown
          aria-hidden
          className={cn('size-3 text-muted-foreground transition-transform', open && 'rotate-180')}
        />
        <span
          className={cn(
            'col-[2/5] truncate text-xs',
            session === 'ok' || session === 'unknown'
              ? 'text-muted-foreground'
              : 'text-status-waiting',
          )}
        >
          {session === 'ok' || session === 'unknown'
            ? meta
            : `${t(`home.summary.cliSession.${session}`)} · ${meta}`}
        </span>
      </button>
      {open && (
        <ul aria-label={t('clis.accountsOf', { cli: t(`cli.${cli.id}`) })} className="mb-1">
          {accounts.map((account, i) => {
            const level = levels[i]
            return (
              <li
                key={account.id}
                title={levelTitle(t, level)}
                className="grid grid-cols-[minmax(0,1fr)_56px_34px] items-center gap-x-2 gap-y-px py-1 pl-8 text-[12.5px]"
              >
                <span className="truncate">{account.name}</span>
                <LevelBar ratio={level?.ratio ?? null} />
                <LevelPercent ratio={level?.ratio ?? null} />
                <span className="col-span-3 truncate text-xs text-muted-foreground">
                  {[
                    account.plan,
                    account.session_state === 'down' ? t('home.summary.cliSession.down') : null,
                    account.live_runs > 0
                      ? t('home.summary.sessionsCount', { count: account.live_runs })
                      : t('home.summary.accountFree'),
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

/** The right column: projects, today's spend and the CLIs, straight on the background. */
export function SummaryAside({
  agents,
  projects,
  today,
  clis,
  accounts,
}: {
  agents: HomeAgent[]
  projects: HomeProject[]
  today: UsageToday | undefined
  clis: CliInfo[]
  accounts: Account[]
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const openNewProject = useDialogs((s) => s.openNewProject)
  const limits = today && Array.isArray(today.limits) ? today.limits : []
  // The day's spend is Claude Code's; its limit is what the Claude accounts add up to.
  const claude = totalLimit(limits.filter((l) => l.cli === 'claude'))

  return (
    <aside
      aria-label={t('home.summary.label')}
      className="sticky top-[84px] flex min-w-0 animate-rise-in flex-col gap-[30px] border-l border-sep pt-5 pl-7 [animation-delay:240ms] max-xl:static max-xl:border-t max-xl:border-l-0 max-xl:pl-0"
    >
      <AsideSection
        title={t('home.summary.projects')}
        meta={t('home.summary.projectsMeta', { count: projects.length })}
        link={{ label: t('home.summary.allProjects'), to: '/proyectos' }}
        onAdd={openNewProject}
        addLabel={t('home.summary.newProject')}
      >
        {projects.map((project) => (
          <Link
            key={project.id}
            to={`/proyectos/${project.id}`}
            className={cn(
              ROW,
              'grid grid-cols-[8px_minmax(0,1fr)_auto] items-center gap-x-2.5 gap-y-px py-1.5',
            )}
          >
            <span className="size-2 rounded-[2px]" style={{ background: project.color }} />
            <span className="truncate">{project.name}</span>
            <span className="text-xs whitespace-nowrap text-muted-foreground">
              {t('home.summary.openTasks', { count: project.open_tasks })}
            </span>
            <span className="col-start-2 truncate text-xs text-muted-foreground">
              {project.workers.length > 0
                ? project.workers.map((w) => `${w.agent_name} · ${w.task_title}`).join(', ')
                : t('home.summary.idle')}
            </span>
            <span className="col-start-3 flex justify-end gap-0.5">
              {project.workers.map((w) => (
                <AgentAvatar
                  key={w.task_code}
                  name={w.agent_name}
                  color={agents.find((a) => a.id === w.agent_id)?.color ?? '#8FB4FF'}
                  size={16}
                />
              ))}
            </span>
          </Link>
        ))}
        {projects.length === 0 && (
          <p className="text-xs text-muted-foreground">{t('home.summary.noProjects')}</p>
        )}
      </AsideSection>

      <SpendMeter cost={today?.cost_usd ?? 0} tokens={today?.tokens ?? 0} limit={claude} />

      <AsideSection
        title={t('home.summary.clis')}
        link={{ label: t('home.summary.manage'), to: '/clis' }}
        onAdd={() => void navigate('/clis?nueva=1')}
        addLabel={t('home.summary.addAccount')}
      >
        {clis.map((cli) => (
          <CliRow key={cli.id} cli={cli} accounts={accounts.filter((a) => a.cli === cli.id)} />
        ))}
      </AsideSection>
    </aside>
  )
}
