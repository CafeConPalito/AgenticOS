import { LogIn, MoreHorizontal, RefreshCw, Star, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { useDeleteAccount, useMakeDefaultAccount, useProbeAccount } from '@/api/accounts'
import type { Account } from '@/api/types'
import { AgentAvatar, StatusBadge } from '@/components/agentic/primitives'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useNow } from '@/hooks/use-now'
import { errorMessage } from '@/lib/form-errors'
import { formatPercent, formatTokensUnit, formatUsd } from '@/lib/format'
import { relativeTime } from '@/lib/time'
import { cn } from '@/lib/utils'
import { QuotaBars } from './QuotaBars'

const WARN = 0.8

/** What the account used today against its daily limit, in its CLI's unit. */
function TodayMeter({ account }: { account: Account }) {
  const { t } = useTranslation()
  const format = account.unit === 'usd' ? formatUsd : formatTokensUnit
  const ratio = account.daily_limit ? account.used_today / account.daily_limit : null
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline gap-2 text-[12.5px]">
        <span className="font-medium">{t('accounts.today.label')}</span>
        <span className="ml-auto font-mono text-xs text-muted-foreground">
          {format(account.used_today)}
          {account.daily_limit ? ` / ${format(account.daily_limit)}` : ''}
        </span>
      </div>
      {ratio !== null ? (
        <>
          <span
            role="progressbar"
            aria-label={t('accounts.today.label')}
            aria-valuenow={Math.round(ratio * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            className="relative h-1.5 overflow-hidden rounded-full bg-muted"
          >
            <span
              className={cn(
                'absolute inset-y-0 left-0 rounded-full',
                ratio >= WARN ? 'bg-status-waiting' : 'bg-muted-foreground',
              )}
              style={{ width: `${Math.min(ratio, 1) * 100}%` }}
            />
          </span>
          <span className="text-[11.5px] text-muted-foreground">
            {t('accounts.today.ofLimit', { percent: formatPercent(ratio) })}
          </span>
        </>
      ) : (
        <span className="text-[11.5px] text-muted-foreground">{t('accounts.today.noLimit')}</span>
      )}
    </div>
  )
}

/** One login of a CLI: who it is, its session, its subscription windows and who works with it. */
export function AccountCard({
  account,
  onLogin,
}: {
  account: Account
  /** Opens the login terminal (the page starts the CLI's login first). */
  onLogin: (account: Account) => void
}) {
  const { t } = useTranslation()
  const probe = useProbeAccount()
  const makeDefault = useMakeDefaultAccount()
  const remove = useDeleteAccount()
  const [confirming, setConfirming] = useState(false)
  const now = useNow(60_000)
  const onError = (error: unknown) => toast.error(errorMessage(error))
  const down = account.session_state === 'down'
  const tone = account.session_state === 'ok' ? 'done' : down ? 'waiting' : 'cancelled'

  return (
    <li
      aria-label={account.name}
      className="flex flex-col gap-3.5 border-t border-sep px-4 py-3.5 first:border-t-0"
    >
      <div className="flex flex-wrap items-center gap-2.5">
        <span
          aria-hidden
          className="grid size-[26px] shrink-0 place-items-center rounded-full bg-secondary text-xs font-bold"
        >
          {account.name.slice(0, 1).toUpperCase()}
        </span>
        <span className="text-[14px] font-medium">{account.name}</span>
        {account.is_system && (
          <span className="text-xs text-muted-foreground">{t('accounts.system')}</span>
        )}
        {account.plan && (
          <Badge variant="secondary" className="h-[19px] rounded-full px-[7px] text-[11px]">
            {account.plan}
          </Badge>
        )}
        {account.is_default && (
          <Badge variant="outline" className="h-[19px] rounded-full px-[7px] text-[11px]">
            {t('accounts.default')}
          </Badge>
        )}
        <StatusBadge
          tone={tone}
          size="sm"
          label={
            account.logging_in
              ? t('accounts.session.loggingIn')
              : t(`accounts.session.${account.session_state}`)
          }
        />
        {account.session_checked_at && (
          <span className="text-[11.5px] text-muted-foreground">
            {t('accounts.session.checked', { time: relativeTime(account.session_checked_at, now) })}
          </span>
        )}
        <div className="ml-auto flex items-center gap-1.5">
          <Button
            size="sm"
            variant={down ? 'default' : 'outline'}
            onClick={() => onLogin(account)}
            className={down ? 'bg-primary-action text-white hover:bg-primary-action-hover' : ''}
          >
            <LogIn />
            {account.logging_in
              ? t('accounts.openLogin')
              : down
                ? t('accounts.reconnect')
                : t('accounts.signIn')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={probe.isPending}
            onClick={() => probe.mutate(account.id, { onError })}
          >
            <RefreshCw className={cn(probe.isPending && 'animate-spin')} />
            {t('accounts.check')}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                size="icon"
                variant="ghost"
                aria-label={t('accounts.more', { name: account.name })}
                className="size-8"
              >
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {!account.is_default && (
                <DropdownMenuItem
                  onSelect={() =>
                    makeDefault.mutate(account.id, {
                      onSuccess: () =>
                        toast.success(t('accounts.madeDefault', { name: account.name })),
                      onError,
                    })
                  }
                >
                  <Star />
                  {t('accounts.makeDefault')}
                </DropdownMenuItem>
              )}
              {!account.is_system && (
                <DropdownMenuItem variant="destructive" onSelect={() => setConfirming(true)}>
                  <Trash2 />
                  {t('accounts.remove')}
                </DropdownMenuItem>
              )}
              {account.is_default && account.is_system && (
                <DropdownMenuItem disabled>{t('accounts.systemKept')}</DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-8 gap-y-3 max-md:grid-cols-1">
        <QuotaBars windows={account.quota} />
        <TodayMeter account={account} />
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
        <span>{t('accounts.sessions', { count: account.live_runs })}</span>
        {account.agents.length === 0 ? (
          <span>{t('accounts.noAgents')}</span>
        ) : (
          <ul aria-label={t('accounts.agents')} className="flex flex-wrap items-center gap-1.5">
            {account.agents.map((agent) => (
              <li key={agent.id}>
                <Link
                  to={`/agentes/${agent.id}`}
                  className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-foreground hover:bg-accent"
                >
                  <AgentAvatar name={agent.name} color={agent.color} size={14} />
                  {agent.name}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('accounts.removeTitle', { name: account.name })}</AlertDialogTitle>
            <AlertDialogDescription>{t('accounts.removeDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                remove.mutate(account.id, {
                  onSuccess: () => toast.success(t('accounts.removed', { name: account.name })),
                  onError,
                })
              }
            >
              {t('accounts.remove')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </li>
  )
}
